import os
import time
import uuid
import hmac
import json
import base64
import hashlib
import asyncio
from datetime import datetime
from urllib.parse import urlparse, urlencode
from time import mktime
from wsgiref.handlers import format_date_time
from typing import Optional

import websocket
from loguru import logger

from basereal import BaseReal
from perf_logger import elapsed_ms, log_perf, now


def _find_last_punct(text: str) -> int:
    last_punct = -1
    for p in ",.!;:，。！？：；":
        pos = text.rfind(p)
        if pos > last_punct:
            last_punct = pos
    return last_punct


def _env_bool(name: str, default: bool = True) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() not in {"0", "false", "no", "off"}


def _env_int(name: str, default: int, min_value: int = 1) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return max(min_value, int(value))
    except ValueError:
        logger.warning(f"Invalid {name}={value!r}; using {default}")
        return default


class StreamingTTSDispatcher:
    sentence_punct = "。！？!?"
    soft_punct = "，,；;：:、"

    def __init__(self, nerfreal: BaseReal, trace_id: Optional[str]):
        self.nerfreal = nerfreal
        self.trace_id = trace_id
        self.enabled = _env_bool("LLM_STREAM_TTS_ENABLED", True)
        self.first_chars = _env_int("LLM_STREAM_TTS_FIRST_CHARS", 10)
        self.min_chars = _env_int("LLM_STREAM_TTS_MIN_CHARS", 10)
        self.max_chars = _env_int("LLM_STREAM_TTS_MAX_CHARS", 24)
        self.buffer = ""
        self.segment_index = 0
        self.start = now()
        self.first_dispatched = False

    def append(self, chunk: str):
        self.buffer += chunk
        if self.enabled:
            self._flush_ready(final=False)

    def finish(self):
        self._flush_ready(final=True)

    def _flush_ready(self, final: bool):
        while True:
            segment, reason = self._next_segment(final)
            if not segment:
                return
            self._dispatch(segment, reason)
            if final:
                continue

    def _next_segment(self, final: bool):
        text = self.buffer
        if not text.strip():
            self.buffer = ""
            return None, None

        if final:
            self.buffer = ""
            return text, "final"

        split_at = self._find_split(text)
        if split_at is not None:
            segment = text[:split_at]
            self.buffer = text[split_at:]
            return segment, "punct"

        if not self.first_dispatched and len(text.strip()) >= self.first_chars:
            segment = text[:self.max_chars]
            self.buffer = text[self.max_chars:]
            return segment, "first_fast"

        if len(text.strip()) >= self.max_chars:
            segment = text[:self.max_chars]
            self.buffer = text[self.max_chars:]
            return segment, "max_chars"

        return None, None

    def _find_split(self, text: str):
        sentence_pos = max([text.rfind(p) for p in self.sentence_punct] or [-1])
        if sentence_pos != -1 and len(text[: sentence_pos + 1].strip()) >= self.min_chars:
            return sentence_pos + 1

        soft_pos = max([text.rfind(p) for p in self.soft_punct] or [-1])
        if soft_pos != -1 and len(text[: soft_pos + 1].strip()) >= self.min_chars:
            return soft_pos + 1

        return None

    def _dispatch(self, text: str, reason: str):
        text = text.strip()
        if not text:
            return
        self.segment_index += 1
        self.first_dispatched = True
        self.nerfreal.put_msg_txt(
            text,
            trace_id=self.trace_id,
            segment_index=self.segment_index,
        )
        log_perf(
            "trace",
            "llm_segment_to_tts",
            elapsed_ms(self.start),
            trace_id=self.trace_id,
            segment_index=self.segment_index,
            reason=reason,
            text_len=len(text),
        )


def _build_auth_url(base_url: str, api_key: str, api_secret: str) -> str:
    host = urlparse(base_url).netloc
    path = urlparse(base_url).path
    date = format_date_time(mktime(datetime.now().timetuple()))

    signature_origin = f"host: {host}\n" f"date: {date}\n" f"GET {path} HTTP/1.1"
    signature_sha = hmac.new(
        api_secret.encode("utf-8"),
        signature_origin.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    signature_sha_base64 = base64.b64encode(signature_sha).decode("utf-8")

    authorization_origin = (
        f'api_key="{api_key}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{signature_sha_base64}"'
    )
    authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode(
        "utf-8"
    )

    params = {"host": host, "date": date, "authorization": authorization}
    return f"{base_url}?{urlencode(params)}"


def _build_text_request(
    appid: str, sn: str, scene: str, vcn: str, message: str, stmid: str
) -> str:
    # 对齐讯飞 AIUI V3 文本 one-shot 请求格式
    payload = {
        "header": {
            "appid": appid,
            "sn": sn,
            "stmid": stmid,
            "status": 3,
            "scene": scene,
            "interact_mode": "oneshot",
        },
        "parameter": {
            "nlp": {
                "nlp": {"compress": "raw", "format": "json", "encoding": "utf8"},
                "new_session": True,
            },
            "tts": {
                "vcn": vcn,
                "tts": {
                    "channels": 1,
                    "bit_depth": 16,
                    "sample_rate": 16000,
                    "encoding": "raw",
                },
            },
        },
        "payload": {
            "text": {
                "compress": "raw",
                "format": "plain",
                "text": base64.b64encode(message.encode("utf-8")).decode("utf-8"),
                "encoding": "utf8",
                "status": 3,
            }
        },
    }
    return json.dumps(payload, ensure_ascii=False)


def llm_response(
    message: str,
    nerfreal: BaseReal,
    sessionid: str,
    result_queue: asyncio.Queue,
    trace_id: Optional[str] = None,
) -> str:
    start_time = time.perf_counter()
    perf_start = now()
    first_token_received = False
    msg_id = str(uuid.uuid4())

    ws_url = os.environ.get("IFLYTEK_WS_URL", "wss://aiui.xf-yun.com/v3/aiint/sos")
    appid = os.environ.get("IFLYTEK_APPID", "")
    api_key = os.environ.get("IFLYTEK_API_KEY", "")
    api_secret = os.environ.get("IFLYTEK_API_SECRET", "")
    scene = os.environ.get("IFLYTEK_SCENE", "main_box")
    vcn = os.environ.get("IFLYTEK_VCN", "x5_lingxiaoyue_flow")
    timeout = int(os.environ.get("IFLYTEK_TIMEOUT", "30"))

    if not appid or not api_key or not api_secret:
        logger.error("讯飞LLM配置缺失，请设置 IFLYTEK_APPID / IFLYTEK_API_KEY / IFLYTEK_API_SECRET")
        result_queue.put_nowait({"data": "", "id": msg_id, "finish": True})
        return None

    ws = None
    complete_response = []
    seen_nlp_seq = set()
    tts_dispatcher = StreamingTTSDispatcher(nerfreal, trace_id)

    try:
        auth_url = _build_auth_url(ws_url, api_key, api_secret)
        ws = websocket.create_connection(auth_url, timeout=timeout)
        sn = os.environ.get("IFLYTEK_SN", f"{sessionid or 'session'}-{msg_id}")
        stmid = f"text-{msg_id}"

        req_data = _build_text_request(
            appid=appid, sn=sn, scene=scene, vcn=vcn, message=message, stmid=stmid
        )
        ws.send(req_data)
        logger.info("开始接收讯飞AIUI流式响应")

        while True:
            raw = ws.recv()
            if not raw:
                continue

            data = json.loads(raw)
            header = data.get("header", {})
            code = header.get("code", -1)
            if code != 0:
                logger.error(f"讯飞AIUI返回错误 code={code}, message={raw}")
                break

            payload = data.get("payload", {})

            if "nlp" in payload:
                nlp_json = payload["nlp"]
                seq = nlp_json.get("seq")
                if seq in seen_nlp_seq:
                    if header.get("status") == 2:
                        break
                    continue
                seen_nlp_seq.add(seq)

                text_bs64 = nlp_json.get("text")
                if text_bs64:
                    nlp_text = base64.b64decode(text_bs64).decode("utf-8")
                    chunk = nlp_text.translate(str.maketrans("", "", "*#-"))
                    if chunk:
                        if not first_token_received:
                            first_token_received = True
                            logger.info(
                                f"讯飞LLM首次响应耗时: {time.perf_counter() - start_time:.2f}s"
                            )
                            log_perf(
                                "trace",
                                "llm_first_token",
                                elapsed_ms(perf_start),
                                trace_id=trace_id,
                                sessionid=sessionid,
                                chunk_len=len(chunk),
                            )

                        result_queue.put_nowait(
                            {"data": chunk, "id": msg_id, "finish": False}
                        )
                        complete_response.append(chunk)
                        tts_dispatcher.append(chunk)

            if header.get("status") == 2:
                break

        tts_dispatcher.finish()

        result_queue.put_nowait({"data": "", "id": msg_id, "finish": True})
        logger.info(f"讯飞LLM总响应耗时: {time.perf_counter() - start_time:.2f}s")
        return "".join(complete_response)

    except Exception as e:
        logger.error(f"讯飞LLM处理异常: {str(e)}")
        result_queue.put_nowait({"data": "", "id": msg_id, "finish": True})
        return None
    finally:
        try:
            if ws is not None:
                ws.close()
        except Exception:
            pass
