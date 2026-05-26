import asyncio
import base64
import json
import sys
import types
import unittest
from urllib.parse import parse_qs, urlparse
from unittest.mock import MagicMock, patch

# 允许在未安装 websocket-client 的环境下导入 provider
if "websocket" not in sys.modules:
    sys.modules["websocket"] = MagicMock()
if "loguru" not in sys.modules:
    fake_loguru = types.ModuleType("loguru")
    fake_loguru.logger = MagicMock()
    sys.modules["loguru"] = fake_loguru
if "basereal" not in sys.modules:
    fake_basereal = types.ModuleType("basereal")

    class _BaseReal:
        pass

    fake_basereal.BaseReal = _BaseReal
    sys.modules["basereal"] = fake_basereal

from llm.providers.iflytek import _build_auth_url, llm_response


def _drain_queue(queue: asyncio.Queue):
    items = []
    while True:
        try:
            items.append(queue.get_nowait())
        except asyncio.QueueEmpty:
            break
    return items


class TestIflytekProvider(unittest.TestCase):
    def test_build_auth_url_contains_required_params(self):
        url = _build_auth_url(
            "wss://aiui.xf-yun.com/v3/aiint/sos",
            api_key="test_key",
            api_secret="test_secret",
        )
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        self.assertIn("host", query)
        self.assertIn("date", query)
        self.assertIn("authorization", query)
        self.assertEqual(parsed.scheme, "wss")

    @patch("llm.providers.iflytek.websocket.create_connection")
    def test_llm_response_returns_none_when_missing_config(self, mock_conn):
        queue = asyncio.Queue()
        nerfreal = MagicMock()

        with patch.dict("os.environ", {}, clear=True):
            result = llm_response("你好", nerfreal, "session-1", queue)

        self.assertIsNone(result)
        mock_conn.assert_not_called()
        nerfreal.put_msg_txt.assert_not_called()

        items = _drain_queue(queue)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["finish"], True)

    @patch("llm.providers.iflytek.websocket.create_connection")
    def test_llm_response_success(self, mock_conn):
        nlp_text = "你好，我是讯飞助手，我可以帮助你处理问答请求。"
        ws_messages = [
            json.dumps(
                {
                    "header": {"code": 0, "status": 0},
                    "payload": {
                        "nlp": {
                            "seq": 1,
                            "text": base64.b64encode(
                                nlp_text.encode("utf-8")
                            ).decode("utf-8"),
                        }
                    },
                }
            ),
            json.dumps({"header": {"code": 0, "status": 2}, "payload": {}}),
        ]

        ws = MagicMock()
        ws.recv = MagicMock(side_effect=ws_messages)
        mock_conn.return_value = ws

        queue = asyncio.Queue()
        nerfreal = MagicMock()

        with patch.dict(
            "os.environ",
            {
                "IFLYTEK_APPID": "appid",
                "IFLYTEK_API_KEY": "api_key",
                "IFLYTEK_API_SECRET": "api_secret",
            },
            clear=True,
        ):
            result = llm_response("帮我介绍你自己", nerfreal, "session-2", queue)

        self.assertEqual(result, nlp_text)
        ws.send.assert_called_once()
        ws.close.assert_called_once()
        nerfreal.put_msg_txt.assert_called()

        items = _drain_queue(queue)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["data"], nlp_text)
        self.assertEqual(items[0]["finish"], False)
        self.assertEqual(items[1]["finish"], True)

    @patch("llm.providers.iflytek.websocket.create_connection")
    def test_llm_response_connection_error(self, mock_conn):
        mock_conn.side_effect = Exception("connect failed")
        queue = asyncio.Queue()
        nerfreal = MagicMock()

        with patch.dict(
            "os.environ",
            {
                "IFLYTEK_APPID": "appid",
                "IFLYTEK_API_KEY": "api_key",
                "IFLYTEK_API_SECRET": "api_secret",
            },
            clear=True,
        ):
            result = llm_response("你好", nerfreal, "session-3", queue)

        self.assertIsNone(result)
        nerfreal.put_msg_txt.assert_not_called()
        items = _drain_queue(queue)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["finish"], True)


if __name__ == "__main__":
    unittest.main()
