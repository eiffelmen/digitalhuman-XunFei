import asyncio
import inspect
import os
import uuid
from typing import TYPE_CHECKING

from asr.factory import create_asr_provider
from asr.base import BaseASRProvider
from audio_vad import AudioVAD
from loguru import logger
from perf_logger import elapsed_ms, log_perf, log_timepoint, now

if TYPE_CHECKING:
    from aiohttp.web import WebSocketResponse
    from app_v2 import AppState


def _get_llm_response():
    provider = os.environ.get("LLM_PROVIDER", "gongan")
    if provider == "gongan":
        from llm.providers.gongan import llm_response
    elif provider == "rag":
        from llm.providers.rag import llm_response
    elif provider == "chatgpt_oss":
        from llm.providers.chatgpt_oss import llm_response
    elif provider == "ratubrain":
        from llm.providers.ratubrain import llm_response
    elif provider == "iflytek":
        from llm.providers.iflytek import llm_response
    elif provider == "aliyun":
        from llm.providers.aliyun import llm_response
    else:
        from llm.providers.gongan import llm_response
    return llm_response


class ASRSessionHandler:
    def __init__(self, session_id: str, state: "AppState", ws: "WebSocketResponse | None" = None):
        self._session_id = session_id
        self._state = state
        self._ws = ws
        self._provider: BaseASRProvider | None = None
        self._trace_id: str | None = None
        self._speech_start_mono: float | None = None
        self._audio_frames_sent = 0
        self._audio_bytes_sent = 0
        self._prebuffer_frames = 0
        self._provider_name = os.environ.get("ASR_PROVIDER", "gongan")
        self._audio_chunks_received = 0
        self._audio_bytes_received = 0
        self._audio_chunks_skipped_speaking = 0
        self._audio_bytes_skipped_speaking = 0
        self._last_audio_diag_mono = 0.0
        self._last_speaking_skip_diag_mono = 0.0
        self._had_speaking_skip = False
        self._last_asr_partial_text = ""
        self._vad = AudioVAD(
            on_speech_start=self._on_speech_start,
            on_speech_end=self._on_speech_end,
            on_audio=self._on_audio,
            threshold=0.7,
        )

    async def on_audio_chunk(self, pcm: bytes) -> None:
        self._audio_chunks_received += 1
        self._audio_bytes_received += len(pcm)
        current = now()
        # 数字人正在说话时，跳过 VAD 处理，防止麦克风拾取数字人自身声音导致反馈循环
        nerfreal = self._state.nerfreals.get(self._session_id)
        if nerfreal and getattr(nerfreal, 'speaking', False):
            self._audio_chunks_skipped_speaking += 1
            self._audio_bytes_skipped_speaking += len(pcm)
            self._had_speaking_skip = True
            should_log = (
                self._audio_chunks_skipped_speaking <= 3
                or current - self._last_speaking_skip_diag_mono >= 5.0
            )
            if should_log:
                self._last_speaking_skip_diag_mono = current
                logger.warning(
                    f"[PIPELINE] audio_chunk_skipped_while_avatar_speaking "
                    f"session={self._session_id} "
                    f"received_chunks={self._audio_chunks_received} "
                    f"received_bytes={self._audio_bytes_received} "
                    f"skipped_chunks={self._audio_chunks_skipped_speaking} "
                    f"skipped_bytes={self._audio_bytes_skipped_speaking}"
                )
            return
        if self._had_speaking_skip:
            self._had_speaking_skip = False
            logger.info(
                f"[PIPELINE] audio_chunk_resumed_to_vad session={self._session_id} "
                f"received_chunks={self._audio_chunks_received} "
                f"skipped_while_speaking={self._audio_chunks_skipped_speaking}"
            )
        if (
            self._audio_chunks_received <= 3
            or current - self._last_audio_diag_mono >= 5.0
        ):
            self._last_audio_diag_mono = current
            logger.debug(
                f"[PIPELINE] audio_chunk_to_vad session={self._session_id} "
                f"chunks={self._audio_chunks_received} "
                f"bytes={self._audio_bytes_received} "
                f"chunk_bytes={len(pcm)}"
            )
        await self._vad.process_chunk(pcm)

    async def _on_speech_start(self, pre_buffer: list[bytes]) -> None:
        self._trace_id = uuid.uuid4().hex[:12]
        self._speech_start_mono = now()
        self._audio_frames_sent = 0
        self._audio_bytes_sent = 0
        self._prebuffer_frames = len(pre_buffer)
        self._provider_name = os.environ.get("ASR_PROVIDER", "gongan")
        self._last_asr_partial_text = ""
        logger.info(
            f"[ASR] speech start, session={self._session_id}, "
            f"trace_id={self._trace_id}, prebuffer_frames={len(pre_buffer)}"
        )
        log_timepoint(
            "ASR",
            "检测到说话开始",
            trace_id=self._trace_id,
            sessionid=self._session_id,
            provider=self._provider_name,
            prebuffer_frames=len(pre_buffer),
        )
        provider_start = now()
        try:
            self._provider = create_asr_provider()
            if hasattr(self._provider, "set_partial_callback"):
                self._provider.set_partial_callback(self._handle_asr_partial)
            await self._provider.start_session()
            log_perf(
                "asr",
                "provider_start_session",
                elapsed_ms(provider_start),
                trace_id=self._trace_id,
                sessionid=self._session_id,
                provider=self._provider_name,
            )
            for chunk in pre_buffer:
                await self._provider.send_audio(chunk)
                self._audio_frames_sent += 1
                self._audio_bytes_sent += len(chunk)
            if pre_buffer:
                log_perf(
                    "asr",
                    "prebuffer_sent",
                    trace_id=self._trace_id,
                    sessionid=self._session_id,
                    provider=self._provider_name,
                    frames=len(pre_buffer),
                    bytes=sum(len(chunk) for chunk in pre_buffer),
                )
        except Exception as e:
            logger.warning(f"[ASR] failed to start provider trace_id={self._trace_id}: {e}")
            if self._provider:
                try:
                    await self._provider.close()
                except Exception:
                    pass
            self._provider = None

    async def _on_audio(self, frame: bytes) -> None:
        if self._provider:
            try:
                self._audio_frames_sent += 1
                self._audio_bytes_sent += len(frame)
                await self._provider.send_audio(frame)
            except Exception as e:
                logger.warning(
                    f"[ASR] failed to send audio frame trace_id={self._trace_id}: {e}"
                )

    async def _on_speech_end(self) -> None:
        if not self._provider:
            return
        trace_id = self._trace_id
        speech_duration_ms = (
            elapsed_ms(self._speech_start_mono)
            if self._speech_start_mono is not None
            else None
        )
        speech_duration_text = (
            f"{speech_duration_ms:.2f}" if speech_duration_ms is not None else "unknown"
        )
        logger.info(
            f"[ASR] speech end, session={self._session_id}, trace_id={trace_id}, "
            f"speech_duration_ms={speech_duration_text}, "
            f"audio_frames={self._audio_frames_sent}, audio_bytes={self._audio_bytes_sent}"
        )
        log_timepoint(
            "ASR",
            "检测到说话结束",
            trace_id=trace_id,
            sessionid=self._session_id,
            provider=self._provider_name,
            audio_frames=self._audio_frames_sent,
            audio_bytes=self._audio_bytes_sent,
            speech_duration_ms=speech_duration_text,
        )
        provider = self._provider
        self._provider = None
        asr_start = now()
        success = True
        try:
            text = await provider.end_session()
        except Exception as e:
            success = False
            logger.warning(f"[ASR] provider end_session failed trace_id={trace_id}: {e}")
            text = ""
        finally:
            asr_duration_ms = elapsed_ms(asr_start)
            log_perf(
                "asr",
                "provider_end_session",
                asr_duration_ms,
                trace_id=trace_id,
                sessionid=self._session_id,
                provider=self._provider_name,
                success=success,
                recognized_len=len(text or ""),
                audio_frames=self._audio_frames_sent,
                audio_bytes=self._audio_bytes_sent,
                speech_duration_ms=speech_duration_text,
            )
            close_start = now()
            await provider.close()
            log_perf(
                "asr",
                "provider_close",
                elapsed_ms(close_start),
                trace_id=trace_id,
                sessionid=self._session_id,
                provider=self._provider_name,
            )

        if not text:
            logger.debug(f"[ASR] empty result, skipping LLM dispatch trace_id={trace_id}")
            return

        logger.info(f"[ASR] recognized trace_id={trace_id}: {text!r}")
        log_perf(
            "trace",
            "asr_done",
            asr_duration_ms,
            trace_id=trace_id,
            sessionid=self._session_id,
            provider=self._provider_name,
            recognized_len=len(text),
            total_from_speech_start_ms=speech_duration_text,
        )

        # 将 ASR 结果推送给前端
        await self._send_asr_result(text, trace_id=trace_id, is_final=True)

        self._dispatch_to_llm(text, trace_id=trace_id)

    async def _handle_asr_partial(self, text: str, *, is_final: bool = False) -> None:
        text = (text or "").strip()
        if not text:
            return
        if not is_final and text == self._last_asr_partial_text:
            return
        self._last_asr_partial_text = text
        logger.info(
            f"[ASR] partial result trace_id={self._trace_id}, "
            f"session={self._session_id}, is_final={is_final}, text={text!r}"
        )
        log_perf(
            "asr",
            "partial_result_to_client",
            trace_id=self._trace_id,
            sessionid=self._session_id,
            provider=self._provider_name,
            text_len=len(text),
            is_final=is_final,
        )
        await self._send_asr_result(text, trace_id=self._trace_id, is_final=is_final)

    async def _send_asr_result(
        self,
        text: str,
        trace_id: str | None = None,
        *,
        is_final: bool = True,
    ) -> None:
        ws = await self._wait_for_text_ws(timeout=1.0 if is_final else 0.2)
        if ws is None:
            logger.warning(
                f"[ASR] text websocket not ready; cannot send result "
                f"session={self._session_id}, trace_id={trace_id}, is_final={is_final}"
            )
            return
        start = now()
        try:
            await ws.send_json(
                {
                    "type": "asr",
                    "data": text,
                    "text": text,
                    "result": text,
                    "trace_id": trace_id,
                    "is_final": is_final,
                    "partial": not is_final,
                }
            )
            log_perf(
                "asr",
                "send_result_to_client",
                elapsed_ms(start),
                trace_id=trace_id,
                sessionid=self._session_id,
                text_len=len(text),
                is_final=is_final,
            )
        except Exception as e:
            logger.warning(f"[ASR] failed to send result to client trace_id={trace_id}: {e}")

    async def _wait_for_text_ws(self, timeout: float = 0.0):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(0.0, timeout)
        while True:
            ws = self._state.sessionid_ws.get(self._session_id)
            if ws is None:
                ws = self._ws
            if ws is not None and not getattr(ws, "closed", False):
                self._ws = ws
                return ws
            if loop.time() >= deadline:
                return None
            await asyncio.sleep(0.05)

    def _dispatch_to_llm(self, text: str, trace_id: str | None = None) -> None:
        nerfreal = self._state.nerfreals.get(self._session_id)
        if not nerfreal:
            logger.warning(f"[ASR] no nerfreal for session={self._session_id}, trace_id={trace_id}")
            return
        if hasattr(nerfreal, "set_active_chat_trace"):
            nerfreal.set_active_chat_trace(trace_id)
        result_queue = asyncio.Queue()
        self._state.llm_response_queues[self._session_id] = result_queue
        llm_response = _get_llm_response()
        loop = asyncio.get_event_loop()
        provider = os.environ.get("LLM_PROVIDER", "gongan")
        logger.info(
            f"[ASR] dispatch LLM session={self._session_id}, trace_id={trace_id}, "
            f"provider={provider}, text_len={len(text)}"
        )
        log_timepoint(
            "LLM",
            "ASR结果开始进入大模型",
            trace_id=trace_id,
            sessionid=self._session_id,
            provider=provider,
            text_len=len(text),
        )
        log_perf(
            "trace",
            "llm_dispatch",
            trace_id=trace_id,
            sessionid=self._session_id,
            provider=provider,
            text_len=len(text),
        )
        loop.run_in_executor(
            None,
            self._timed_llm_response,
            llm_response,
            text,
            nerfreal,
            self._session_id,
            result_queue,
            trace_id,
        )

    def _timed_llm_response(
        self,
        llm_response,
        text: str,
        nerfreal,
        sessionid: str,
        result_queue: asyncio.Queue,
        trace_id: str | None,
    ):
        provider = os.environ.get("LLM_PROVIDER", "gongan")
        start = now()
        success = True
        try:
            signature = inspect.signature(llm_response)
            if "trace_id" in signature.parameters:
                return llm_response(
                    text,
                    nerfreal,
                    sessionid,
                    result_queue,
                    trace_id=trace_id,
                )
            return llm_response(text, nerfreal, sessionid, result_queue)
        except Exception:
            success = False
            raise
        finally:
            log_perf(
                "llm",
                "response_total",
                elapsed_ms(start),
                provider=provider,
                sessionid=sessionid,
                text_len=len(text),
                device="external",
                trace_id=trace_id,
                success=success,
            )

    async def close(self) -> None:
        logger.info(
            f"[PIPELINE] audio_asr_handler_close session={self._session_id} "
            f"received_chunks={self._audio_chunks_received} "
            f"received_bytes={self._audio_bytes_received} "
            f"skipped_while_speaking={self._audio_chunks_skipped_speaking} "
            f"skipped_bytes={self._audio_bytes_skipped_speaking}"
        )
        if self._provider:
            await self._provider.close()
            self._provider = None
