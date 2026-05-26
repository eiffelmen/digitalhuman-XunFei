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

import websocket
from loguru import logger

from basereal import BaseReal


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
    message: str, nerfreal: BaseReal, sessionid: str, result_queue: asyncio.Queue
) -> str:
    start_time = time.perf_counter()
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
    buffer = []
    complete_response = []
    seen_nlp_seq = set()

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

                        result_queue.put_nowait(
                            {"data": chunk, "id": msg_id, "finish": False}
                        )
                        complete_response.append(chunk)
                        buffer.append(chunk)

                        if len("".join(buffer)) >= 20:
                            text = "".join(buffer)
                            last_punct = _find_last_punct(text)
                            if last_punct != -1:
                                output_text = text[: last_punct + 1]
                                nerfreal.put_msg_txt(output_text)
                                buffer = [text[last_punct + 1 :]]

            if header.get("status") == 2:
                break

        if buffer:
            final_text = "".join(buffer)
            if final_text.strip():
                nerfreal.put_msg_txt(final_text)

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
