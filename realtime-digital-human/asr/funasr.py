import asyncio
import io
import json
import wave

import numpy as np
import websockets
from loguru import logger

from asr.base import BaseASRProvider

_RECV_TIMEOUT_S = 10
_TEXT_IDLE_TIMEOUT_S = 0.8

_START_PAYLOAD = {
    "chunk_size": [5, 10, 5],
    "wav_name": "h5",
    "wav_format": "wav",
    "is_speaking": True,
    "mode": "offline",
    "itn": True,
    "is_final": False,
}

_END_PAYLOAD = {
    "wav_name": "h5",
    "is_speaking": False,
    "mode": "offline",
    "is_final": True,
}


def _pcm_to_wav(pcm: bytes, sample_rate: int = 16000) -> bytes:
    """将 raw PCM (Int16 mono) 转换为带 WAV 头的字节流"""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


class FunASRProvider(BaseASRProvider):
    def __init__(self, host: str, port: int):
        self._ws_url = f"ws://{host}:{port}"
        self._ws = None
        self._pcm_buf = bytearray()

    async def start_session(self) -> None:
        self._ws = await websockets.connect(self._ws_url)
        self._pcm_buf.clear()
        await self._ws.send(json.dumps(_START_PAYLOAD))
        logger.info(f"FunASR session started → {self._ws_url}")

    async def send_audio(self, pcm: bytes) -> None:
        if not self._ws:
            logger.warning("FunASR send_audio: ws is None, dropping frame")
            return
        self._pcm_buf.extend(pcm)

    async def end_session(self) -> str:
        if not self._ws:
            return ""

        pcm_bytes = bytes(self._pcm_buf)
        self._pcm_buf.clear()

        if not pcm_bytes:
            logger.warning("FunASR end_session: no audio to send")
            return ""

        wav_bytes = _pcm_to_wav(pcm_bytes)
        samples = np.frombuffer(pcm_bytes, dtype=np.int16)
        energy = int(np.abs(samples).mean())
        logger.info(f"[ASR] sending WAV: {len(samples)} samples ({len(samples)/16000:.1f}s), energy={energy}")

        await self._ws.send(wav_bytes)
        await self._ws.send(json.dumps(_END_PAYLOAD))
        logger.info("FunASR end payload sent, waiting for result")

        final_text = ""
        msg_count = 0

        async def _recv_loop():
            nonlocal final_text, msg_count
            deadline = asyncio.get_running_loop().time() + _RECV_TIMEOUT_S
            while True:
                now = asyncio.get_running_loop().time()
                if final_text:
                    timeout = _TEXT_IDLE_TIMEOUT_S
                else:
                    timeout = max(0.1, deadline - now)

                try:
                    raw = await asyncio.wait_for(self._ws.recv(), timeout=timeout)
                except asyncio.TimeoutError:
                    if final_text:
                        logger.info(
                            f"FunASR no final flag; using latest text after {_TEXT_IDLE_TIMEOUT_S}s idle"
                        )
                        return
                    raise

                msg_count += 1
                logger.debug(f"FunASR msg#{msg_count}: {raw}")
                data = json.loads(raw)
                is_final = data.get("is_final") or data.get("final")
                text = data.get("text") or data.get("result") or ""
                if text:
                    final_text = text
                if is_final:
                    return

        try:
            await asyncio.wait_for(_recv_loop(), timeout=_RECV_TIMEOUT_S)
        except asyncio.TimeoutError:
            logger.warning(f"FunASR recv timeout after {_RECV_TIMEOUT_S}s")
        except Exception as e:
            logger.warning(f"FunASR recv error: {e}")
        logger.info(f"FunASR result: {final_text!r} (received {msg_count} messages)")
        return final_text

    async def close(self) -> None:
        if self._ws:
            await self._ws.close()
            self._ws = None
