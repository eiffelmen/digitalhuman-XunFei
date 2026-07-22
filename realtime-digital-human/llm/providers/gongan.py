import asyncio
import json
import os
import queue
import re
import time
import uuid
from datetime import datetime
from threading import Event, Thread
from typing import Callable, Optional

from loguru import logger

from basereal import BaseReal
from gongan_api import env_bool, env_float, get_gongan_client
from perf_logger import elapsed_ms, log_perf, log_timepoint, now


PUNCTUATION_RE = re.compile(r"[，。！？：；、,.!?;:\n]")


def _find_last_punct(text: str) -> int:
    last_punct = -1
    for mark in "，。！？：；、,.!?;:\n":
        pos = text.rfind(mark)
        if pos > last_punct:
            last_punct = pos
    return last_punct


def _clean_chunk(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    return text.translate(str.maketrans("", "", "*#-")).strip()


def _build_query(message: str) -> str:
    instruction = os.environ.get(
        "GONGAN_REPLY_INSTRUCTION",
        "请用简洁、口语化中文回答，控制在80字以内，适合数字人口播。不要输出思考过程。",
    ).strip()
    if not instruction:
        return message
    return f"{instruction}\n用户问题：{message}"


def _extract_answer(data) -> str:
    if not isinstance(data, dict):
        return ""
    if "answer" in data:
        answer = data.get("answer")
        return answer if isinstance(answer, str) else ""
    nested = data.get("data")
    if isinstance(nested, dict):
        answer = nested.get("answer") or nested.get("content")
        return answer if isinstance(answer, str) else ""
    content = data.get("content")
    return content if isinstance(content, str) else ""


def _use_agent_chat() -> bool:
    default_enabled = bool(
        os.environ.get("GONGAN_API_TOKEN")
        or os.environ.get("API_KEY")
        or os.environ.get("GONGAN_AGENT_FRIEND_ID")
        or os.environ.get("GONGAN_AGENT_ID")
    )
    return env_bool("GONGAN_AGENT_ENABLED", default_enabled)


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return max(minimum, int(value))
    except ValueError:
        logger.warning(f"Invalid {name}={value!r}; using {default}")
        return default


def _trim_history(history: list[dict], max_chars: int) -> list[dict]:
    if max_chars <= 0:
        return history
    trimmed: list[dict] = []
    total = 0
    for item in reversed(history):
        content = item.get("content") or ""
        if not content:
            continue
        if total + len(content) > max_chars and trimmed:
            break
        trimmed.append(item)
        total += len(content)
    return list(reversed(trimmed))


def _fetch_agent_history(client, friend_id: str, trace_id: Optional[str] = None) -> list[dict]:
    if not friend_id or not env_bool("GONGAN_AGENT_HISTORY_ENABLED", True):
        return []

    rows = _env_int("GONGAN_AGENT_HISTORY_ROWS", 1, minimum=0)
    if rows <= 0:
        return []

    max_chars = _env_int("GONGAN_AGENT_HISTORY_MAX_CHARS", 2000, minimum=0)
    timeout = env_float("GONGAN_AGENT_HISTORY_TIMEOUT", min(client.timeout, 3.0))
    payload = {
        "askEndTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "friendId": friend_id,
        "page": 1,
        "row": rows,
    }
    start = now()
    try:
        response = client.session.post(
            f"{client.base_url}/agentService/agentChat/getChatInfo",
            json=payload,
            headers=client.token_header(),
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("status") != "success":
            logger.warning(
                f"Gongan agent history query failed trace_id={trace_id}: {data}"
            )
            return []

        result = data.get("result", {})
        items = result.get("items") if isinstance(result, dict) else result
        if not isinstance(items, list):
            return []

        items = [item for item in items if isinstance(item, dict)]
        items = sorted(items, key=lambda item: item.get("createTime", ""))
        history: list[dict] = []
        for item in items:
            ask = (item.get("ask") or "").strip()
            reply = (item.get("reply") or "").strip()
            if ask:
                history.append({"role": "user", "content": ask})
            if reply:
                history.append({"role": "assistant", "content": reply})

        history = _trim_history(history, max_chars)
        logger.info(
            f"Gongan agent history loaded trace_id={trace_id}, "
            f"rows={rows}, messages={len(history)}, chars={sum(len(i['content']) for i in history)}"
        )
        log_perf(
            "llm",
            "agent_history_loaded",
            elapsed_ms(start),
            trace_id=trace_id,
            rows=rows,
            messages=len(history),
            chars=sum(len(i["content"]) for i in history),
        )
        return history
    except Exception as exc:
        logger.warning(f"Gongan agent history unavailable trace_id={trace_id}: {exc}")
        return []


def _build_agent_payload(message: str, model_id: str, client=None, trace_id: Optional[str] = None) -> dict:
    friend_id = os.environ.get("GONGAN_AGENT_FRIEND_ID", "").strip()
    agent_id = os.environ.get("GONGAN_AGENT_ID", "").strip()
    if not friend_id and not agent_id:
        raise RuntimeError(
            "Gongan agent chat requires GONGAN_AGENT_FRIEND_ID or GONGAN_AGENT_ID."
        )

    payload = {
        "modelId": model_id,
        "history": _fetch_agent_history(client, friend_id, trace_id) if client else [],
        "query": _build_query(message),
        "stream": True,
        "startFlag": 0,
        "useTmp": 0,
        "exact_match": env_bool("GONGAN_AGENT_EXACT_MATCH", False),
        "file_names": [],
        "isBoot": os.environ.get("GONGAN_AGENT_IS_BOOT", "1"),
    }
    if friend_id:
        payload["friendId"] = friend_id
    else:
        payload["agentId"] = agent_id

    process_id = os.environ.get("GONGAN_AGENT_PROCESS_ID", "").strip()
    if process_id:
        # The upstream document spells this field as "prrocessId".
        payload["prrocessId"] = process_id
    return payload


def _make_tts_sender(
    nerfreal: BaseReal,
    trace_id: Optional[str] = None,
) -> tuple[Callable[[str], None], Callable[[], None]]:
    tts = getattr(nerfreal, "tts", None)
    can_direct_tts = bool(
        env_bool("GONGAN_DIRECT_TTS", True)
        and hasattr(tts, "start_text_stream")
    )
    direct_queue: queue.Queue[tuple[int, str] | None] = queue.Queue()
    direct_done = Event()
    segment_index = 0

    def _is_active() -> bool:
        is_active = getattr(nerfreal, "is_active_chat_trace", None)
        return not (trace_id and callable(is_active) and not is_active(trace_id))

    def _clear_active_tts_trace() -> None:
        if hasattr(nerfreal, "clear_active_tts_trace"):
            nerfreal.clear_active_tts_trace()

    def _fallback_to_queue(clean_text: str, index: int) -> None:
        nerfreal.put_msg_txt(
            clean_text,
            trace_id=trace_id,
            segment_index=index,
        )

    def _direct_text_parts(clean_text: str) -> list[str]:
        splitter = getattr(tts, "_split_tts_text", None)
        if not callable(splitter):
            return [clean_text]
        try:
            parts = [part for part in splitter(clean_text) if part.strip()]
            return parts or [clean_text]
        except Exception as exc:
            logger.warning(
                f"Gongan direct TTS split failed trace_id={trace_id}, "
                f"len={len(clean_text)}: {exc}"
            )
            return [clean_text]

    def _run_direct_tts_segments() -> None:
        try:
            while True:
                item = direct_queue.get()
                if item is None:
                    return
                index, clean_text = item
                if not _is_active():
                    logger.info(
                        f"Skip stale direct Gongan TTS segment trace_id={trace_id}, "
                        f"segment_index={index}, len={len(clean_text)}"
                    )
                    continue

                parts = _direct_text_parts(clean_text)
                for part_index, part_text in enumerate(parts, start=1):
                    if not _is_active():
                        break
                    stream = None
                    try:
                        if hasattr(nerfreal, "set_active_tts_trace"):
                            nerfreal.set_active_tts_trace(trace_id, index)
                        stream_start = now()
                        stream = tts.start_text_stream()
                        logger.info(
                            f"Gongan LLM direct TTS segment stream started "
                            f"trace_id={trace_id}, segment_index={index}, "
                            f"part_index={part_index}/{len(parts)}, len={len(part_text)}"
                        )
                        log_perf(
                            "tts",
                            "direct_stream_start",
                            elapsed_ms(stream_start),
                            trace_id=trace_id,
                            segment_index=index,
                            part_index=part_index,
                            part_count=len(parts),
                            direct_tts=True,
                            per_segment=True,
                        )
                        stream.send_text(part_text)
                        stream.finish()
                        diagnostics = (
                            stream.diagnostics()
                            if hasattr(stream, "diagnostics")
                            else {}
                        )
                        log_perf(
                            "tts",
                            "direct_segment_stream_done",
                            trace_id=trace_id,
                            segment_index=index,
                            part_index=part_index,
                            part_count=len(parts),
                            text_len=len(part_text),
                            segments_sent=diagnostics.get("segments_sent"),
                            segments_done=diagnostics.get("segments_done"),
                            audio_packets=diagnostics.get("audio_packets"),
                            audio_bytes=diagnostics.get("audio_bytes"),
                            finish_wait_timed_out=diagnostics.get("finish_wait_timed_out"),
                        )
                    except Exception as exc:
                        logger.warning(
                            f"Gongan direct TTS segment failed, fallback to queue "
                            f"trace_id={trace_id}, segment_index={index}, "
                            f"part_index={part_index}: {exc}"
                        )
                        try:
                            if stream is not None and hasattr(stream, "abort"):
                                stream.abort()
                        except Exception:
                            pass
                        _fallback_to_queue(part_text, index)
                    finally:
                        _clear_active_tts_trace()
        finally:
            direct_done.set()

    worker = None
    if can_direct_tts:
        worker = Thread(
            target=_run_direct_tts_segments,
            name=f"gongan-tts-{trace_id or 'stream'}",
            daemon=True,
        )
        worker.start()

    def send(text: str) -> None:
        nonlocal segment_index
        clean_text = text.strip()
        if not clean_text:
            return
        segment_index += 1
        if not _is_active():
            logger.info(
                f"Skip stale Gongan TTS segment trace_id={trace_id}, "
                f"segment_index={segment_index}, len={len(clean_text)}"
            )
            return
        log_timepoint(
            "TTS",
            "LLM文本段进入TTS",
            trace_id=trace_id,
            segment_index=segment_index,
            text_len=len(clean_text),
            direct_tts=can_direct_tts,
            first_char=clean_text[:1],
        )
        log_perf(
            "trace",
            "tts_segment_dispatch",
            trace_id=trace_id,
            segment_index=segment_index,
            text_len=len(clean_text),
            direct_tts=can_direct_tts,
        )
        if can_direct_tts and worker is not None and not direct_done.is_set():
            direct_queue.put((segment_index, clean_text))
        else:
            _fallback_to_queue(clean_text, segment_index)

    def finish() -> None:
        if can_direct_tts and worker is not None:
            direct_queue.put(None)
            finish_timeout = float(
                getattr(tts, "_finish_timeout", env_float("GONGAN_TTS_FINISH_TIMEOUT", 20.0))
            )
            segment_timeout = float(
                getattr(tts, "_segment_timeout", env_float("GONGAN_TTS_SEGMENT_TIMEOUT", 20.0))
            )
            timeout = max(5.0, (finish_timeout + segment_timeout + 2.0) * max(1, segment_index))
            if not direct_done.wait(timeout=timeout):
                logger.warning(
                    f"Gongan direct TTS worker finish timed out trace_id={trace_id}, "
                    f"segments={segment_index}, timeout={timeout:.1f}s"
                )
        _clear_active_tts_trace()

    return send, finish


def llm_response(
    message: str,
    nerfreal: BaseReal,
    sessionid: str,
    result_queue: asyncio.Queue,
    trace_id: Optional[str] = None,
) -> str:
    start_time = time.perf_counter()
    first_token_received = False
    msg_id = trace_id or str(uuid.uuid4())
    trace_id = msg_id
    client = get_gongan_client()
    complete_response: list[str] = []
    tts_buffer = ""
    chunk_count = 0
    tts_segments_queued = 0
    response = None
    min_segment_len = int(os.environ.get("GONGAN_TTS_MIN_SEGMENT_LEN", "12"))
    max_segment_len = int(os.environ.get("GONGAN_TTS_MAX_SEGMENT_LEN", "80"))
    read_timeout = env_float("GONGAN_LLM_READ_TIMEOUT", 60.0)
    send_tts, finish_tts = _make_tts_sender(nerfreal, trace_id=trace_id)

    def queue_tts(text: str) -> None:
        nonlocal tts_segments_queued
        tts_segments_queued += 1
        logger.info(
            f"Gongan TTS segment queued trace_id={msg_id}, "
            f"segment_index={tts_segments_queued}, text={text[:30]!r}, len={len(text)}"
        )
        log_perf(
            "llm",
            "queue_tts_segment",
            trace_id=msg_id,
            segment_index=tts_segments_queued,
            text_len=len(text),
            total_answer_len=sum(len(part) for part in complete_response),
        )
        send_tts(text)

    try:
        use_agent = _use_agent_chat()
        if use_agent:
            client.ensure_login()
            url = f"{client.base_url}/agentService/agentChat/query"
            payload = _build_agent_payload(
                message,
                client.ensure_model_id(),
                client=client,
                trace_id=msg_id,
            )
        else:
            client.ensure_ready()
            url = f"{client.base_url}/aichat/chat/query"
            payload = {
                "query": _build_query(message),
                "history": [],
                "stream": True,
                "startFlag": 0,
                "groupId": None,
                "useTmp": 0,
                "kb_ids": [],
                "file_names": [],
                "is_only_specialized": False,
                "modelId": client.ensure_model_id(),
                "isBoot": "1",
            }

        logger.info(
            f"Start receiving Gongan LLM stream trace_id={msg_id}, "
            f"sessionid={sessionid}, text_len={len(message)}, "
            f"read_timeout={read_timeout}, agent_chat={use_agent}"
        )
        log_timepoint(
            "LLM",
            "请求公安大模型",
            trace_id=msg_id,
            sessionid=sessionid,
            text_len=len(message),
            model=payload.get("modelId"),
            agent_chat=use_agent,
        )
        post_start = now()
        response = client.session.post(
            url,
            json=payload,
            headers=client.sse_headers(),
            stream=True,
            timeout=(client.timeout, read_timeout),
        )
        log_perf(
            "llm",
            "http_post",
            elapsed_ms(post_start),
            trace_id=msg_id,
            sessionid=sessionid,
            status_code=getattr(response, "status_code", None),
        )
        header_start = now()
        response.raise_for_status()
        log_perf(
            "llm",
            "http_headers_ready",
            elapsed_ms(header_start),
            trace_id=msg_id,
            sessionid=sessionid,
            status_code=getattr(response, "status_code", None),
        )

        for raw_line in response.iter_lines(decode_unicode=True):
            is_active = getattr(nerfreal, "is_active_chat_trace", None)
            if trace_id and callable(is_active) and not is_active(trace_id):
                logger.info(
                    f"停止处理已失效的公安LLM响应 trace_id={trace_id}, "
                    f"chunks={chunk_count}, answer_len={sum(len(part) for part in complete_response)}"
                )
                return None
            if not raw_line:
                continue
            if isinstance(raw_line, bytes):
                raw_line = raw_line.decode("utf-8", errors="ignore")
            line = raw_line.strip()
            if line.startswith(("event:", "id:", "retry:")):
                continue
            if line.startswith("data:"):
                line = line[5:].strip()
            if not line or line == "[DONE]":
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                logger.debug(f"Gongan LLM ignored non-JSON SSE line: {line[:120]!r}")
                continue

            chunk = _clean_chunk(_extract_answer(data))
            if not chunk:
                continue

            if not first_token_received:
                first_token_received = True
                first_token_ms = (time.perf_counter() - start_time) * 1000
                logger.info(
                    f"Gongan LLM first token trace_id={msg_id}: "
                    f"{first_token_ms / 1000:.2f}s"
                )
                log_timepoint(
                    "LLM",
                    "流式首token输出",
                    trace_id=msg_id,
                    sessionid=sessionid,
                    first_chunk_len=len(chunk),
                )
                log_perf(
                    "trace",
                    "llm_first_token",
                    first_token_ms,
                    trace_id=msg_id,
                    sessionid=sessionid,
                    first_chunk_len=len(chunk),
                )

            chunk_count += 1
            result_queue.put_nowait(
                {
                    "data": chunk,
                    "id": msg_id,
                    "trace_id": msg_id,
                    "finish": False,
                    "_perf_enqueued_mono": now(),
                }
            )
            complete_response.append(chunk)

            tts_buffer += chunk
            punct_pos = _find_last_punct(tts_buffer)
            if punct_pos >= 0 and (punct_pos >= min_segment_len or len(tts_buffer) >= 30):
                queue_tts(tts_buffer[: punct_pos + 1])
                tts_buffer = tts_buffer[punct_pos + 1 :]
            elif len(tts_buffer) >= max_segment_len:
                queue_tts(tts_buffer)
                tts_buffer = ""

        if tts_buffer.strip():
            queue_tts(tts_buffer)

        result_queue.put_nowait(
            {
                "data": "",
                "id": msg_id,
                "trace_id": msg_id,
                "finish": True,
                "_perf_enqueued_mono": now(),
            }
        )
        total_ms = (time.perf_counter() - start_time) * 1000
        answer_len = sum(len(part) for part in complete_response)
        logger.info(
            f"Gongan LLM total time trace_id={msg_id}: {total_ms / 1000:.2f}s, "
            f"chunks={chunk_count}, answer_len={answer_len}, tts_segments={tts_segments_queued}"
        )
        log_perf(
            "llm",
            "stream_done",
            total_ms,
            trace_id=msg_id,
            sessionid=sessionid,
            chunks=chunk_count,
            answer_len=answer_len,
            tts_segments=tts_segments_queued,
        )
        log_perf(
            "trace",
            "llm_done",
            total_ms,
            trace_id=msg_id,
            sessionid=sessionid,
            chunks=chunk_count,
            answer_len=answer_len,
            tts_segments=tts_segments_queued,
        )
        return "".join(complete_response)

    except Exception as exc:
        logger.exception(f"Gongan LLM error trace_id={msg_id}: {exc}")
        result_queue.put_nowait(
            {
                "data": "",
                "id": msg_id,
                "trace_id": msg_id,
                "finish": True,
                "_perf_enqueued_mono": now(),
            }
        )
        return None
    finally:
        try:
            finish_start = now()
            finish_tts()
            log_perf(
                "tts",
                "finish_after_llm",
                elapsed_ms(finish_start),
                trace_id=msg_id,
                sessionid=sessionid,
                llm_chunks=chunk_count,
                tts_segments=tts_segments_queued,
            )
        except Exception as exc:
            logger.warning(f"Gongan TTS finish error trace_id={msg_id}: {exc}")
        finally:
            try:
                if response is not None:
                    response.close()
            except Exception:
                pass
