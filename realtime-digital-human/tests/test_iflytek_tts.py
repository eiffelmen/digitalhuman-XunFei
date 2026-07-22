"""
IflytekTTS 单元测试

运行方式：
    # 全部测试
    pytest tests/test_iflytek_tts.py -v

    # 只跑某一个
    pytest tests/test_iflytek_tts.py::TestBuildWsUrl::test_required_query_params -v

    # 看 print 输出（默认被 pytest 吞掉）
    pytest tests/test_iflytek_tts.py -v -s
"""

import sys
import types
import queue
import base64
import json
from unittest.mock import MagicMock, patch, call
from urllib.parse import urlparse, parse_qs

# --- 隔离重型依赖，不需要安装 torch / cv2 / resampy / websocket 等 ---
for _mod in ("resampy", "cv2", "torch", "soundfile", "edge_tts", "websocket", "requests"):
    sys.modules.setdefault(_mod, MagicMock())

# loguru 需要暴露 logger 属性，不能直接 MagicMock 整个模块
if "loguru" not in sys.modules:
    _fake_loguru = types.ModuleType("loguru")
    _fake_loguru.logger = MagicMock()
    sys.modules["loguru"] = _fake_loguru

# numpy 用真实的，frombuffer / array 不能 mock
import numpy as np  # noqa: E402

_fake_basereal = types.ModuleType("basereal")
_fake_basereal.BaseReal = type("BaseReal", (), {})
sys.modules.setdefault("basereal", _fake_basereal)

from ttsreal import IflytekTTS  # noqa: E402


# ---------------------------------------------------------------------------
# 辅助：构造最小 opt / parent
# ---------------------------------------------------------------------------

def _make_tts(app_id="app123", api_key="key456", vcn="xiaoyan"):
    opt = MagicMock()
    opt.fps = 50          # chunk = 16000 // 50 = 320 samples
    opt.ifly_vcn = vcn
    parent = MagicMock()
    with patch.dict("os.environ", {"IFLY_APP_ID": app_id, "IFLY_API_KEY": api_key}):
        tts = IflytekTTS(opt, parent)
    return tts, parent


# ---------------------------------------------------------------------------
# 1. 鉴权 URL 格式
# ---------------------------------------------------------------------------

class TestBuildWsUrl:
    def test_required_query_params(self):
        """URL 必须带 appid / checksum / param / curtime / signtype=md5"""
        tts, _ = _make_tts()
        url = tts._build_ws_url()
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)

        assert parsed.scheme == "ws"
        assert "wsapi.xfyun.cn" in parsed.netloc
        assert qs["appid"] == ["app123"]
        assert qs["signtype"] == ["md5"]
        assert "checksum" in qs
        assert "param" in qs
        assert "curtime" in qs

    def test_param_is_valid_base64_json(self):
        """param 字段解码后应是包含 scene / vcn 的 JSON"""
        tts, _ = _make_tts(vcn="aisjiuxu")
        url = tts._build_ws_url()
        param_b64 = parse_qs(urlparse(url).query)["param"][0]
        payload = json.loads(base64.b64decode(param_b64).decode())

        assert payload["scene"] == "IFLYTEK.tts"
        assert payload["vcn"] == "aisjiuxu"
        assert payload["tts_res_type"] == "base64"

    def test_checksum_changes_with_time(self):
        """每次调用 curtime 不同，checksum 也应不同"""
        tts, _ = _make_tts()
        with patch("ttsreal.time") as mock_time:
            mock_time.time.return_value = 1000
            url1 = tts._build_ws_url()
            mock_time.time.return_value = 2000
            url2 = tts._build_ws_url()

        qs1 = parse_qs(urlparse(url1).query)
        qs2 = parse_qs(urlparse(url2).query)
        assert qs1["checksum"] != qs2["checksum"]


# ---------------------------------------------------------------------------
# 2. _ifly_tts：WebSocket 消息处理
# ---------------------------------------------------------------------------

class TestIflyTts:
    def _run_ws_simulation(self, tts, messages):
        """
        模拟 WebSocket 服务端行为：
        - 拦截 WebSocketApp 构造，记录注册的回调
        - 在 run_forever 里依次触发 messages 列表中的消息
        - 返回 _ifly_tts 生成的所有 chunk
        """
        captured = {}

        def fake_ws_app(url, on_message, on_close, on_error, header):
            captured["url"] = url
            captured["on_message"] = on_message
            captured["on_close"] = on_close
            ws_mock = MagicMock()
            captured["ws"] = ws_mock

            def run_forever():
                for msg in messages:
                    on_message(ws_mock, json.dumps(msg))
                on_close(ws_mock, 1000, None)

            ws_mock.run_forever = run_forever
            return ws_mock

        with patch("ttsreal.websocket.WebSocketApp", side_effect=fake_ws_app):
            chunks = list(tts._ifly_tts("你好"))

        return chunks, captured

    def test_sends_text_on_started(self):
        """收到 action=started 后，应立即发送文本和结束符"""
        tts, _ = _make_tts()
        messages = [{"action": "started"}]
        _, captured = self._run_ws_simulation(tts, messages)

        ws = captured["ws"]
        assert ws.send.call_count == 2
        assert ws.send.call_args_list[0] == call("你好")
        assert ws.send.call_args_list[1] == call("--end--")

    def test_yields_decoded_audio_chunks(self):
        """action=result sub=tts 时，content 应 base64 解码后 yield"""
        tts, _ = _make_tts()
        fake_pcm = b"\x01\x02" * 100
        messages = [
            {"action": "started"},
            {"action": "result", "data": {
                "sub": "tts",
                "content": base64.b64encode(fake_pcm).decode()
            }},
        ]
        chunks, _ = self._run_ws_simulation(tts, messages)

        assert len(chunks) == 1
        assert chunks[0] == fake_pcm

    def test_multiple_tts_chunks(self):
        """多条 tts 消息都应被 yield"""
        tts, _ = _make_tts()
        pcm1 = b"\xAA" * 50
        pcm2 = b"\xBB" * 80
        messages = [
            {"action": "started"},
            {"action": "result", "data": {"sub": "tts", "content": base64.b64encode(pcm1).decode()}},
            {"action": "result", "data": {"sub": "tts", "content": base64.b64encode(pcm2).decode()}},
        ]
        chunks, _ = self._run_ws_simulation(tts, messages)

        assert chunks == [pcm1, pcm2]

    def test_non_tts_result_ignored(self):
        """sub != tts 的 result（如 iat / nlp）应被忽略"""
        tts, _ = _make_tts()
        messages = [
            {"action": "started"},
            {"action": "result", "data": {"sub": "iat", "content": "ignored"}},
        ]
        chunks, _ = self._run_ws_simulation(tts, messages)

        assert chunks == []

    def test_stops_yielding_when_paused(self):
        """state=PAUSE 时收到的 chunk 应被丢弃"""
        from ttsreal import State
        tts, _ = _make_tts()
        tts.state = State.PAUSE

        fake_pcm = b"\x01\x02" * 100
        messages = [
            {"action": "started"},
            {"action": "result", "data": {"sub": "tts", "content": base64.b64encode(fake_pcm).decode()}},
        ]
        chunks, _ = self._run_ws_simulation(tts, messages)

        assert chunks == []


# ---------------------------------------------------------------------------
# 3. stream_tts：PCM 转 float32 并按帧推送
# ---------------------------------------------------------------------------

class TestStreamTts:
    def test_pushes_320_sample_frames(self):
        """每帧应为 320 个 float32 样本（16kHz × 20ms）"""
        tts, parent = _make_tts()
        pcm = np.zeros(640, dtype=np.int16).tobytes()   # 640 samples = 2 帧
        tts.stream_tts(iter([pcm]))

        assert parent.put_audio_frame.call_count == 2
        for c in parent.put_audio_frame.call_args_list:
            frame = c[0][0]
            assert frame.shape == (320,)
            assert frame.dtype == np.float32

    def test_normalizes_to_float32(self):
        """int16 最大值 32767 应归一化为约 1.0"""
        tts, parent = _make_tts()
        pcm = np.full(320, 32767, dtype=np.int16).tobytes()
        tts.stream_tts(iter([pcm]))

        frame = parent.put_audio_frame.call_args[0][0]
        assert abs(frame.max() - 1.0) < 1e-4

    def test_remainder_samples_dropped(self):
        """不足一帧的尾部样本应被丢弃，不调用 put_audio_frame"""
        tts, parent = _make_tts()
        pcm = np.zeros(400, dtype=np.int16).tobytes()   # 400 = 1 帧 + 80 剩余
        tts.stream_tts(iter([pcm]))

        assert parent.put_audio_frame.call_count == 1
