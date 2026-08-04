import base64
import hashlib
import hmac
import json
from email.utils import formatdate
from urllib.parse import urlencode

import websockets
from loguru import logger

from asr.base import BaseASRProvider

IAT_URL = "wss://iat-api.xfyun.cn/v2/iat"


class IflyTekASRProvider(BaseASRProvider):
    def __init__(self, app_id: str, api_key: str, api_secret: str):
        self._app_id = app_id
        self._api_key = api_key
        self._api_secret = api_secret
        self._ws = None

    def _build_auth_url(self) -> str:
        date = formatdate(usegmt=True)
        sign_origin = (
            f"host: iat-api.xfyun.cn\ndate: {date}\nGET /v2/iat HTTP/1.1"
        )
        signature = base64.b64encode(
            hmac.new(
                self._api_secret.encode("utf-8"),
                sign_origin.encode("utf-8"),
                digestmod=hashlib.sha256,
            ).digest()
        ).decode()
        authorization_origin = (
            f'api_key="{self._api_key}", algorithm="hmac-sha256", '
            f'headers="host date request-line", signature="{signature}"'
        )
        authorization = base64.b64encode(
            authorization_origin.encode("utf-8")
        ).decode()
        params = {
            "authorization": authorization,
            "date": date,
            "host": "iat-api.xfyun.cn",
        }
        return f"{IAT_URL}?{urlencode(params)}"

    async def start_session(self) -> None:
        url = self._build_auth_url()
        self._ws = await websockets.connect(url)
        init_frame = {
            "common": {"app_id": self._app_id},
            "business": {
                "language": "zh_cn",
                "domain": "iat",
                "accent": "mandarin",
                "vad_eos": 10000,
                "dwa": "wpgs",
            },
            "data": {
                "status": 0,
                "format": "audio/L16;rate=16000",
                "encoding": "raw",
                "audio": "",
            },
        }
        await self._ws.send(json.dumps(init_frame))
        logger.info("iFlyTek ASR session started")

    async def send_audio(self, pcm: bytes) -> None:
        if not self._ws:
            return
        frame = {
            "data": {
                "status": 1,
                "format": "audio/L16;rate=16000",
                "encoding": "raw",
                "audio": base64.b64encode(pcm).decode(),
            }
        }
        await self._ws.send(json.dumps(frame))

    async def end_session(self) -> str:
        if not self._ws:
            return ""
        end_frame = {"data": {"status": 2, "audio": ""}}
        await self._ws.send(json.dumps(end_frame))
        parts = []
        async for raw in self._ws:
            data = json.loads(raw)
            result = data.get("data", {}).get("result")
            if result:
                parts.append(self._extract_text(result))
            if data.get("data", {}).get("status") == 2:
                break
        text = "".join(parts)
        logger.info(f"iFlyTek ASR result: {text!r}")
        return text

    def _extract_text(self, result: dict) -> str:
        words = []
        for ws_item in result.get("ws", []):
            for cw in ws_item.get("cw", []):
                words.append(cw.get("w", ""))
        return "".join(words)

    async def close(self) -> None:
        if self._ws:
            await self._ws.close()
            self._ws = None
