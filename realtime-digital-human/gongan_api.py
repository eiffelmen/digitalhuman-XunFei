import os
import threading
from typing import Any

import requests
from loguru import logger


DEFAULT_BASE_URL = "https://jywt.com.cn/ga/api"
DEFAULT_TTS_WS_URL = "wss://jywt.com.cn/ga/api/audio/paddlespeech/tts/streaming"
DEFAULT_ASR_WS_URL = "wss://jywt.com.cn/ga/api/audio/paddlespeech/asr/streaming"
DEFAULT_ORIGIN = "https://jywt.com.cn"


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        logger.warning(f"Invalid {name}={value!r}; using {default}")
        return default


class GonganAPIClient:
    def __init__(self) -> None:
        self.base_url = os.environ.get(
            "GONGAN_API_BASE_URL", os.environ.get("BASE_URL", DEFAULT_BASE_URL)
        ).rstrip("/")
        self.tts_ws_url = os.environ.get("GONGAN_TTS_WS_URL", DEFAULT_TTS_WS_URL)
        self.asr_ws_url = os.environ.get("GONGAN_ASR_WS_URL", DEFAULT_ASR_WS_URL)
        self.origin = os.environ.get("GONGAN_API_ORIGIN", DEFAULT_ORIGIN)
        self.api_token = os.environ.get(
            "GONGAN_API_TOKEN", os.environ.get("API_KEY", "")
        )
        self.username = os.environ.get(
            "GONGAN_API_USERNAME", os.environ.get("GONGAN_USERNAME", "")
        )
        self.pwd_md5 = os.environ.get(
            "GONGAN_API_PWD_MD5", os.environ.get("GONGAN_PWD_MD5", "")
        )
        self.model_name = os.environ.get("GONGAN_MODEL_NAME", "qwen3-14b")
        self.model_id = (
            os.environ.get("GONGAN_MODEL_ID")
            or os.environ.get("GONGAN_AGENT_MODEL_ID")
            or None
        )
        generic_model_name = os.environ.get("MODEL_NAME")
        if not self.model_id and generic_model_name and generic_model_name.isdigit():
            self.model_id = generic_model_name
        elif generic_model_name:
            self.model_name = generic_model_name
        self.timeout = env_float("GONGAN_API_TIMEOUT", 10.0)
        self.session = requests.Session()
        self.session_id: str | None = None
        self._lock = threading.RLock()

    def ensure_login(self, force: bool = False) -> str:
        with self._lock:
            if self.api_token:
                self.session_id = self.api_token
                return self.api_token

            if self.session_id and not force:
                return self.session_id

            if not self.username or not self.pwd_md5:
                raise RuntimeError(
                    "Missing Gongan API credentials. Set GONGAN_API_TOKEN/API_KEY, "
                    "or set GONGAN_API_USERNAME and GONGAN_API_PWD_MD5."
                )

            url = f"{self.base_url}/systemMgr/systemMgr/login"
            response = self.session.post(
                url,
                json={"username": self.username, "pwd": self.pwd_md5},
                headers={"Content-Type": "application/json;charset=UTF-8"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            if data.get("status") != "success":
                raise RuntimeError(f"Gongan API login failed: {data}")

            session_id = data.get("result", {}).get("sessionId")
            if not session_id:
                raise RuntimeError("Gongan API login did not return sessionId")

            self.session_id = session_id
            logger.info("Gongan API login OK")
            return session_id

    def ensure_model_id(self, force: bool = False) -> str:
        with self._lock:
            if self.model_id and not force:
                return self.model_id

            if self.api_token:
                raise RuntimeError(
                    "Missing Gongan model id. Set GONGAN_MODEL_ID, "
                    "GONGAN_AGENT_MODEL_ID, or numeric MODEL_NAME."
                )

            session_id = self.ensure_login()
            url = f"{self.base_url}/model-service/llmModel/myListPage"
            response = self.session.get(
                url,
                params={"page": 1, "row": -1, "enable": 1},
                headers={"x-token-key": session_id},
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            if data.get("status") != "success":
                raise RuntimeError(f"Gongan model list failed: {data}")

            for item in data.get("result", {}).get("items", []):
                if item.get("name") == self.model_name:
                    self.model_id = item.get("id")
                    logger.info(f"Gongan model selected: {self.model_name}")
                    return self.model_id

            raise RuntimeError(f"Gongan model not found: {self.model_name!r}")

    def ensure_ready(self) -> None:
        self.ensure_login()
        self.ensure_model_id()

    def token_header(self, content_type: str | None = "application/json") -> dict[str, str]:
        headers = {"x-token-key": self.ensure_login()}
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def sse_headers(self) -> dict[str, str]:
        return {
            "x-token-key": self.ensure_login(),
            "accept": "text/event-stream",
            "Content-Type": "application/json",
        }

    def cookie_header(self) -> str:
        return f"locale=zh-Hans; JSESSIONID={self.ensure_login()}"

    def websocket_headers(self) -> dict[str, str]:
        return {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Cache-Control": "no-cache",
            "Cookie": self.cookie_header(),
        }

    def websocket_header_list(self) -> list[str]:
        return [
            "User-Agent: Mozilla/5.0",
            "Accept-Language: zh-CN,zh;q=0.9",
            "Cache-Control: no-cache",
        ]

    def tokenized_url(self, url: str) -> str:
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}x-token-key={self.ensure_login()}"

    def restore_punctuation(self, text: str) -> str:
        if not text:
            return ""
        url = f"{self.base_url}/audio/paddlespeech/text"
        try:
            response = self.session.request(
                "GET",
                url,
                headers=self.token_header(),
                json={"text": text},
                timeout=self.timeout,
            )
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            if data.get("success"):
                return data.get("result", {}).get("punc_text") or text
            logger.warning(f"Gongan punctuation restore failed: {data}")
        except Exception as exc:
            logger.warning(f"Gongan punctuation restore error: {exc}")
        return text


_client: GonganAPIClient | None = None
_client_lock = threading.Lock()


def get_gongan_client() -> GonganAPIClient:
    global _client
    with _client_lock:
        if _client is None:
            _client = GonganAPIClient()
        return _client
