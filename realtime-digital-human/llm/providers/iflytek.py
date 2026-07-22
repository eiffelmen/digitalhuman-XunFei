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

import numpy as np
import websocket
from loguru import logger

from basereal import BaseReal


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return max(0, min(100, int(value)))
    except ValueError:
        logger.warning(f"Invalid {name}={value!r}; using {default}")
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _stream_pcm_to_nerfreal(nerfreal, chunks: list[bytes]) -> None:
    """将 AIUI v3 返回的 raw int16 PCM 块直接送入渲染管线。"""
    chunk_size = nerfreal.chunk
    for raw in chunks:
        if not raw:
            continue
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32767.0
        idx = 0
        while idx + chunk_size <= len(samples):
            nerfreal.put_audio_frame(samples[idx:idx + chunk_size])
            idx += chunk_size


def _find_last_punct(text: str) -> int:
    last_punct = -1
    for p in ",.!;:，。！？：；":
        pos = text.rfind(p)
        if pos > last_punct:
            last_punct = pos
    return last_punct


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
    appid: str,
    sn: str,
    scene: str,
    vcn: str,
    message: str,
    stmid: str,
    speed: int,
    volume: int,
    pitch: int,
    enable_tts_audio: bool,
) -> str:
    # 对齐讯飞 AIUI V3 文本 one-shot 请求格式
    parameter = {
        "nlp": {
            "nlp": {"compress": "raw", "format": "json", "encoding": "utf8"},
            "new_session": True,
        },
    }
    if enable_tts_audio:
        parameter["tts"] = {
            "vcn": vcn,
            "speed": speed,
            "volume": volume,
            "pitch": pitch,
            "tts": {
                "channels": 1,
                "bit_depth": 16,
                "sample_rate": 16000,
                "encoding": "raw",
            },
        }

    payload = {
        "header": {
            "appid": appid,
            "sn": sn,
            "stmid": stmid,
            "status": 3,
            "scene": scene,
            "interact_mode": "oneshot",
        },
        "parameter": parameter,
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
    message: str, nerfreal: BaseReal, sessionid: str, result_queue: asyncio.Queue
) -> str:
    start_time = time.perf_counter()
    first_token_received = False
    msg_id = str(uuid.uuid4())

    ws_url = os.environ.get("IFLYTEK_WS_URL", "wss://aiui.xf-yun.com/v3/aiint/sos")
    appid = os.environ.get("IFLYTEK_APPID", "")
    api_key = os.environ.get("IFLYTEK_API_KEY", "")
    api_secret = os.environ.get("IFLYTEK_API_SECRET", "")
    sn = os.environ.get("IFLYTEK_SN", "").strip()
    scene = os.environ.get("IFLYTEK_SCENE", "main_box")
    vcn = os.environ.get("IFLYTEK_VCN", "x5_lingyuzhao_flow")
    speed = _env_int("IFLYTEK_TTS_SPEED", 45)
    volume = _env_int("IFLYTEK_TTS_VOLUME", 55)
    pitch = _env_int("IFLYTEK_TTS_PITCH", 48)
    timeout = int(os.environ.get("IFLYTEK_TIMEOUT", "30"))
    enable_tts_audio = _env_bool("IFLYTEK_AIUI_V3_TTS_AUDIO", False)
    incremental_tts = _env_bool("IFLYTEK_INCREMENTAL_TTS", True)
    reply_instruction = os.environ.get(
        "IFLYTEK_REPLY_INSTRUCTION",
        "请用简洁、口语化中文回答，控制在80字以内，适合数字人口播。",
    ).strip()
    request_message = (
        f"{reply_instruction}\n用户问题：{message}" if reply_instruction else message
    )

    if not appid or not api_key or not api_secret or not sn:
        logger.error(
            "讯飞LLM配置缺失，请在 .env 中设置 "
            "IFLYTEK_SN / IFLYTEK_APPID / IFLYTEK_API_KEY / IFLYTEK_API_SECRET"
        )
        result_queue.put_nowait({"data": "", "id": msg_id, "finish": True})
        return None

    ws = None
    complete_response = []
    seen_nlp_seq = set()

    try:
        auth_url = _build_auth_url(ws_url, api_key, api_secret)
        ws = websocket.create_connection(auth_url, timeout=timeout)
        stmid = f"text-{msg_id}"

        req_data = _build_text_request(
            appid=appid,
            sn=sn,
            scene=scene,
            vcn=vcn,
            message=request_message,
            stmid=stmid,
            speed=speed,
            volume=volume,
            pitch=pitch,
            enable_tts_audio=enable_tts_audio,
        )
        ws.send(req_data)
        logger.info("开始接收讯飞AIUI流式响应")

        tts_audio_chunks = []
        queued_tts_text = False
        tts_text_buffer = ""

        def _queue_tts_text(text: str) -> None:
            nonlocal queued_tts_text
            text = text.strip()
            if not text:
                return
            queued_tts_text = True
            logger.info(f"增量TTS入队: {text[:30]!r}, len={len(text)}")
            nerfreal.put_msg_txt(text)

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

                        result_queue.put_nowait(
                            {"data": chunk, "id": msg_id, "finish": False}
                        )
                        complete_response.append(chunk)

                        if incremental_tts and not enable_tts_audio:
                            tts_text_buffer += chunk
                            punct_pos = _find_last_punct(tts_text_buffer)
                            if punct_pos >= 0 and (punct_pos >= 7 or len(tts_text_buffer) >= 30):
                                _queue_tts_text(tts_text_buffer[: punct_pos + 1])
                                tts_text_buffer = tts_text_buffer[punct_pos + 1 :]
                            elif len(tts_text_buffer) >= 80:
                                _queue_tts_text(tts_text_buffer)
                                tts_text_buffer = ""

            if "tts" in payload:
                tts_data = payload["tts"]
                audio_b64 = tts_data.get("audio")
                if audio_b64:
                    tts_audio_chunks.append(base64.b64decode(audio_b64))

            if header.get("status") == 2:
                break

        if tts_audio_chunks and not queued_tts_text:
            logger.info(f"使用AIUI v3 TTS音频直接播放，共 {len(tts_audio_chunks)} 个块")
            _stream_pcm_to_nerfreal(nerfreal, tts_audio_chunks)
        elif incremental_tts and not enable_tts_audio:
            _queue_tts_text(tts_text_buffer)
        elif complete_response:
            nerfreal.put_msg_txt("".join(complete_response))

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
