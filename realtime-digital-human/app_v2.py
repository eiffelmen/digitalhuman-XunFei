import os
import time
import json
import inspect
import gc
from typing import Any, Dict
import uuid
import asyncio
import argparse
import torch.multiprocessing as mp
from dotenv import load_dotenv

# 加载 .env 环境变量
load_dotenv(override=True)

import os as _os
from mylogger import logger as _early_logger

_SENSITIVE_ENV_HINTS = ("KEY", "PWD", "PASSWORD", "TOKEN", "SECRET")


def _mask_env_value(key, value):
    if value is None:
        return None
    if any(hint in key.upper() for hint in _SENSITIVE_ENV_HINTS):
        text = str(value)
        if len(text) <= 8:
            return "***"
        return f"{text[:3]}***{text[-3:]}"
    return value


_early_logger.info("=== 启动环境变量 ===")
for _k in ["CUDA_VISIBLE_DEVICES", "LLM_PROVIDER", "ASR_PROVIDER",
           "IFLYTEK_SN", "IFLY_APP_ID", "IFLY_API_KEY", "IFLYTEK_VCN",
           "IFLYTEK_TTS_ENGINE", "IFLYTEK_TTS_SPEED", "IFLYTEK_TTS_PITCH",
           "IFLYTEK_INCREMENTAL_TTS",
           "FUNASR_HOST", "FUNASR_PORT", "GONGAN_API_BASE_URL",
           "GONGAN_MODEL_NAME", "GONGAN_DIRECT_TTS", "LISTEN_PORT"]:
    _v = _os.environ.get(_k)
    _early_logger.info(f"  {_k} = {_mask_env_value(_k, _v)!r}")
_early_logger.info("===================")

from tomlkit import dumps, parse

from lipreal import LipReal, load_model, load_avatar, warm_up
from basereal import BaseReal
from asr_session import ASRSessionHandler
from build_nerf import build_nerfreal
import aiohttp
import aiohttp_cors
from aiohttp import web
from webrtc import HumanPlayer
from aiortc.rtcrtpsender import RTCRtpSender
from aiortc import (
    RTCPeerConnection,
    RTCSessionDescription,
    RTCIceServer,
    RTCConfiguration,
)
from mylogger import logger
from perf_logger import elapsed_ms, log_perf, log_timepoint, now
from session_websocket import (
    claim_websocket,
    invalidate_websocket,
    release_websocket,
    websocket_epoch_matches,
    websocket_is_open,
)


WEBRTC_DISCONNECT_GRACE = float(os.environ.get("WEBRTC_DISCONNECT_GRACE", "10"))
SESSION_WS_CLOSE_GRACE = float(os.environ.get("SESSION_WS_CLOSE_GRACE", "5"))
MAX_ACTIVE_WEBRTC_SESSIONS = max(
    1, int(os.environ.get("MAX_ACTIVE_WEBRTC_SESSIONS", "1"))
)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.lower() not in {"0", "false", "no", "off"}


def _env_float(name: str, default: float, minimum: float) -> float:
    try:
        return max(minimum, float(os.environ.get(name, default) or default))
    except (TypeError, ValueError):
        logger.warning(f"{name} 配置无效，使用默认值 {default}")
        return max(minimum, default)


def _env_int(name: str, default: int, minimum: int) -> int:
    try:
        return max(minimum, int(os.environ.get(name, default) or default))
    except (TypeError, ValueError):
        logger.warning(f"{name} 配置无效，使用默认值 {default}")
        return max(minimum, default)


SERVER_METRICS_ENABLED = _env_bool("SERVER_METRICS_ENABLED", True)
SERVER_METRICS_INTERVAL_S = _env_float("SERVER_METRICS_INTERVAL_S", 10.0, 2.0)
CLIENT_METRICS_MAX_BYTES = _env_int("CLIENT_METRICS_MAX_BYTES", 120000, 1024)
CLIENT_METRICS_MAX_TEXT = _env_int("CLIENT_METRICS_MAX_TEXT", 3000, 256)


class AppState:
    def __init__(self):
        self.nerfreals: Dict[str, BaseReal] = {}
        self.pcs: set = set()
        self.instanceid_pc: Dict[str, RTCPeerConnection] = {}
        self.sessionid_ws: Dict[str, web.WebSocketResponse] = {}
        self.sessionid_ws_epochs: Dict[str, int] = {}
        self.opt = None
        self.model = None
        self.avatar = None
        self.llm_response_queues: Dict[str, asyncio.Queue] = {}
        self.llm_ws_metrics: Dict[str, Dict[str, Any]] = {}
        self.cleaning_sessions: set[str] = set()
        self.offer_lock = asyncio.Lock()
        self.session_players: Dict[str, HumanPlayer] = {}


class ConfigManager:
    CONFIG_FILE = "config.toml"

    @staticmethod
    def get_configs():
        try:
            if not os.path.exists(ConfigManager.CONFIG_FILE):
                with open(ConfigManager.CONFIG_FILE, "w", encoding="utf-8") as f:
                    f.write("")
                return {}
            with open(ConfigManager.CONFIG_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return {}
                return dict(parse(content))
        except Exception as e:
            logger.error(f"读取配置文件失败: {str(e)}")
            return {}

    @staticmethod
    def save_configs(new_configs):
        try:
            existing = ConfigManager.get_configs()
            merged = existing.copy()
            for key, value in new_configs.items():
                if isinstance(value, dict) and key in existing:
                    if key == "sessions":
                        merged[key] = {**existing[key], **value}
                    else:
                        merged[key] = {**existing.get(key, {}), **value}
                else:
                    merged[key] = value

            with open(ConfigManager.CONFIG_FILE, "w", encoding="utf-8") as f:
                f.write(dumps(merged))
        except Exception as e:
            logger.error(f"保存配置文件失败: {str(e)}")


def _truncate_value(value: Any, max_text: int = CLIENT_METRICS_MAX_TEXT):
    if isinstance(value, dict):
        return {
            str(key)[:80]: _truncate_value(item, max_text)
            for key, item in list(value.items())[:120]
        }
    if isinstance(value, list):
        return [_truncate_value(item, max_text) for item in value[:80]]
    if isinstance(value, tuple):
        return tuple(_truncate_value(item, max_text) for item in value[:80])
    if isinstance(value, str) and len(value) > max_text:
        return value[:max_text] + f"...<truncated:{len(value)}>"
    return value


def _json_dumps_for_log(payload: Any) -> str:
    try:
        return json.dumps(
            _truncate_value(payload),
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
    except Exception as exc:
        return json.dumps(
            {"log_encode_error": str(exc), "payload_type": type(payload).__name__},
            ensure_ascii=False,
        )


def _safe_qsize(target_queue):
    if target_queue is None:
        return None
    try:
        return target_queue.qsize()
    except Exception:
        return None


def _safe_queue_max(target_queue):
    if target_queue is None:
        return None
    return getattr(target_queue, "maxsize", getattr(target_queue, "_maxsize", None))


def _proc_status_snapshot():
    status = {}
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as f:
            for line in f:
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                if key in {
                    "VmRSS",
                    "VmHWM",
                    "VmSize",
                    "VmData",
                    "VmSwap",
                    "Threads",
                    "FDSize",
                }:
                    status[key] = value.strip()
    except Exception:
        pass

    try:
        status["open_fds"] = len(os.listdir("/proc/self/fd"))
    except Exception:
        status["open_fds"] = None

    return status


def _cuda_snapshot():
    try:
        import torch

        if not torch.cuda.is_available():
            return {"available": False}
        return {
            "available": True,
            "device_name": torch.cuda.get_device_name(0),
            "memory_allocated_mb": round(torch.cuda.memory_allocated() / 1024 / 1024, 2),
            "memory_reserved_mb": round(torch.cuda.memory_reserved() / 1024 / 1024, 2),
            "max_memory_allocated_mb": round(
                torch.cuda.max_memory_allocated() / 1024 / 1024, 2
            ),
            "max_memory_reserved_mb": round(
                torch.cuda.max_memory_reserved() / 1024 / 1024, 2
            ),
        }
    except Exception as exc:
        return {"error": str(exc)}


def _pc_snapshot(pc):
    if pc is None:
        return None
    return {
        "connectionState": getattr(pc, "connectionState", None),
        "iceConnectionState": getattr(pc, "iceConnectionState", None),
        "iceGatheringState": getattr(pc, "iceGatheringState", None),
        "signalingState": getattr(pc, "signalingState", None),
    }


def _nerfreal_snapshot(nerfreal):
    if nerfreal is None:
        return None

    asr = getattr(nerfreal, "asr", None)
    tts = getattr(nerfreal, "tts", None)
    audio_track_size, video_track_size = (None, None)
    try:
        if hasattr(nerfreal, "_media_track_queue_sizes"):
            audio_track_size, video_track_size = nerfreal._media_track_queue_sizes()
    except Exception:
        pass

    return {
        "speaking": getattr(nerfreal, "speaking", None),
        "curr_state": getattr(nerfreal, "curr_state", None),
        "audio_push_count": getattr(nerfreal, "_audio_push_count", None),
        "render_next_linear_index": getattr(nerfreal, "_next_render_linear_index", None),
        "render_last_linear_index": getattr(nerfreal, "_last_render_linear_index", None),
        "render_cache_size": len(getattr(nerfreal, "_render_cache", {}) or {}),
        "render_cache_limit": getattr(nerfreal, "render_cache_size", None),
        "inference_thread_alive": bool(
            getattr(nerfreal, "inference_thread", None)
            and nerfreal.inference_thread.is_alive()
        ),
        "queues": {
            "asr_input": _safe_qsize(getattr(asr, "queue", None)),
            "asr_input_max": _safe_queue_max(getattr(asr, "queue", None)),
            "asr_output": _safe_qsize(getattr(asr, "output_queue", None)),
            "asr_output_max": _safe_queue_max(getattr(asr, "output_queue", None)),
            "asr_feat": _safe_qsize(getattr(asr, "feat_queue", None)),
            "asr_feat_max": _safe_queue_max(getattr(asr, "feat_queue", None)),
            "tts_text": _safe_qsize(getattr(tts, "msgqueue", None)),
            "tts_text_max": _safe_queue_max(getattr(tts, "msgqueue", None)),
            "wav2lip_frames": _safe_qsize(getattr(nerfreal, "res_frame_queue", None)),
            "wav2lip_frames_max": _safe_queue_max(
                getattr(nerfreal, "res_frame_queue", None)
            ),
            "webrtc_audio_track": audio_track_size,
            "webrtc_video_track": video_track_size,
        },
        "asr_counters": {
            "input_frames_received": getattr(asr, "input_frames_received", None),
            "input_frames_dropped": getattr(asr, "input_frames_dropped", None),
            "output_frames_dropped": getattr(asr, "output_frames_dropped", None),
            "feat_batches_dropped": getattr(asr, "feat_batches_dropped", None),
        },
        "tts_state": str(getattr(tts, "state", None)),
        "tts_diagnostics": tts.diagnostics() if hasattr(tts, "diagnostics") else None,
    }


def _server_metrics_payload(state: AppState):
    sessions = {}
    for sessionid, nerfreal in list(state.nerfreals.items()):
        player = state.session_players.get(sessionid)
        sessions[sessionid] = {
            "pc": _pc_snapshot(state.instanceid_pc.get(sessionid)),
            "has_text_ws": sessionid in state.sessionid_ws,
            "llm_queue": _safe_qsize(state.llm_response_queues.get(sessionid)),
            "nerfreal": _nerfreal_snapshot(nerfreal),
            "player": player.diagnostics() if player else None,
        }

    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "active_sessions": len(state.nerfreals),
        "pcs": len(state.pcs),
        "text_websockets": len(state.sessionid_ws),
        "llm_queues": len(state.llm_response_queues),
        "llm_ws_metrics": _truncate_value(state.llm_ws_metrics),
        "cleaning_sessions": list(state.cleaning_sessions),
        "process": _proc_status_snapshot(),
        "gc_counts": gc.get_count(),
        "cuda": _cuda_snapshot(),
        "sessions": sessions,
    }


async def _server_metrics_loop(state: AppState):
    while True:
        await asyncio.sleep(SERVER_METRICS_INTERVAL_S)
        try:
            logger.info(
                "[SERVER_METRICS] "
                + _json_dumps_for_log(_server_metrics_payload(state))
            )
        except Exception as exc:
            logger.warning(f"[SERVER_METRICS] collect failed: {exc}")


async def health_check(request):
    """检查服务状态"""
    return web.json_response({"code": 0, "message": "服务正常"})

async def ready(request):
    """查询服务是否已经完全启动（包括模型已经预热）"""
    return web.json_response({"status": 1})


async def client_metrics(request):
    """接收浏览器端播放/WebRTC/内存指标，统一写入后端日志。"""
    remote = request.remote
    ua = request.headers.get("User-Agent", "")
    try:
        raw = await request.read()
        if len(raw) > CLIENT_METRICS_MAX_BYTES:
            logger.warning(
                f"[CLIENT_METRICS] payload too large remote={remote} bytes={len(raw)}"
            )
            return web.json_response({"code": 413, "message": "payload too large"}, status=413)
        payload = json.loads(raw.decode("utf-8") or "{}")
    except Exception as exc:
        logger.warning(f"[CLIENT_METRICS] invalid payload remote={remote}: {exc}")
        return web.json_response({"code": 400, "message": "invalid payload"}, status=400)

    payload = _truncate_value(payload)
    envelope = {
        "remote": remote,
        "user_agent": ua[:300],
        "payload": payload,
    }
    payload_type = payload.get("type") if isinstance(payload, dict) else None
    event_name = payload.get("event") if isinstance(payload, dict) else None
    log_prefix = "[CLIENT_METRICS]"
    if payload_type == "client_event":
        log_prefix = "[CLIENT_EVENT]"
    elif event_name and event_name != "interval":
        log_prefix = "[CLIENT_METRICS_EVENT]"
    logger.info(f"{log_prefix} " + _json_dumps_for_log(envelope))
    return web.json_response({"code": 0, "data": "ok"})


def stop_nerfreal_instance(nerfreal: LipReal):
    """
    停止并清理 LipReal 实例
    """
    try:
        if nerfreal:
            # 停止数字人实例
            if hasattr(nerfreal, "stop") and callable(getattr(nerfreal, "stop")):
                nerfreal.stop()
                logger.info("数字人实例已停止")
            else:
                logger.warning("数字人实例没有stop方法，跳过停止操作")

            # 清理队列和缓冲区
            if hasattr(nerfreal, "flush_talk") and callable(
                getattr(nerfreal, "flush_talk")
            ):
                nerfreal.flush_talk()
                logger.info("已清理数字人队列")

    except Exception as e:
        logger.error(f"停止数字人实例时发生错误: {str(e)}")
        # 即使出错也要继续清理其他资源


async def cleanup_session(state: AppState, sessionid: str, pc=None, reason: str = ""):
    """
    统一清理单个会话，避免 WebRTC 断线后线程、队列和数字人实例残留。
    """
    if sessionid in state.cleaning_sessions:
        logger.info(f"会话正在清理中，跳过重复清理 sessionid={sessionid}, reason={reason}")
        return
    state.cleaning_sessions.add(sessionid)
    logger.info(f"开始清理会话 sessionid={sessionid}, reason={reason}")

    try:
        current_pc = state.instanceid_pc.get(sessionid)
        if pc is not None and current_pc is not pc:
            logger.info(
                f"忽略旧 WebRTC 连接的清理请求 sessionid={sessionid}, reason={reason}"
            )
            return

        # 先同步摘除本代会话状态，再执行任何 await，避免旧连接的回调误删新状态。
        active_pc = current_pc
        state.instanceid_pc.pop(sessionid, None)
        state.session_players.pop(sessionid, None)
        state.llm_ws_metrics.pop(sessionid, None)
        nerfreal = state.nerfreals.pop(sessionid, None)
        ws = invalidate_websocket(
            state.sessionid_ws, state.sessionid_ws_epochs, sessionid
        )
        state.llm_response_queues.pop(sessionid, None)

        if active_pc is not None:
            state.pcs.discard(active_pc)
            if active_pc.connectionState != "closed":
                try:
                    await active_pc.close()
                except Exception as e:
                    logger.warning(f"关闭 WebRTC 连接失败 sessionid={sessionid}: {e}")

        if nerfreal is not None:
            stop_nerfreal_instance(nerfreal)

        if websocket_is_open(ws):
            try:
                await ws.close()
            except Exception as e:
                logger.warning(f"关闭 WebSocket 失败 sessionid={sessionid}: {e}")

        logger.info(f"会话清理完成 sessionid={sessionid}")
    finally:
        state.cleaning_sessions.discard(sessionid)


async def cleanup_after_ws_close(
    state: AppState, sessionid: str, ws_epoch: int
):
    """
    浏览器刷新或关闭时，文本 WebSocket 通常会先断开。
    如果短暂等待后没有新的文本 WebSocket 接上，主动回收该会话，避免旧推理线程继续占用资源。
    """
    await asyncio.sleep(SESSION_WS_CLOSE_GRACE)
    if not websocket_epoch_matches(
        state.sessionid_ws_epochs, sessionid, ws_epoch
    ):
        logger.info(
            f"忽略旧 WebSocket 的延迟清理 sessionid={sessionid}, epoch={ws_epoch}"
        )
        return
    if sessionid in state.nerfreals and sessionid not in state.sessionid_ws:
        await cleanup_session(
            state,
            sessionid,
            reason=f"text websocket closed for {SESSION_WS_CLOSE_GRACE:.1f}s",
        )


async def wait_for_session_cleanup(
    state: AppState, sessionid: str, timeout: float = 5.0
):
    """同一个 sessionid 重新建联前，等待旧清理流程结束，避免误删新实例。"""
    deadline = time.monotonic() + timeout
    while sessionid in state.cleaning_sessions and time.monotonic() < deadline:
        await asyncio.sleep(0.05)


async def cleanup_old_sessions_for_new_offer(state: AppState, keep_sessionid: str):
    """限制活跃 WebRTC 会话数，防止多次刷新后旧会话堆积导致掉帧。"""
    active_sessionids = [
        sessionid
        for sessionid in list(state.nerfreals.keys())
        if sessionid != keep_sessionid
    ]
    overflow = len(active_sessionids) - (MAX_ACTIVE_WEBRTC_SESSIONS - 1)
    if overflow <= 0:
        return
    for old_sessionid in active_sessionids[:overflow]:
        await cleanup_session(
            state,
            old_sessionid,
            reason=f"new offer; active session limit={MAX_ACTIVE_WEBRTC_SESSIONS}",
        )


async def generate_session(request):
    """
    生成唯一的 sessionID 接口，用于记录用户信息
    """
    try:
        sessionid = str(uuid.uuid4())
        logger.info(f"生成新的 sessionID: {sessionid}")
        return web.Response(
            content_type="application/json", text=json.dumps({"sessionid": sessionid})
        )
    except Exception as e:
        logger.error(f"生成 sessionID 失败: {str(e)}")
        return web.Response(
            content_type="application/json",
            text=json.dumps({"error": "生成 sessionID 失败"}),
            status=500,
        )


async def offer(request):
    """
    处理 WebRTC 连接请求，生成 answer，并返回 sessionid
    """
    state = request.app["state"]
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    sessionid = params["sessionid"]
    logger.info(f"接收到offer请求 sessionid={sessionid}")

    try:
        async with state.offer_lock:
            await wait_for_session_cleanup(state, sessionid)
            if (
                sessionid in state.nerfreals
                or sessionid in state.instanceid_pc
                or sessionid in state.sessionid_ws
            ):
                await cleanup_session(
                    state,
                    sessionid,
                    reason="new offer replaces existing session",
                )
            await cleanup_old_sessions_for_new_offer(state, sessionid)

        # 创建数字人实例并添加到 session_manager
        nerfreal = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(
                None, build_nerfreal, sessionid, state.opt, state.model, state
            ),
            timeout=120.0,
        )

        async with state.offer_lock:
            state.nerfreals[sessionid] = nerfreal
            await cleanup_old_sessions_for_new_offer(state, sessionid)
        logger.info(
            f"数字人实例创建成功，已添加到nerfreals: sessionid={sessionid}, nerfreal={nerfreal}"
        )
    except asyncio.TimeoutError:
        logger.error(f"创建数字人实例超时: sessionid={sessionid}")
        if sessionid in state.nerfreals and state.nerfreals[sessionid] is not None:
            stop_nerfreal_instance(state.nerfreals[sessionid])
        state.nerfreals.pop(sessionid, None)
        return web.Response(
            content_type="application/json",
            text=json.dumps({"error": "创建数字人实例超时"}),
        )
    except Exception as e:
        logger.error(f"创建数字人实例失败: {str(e)}")
        if sessionid in state.nerfreals and state.nerfreals[sessionid] is not None:
            stop_nerfreal_instance(state.nerfreals[sessionid])
        state.nerfreals.pop(sessionid, None)
        return web.Response(
            content_type="application/json",
            text=json.dumps({"error": "创建数字人实例失败"}),
        )

    pc = RTCPeerConnection(configuration=RTCConfiguration())
    state.pcs.add(pc)

    state.instanceid_pc[sessionid] = pc
    disconnect_cleanup_task = None

    async def cleanup_after_grace():
        await asyncio.sleep(WEBRTC_DISCONNECT_GRACE)
        if pc.connectionState in ("disconnected", "failed", "closed"):
            await cleanup_session(
                state,
                sessionid,
                pc,
                f"webrtc {pc.connectionState} for {WEBRTC_DISCONNECT_GRACE:.1f}s",
            )

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        nonlocal disconnect_cleanup_task
        logger.info(f"连接状态 {pc.connectionState}")
        if pc.connectionState == "connected" and disconnect_cleanup_task:
            disconnect_cleanup_task.cancel()
            disconnect_cleanup_task = None
        elif pc.connectionState == "disconnected":
            if disconnect_cleanup_task is None or disconnect_cleanup_task.done():
                disconnect_cleanup_task = asyncio.create_task(cleanup_after_grace())
        elif pc.connectionState in ("failed", "closed"):
            if disconnect_cleanup_task:
                disconnect_cleanup_task.cancel()
                disconnect_cleanup_task = None
            await cleanup_session(state, sessionid, pc, f"webrtc {pc.connectionState}")

    player = HumanPlayer(state.nerfreals[sessionid])
    state.session_players[sessionid] = player
    pc.addTrack(player.audio)
    pc.addTrack(player.video)

    # 设置视频第一优先使用 H264 编解码器
    capabilities = RTCRtpSender.getCapabilities("video")
    preferences = list(filter(lambda x: x.name == "H264", capabilities.codecs))
    preferences += list(filter(lambda x: x.name == "VP8", capabilities.codecs))
    preferences += list(filter(lambda x: x.name == "rtx", capabilities.codecs))
    transceiver = pc.getTransceivers()[1]
    transceiver.setCodecPreferences(preferences)

    try:
        await pc.setRemoteDescription(offer)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
    except Exception as e:
        logger.error(f"设置WebRTC描述失败: {str(e)}")
        return web.Response(
            content_type="application/json",
            text=json.dumps({"error": "WebRTC描述错误"}),
        )
    response_content = json.dumps(
        {
            "sdp": pc.localDescription.sdp,
            "type": pc.localDescription.type,
            "sessionid": sessionid,
        }
    )
    return web.Response(content_type="application/json", text=response_content)


async def interrupt(request):
    """
    处理中断请求，暂停数字人对话
    """
    state = request.app["state"]
    params = await request.json()
    sessionid = params.get("sessionid", 0)
    if sessionid not in state.nerfreals:
        return web.json_response({"code": 404, "message": "无效的 sessionid"}, status=404)
    nerfreal = state.nerfreals[sessionid]
    if nerfreal is None:
        return web.json_response({"code": 400, "message": "数字人实例尚未初始化"}, status=400)
    if hasattr(nerfreal, "set_active_chat_trace"):
        nerfreal.set_active_chat_trace(None)
    logger.info(f"interrupt request: sessionid={sessionid}")
    nerfreal.flush_talk()

    return web.Response(
        content_type="application/json",
        text=json.dumps({"code": 0, "data": "ok"}),
    )


async def close_session(request):
    """
    前端页面刷新/关闭时主动释放当前数字人会话。
    """
    state = request.app["state"]
    try:
        params = await request.json()
    except Exception:
        try:
            params = json.loads(await request.text())
        except Exception:
            params = {}

    sessionid = str(params.get("sessionid") or "").strip()
    if not sessionid:
        return web.json_response({"code": 400, "message": "缺少必要参数: sessionid"}, status=400)

    if (
        sessionid not in state.nerfreals
        and sessionid not in state.instanceid_pc
        and sessionid not in state.sessionid_ws
    ):
        return web.json_response({"code": 0, "data": "already closed"})

    await cleanup_session(state, sessionid, reason="client requested close")
    return web.json_response({"code": 0, "data": "closed"})


async def human(request):
    """
    大模型回复接口
    处理用户发送的聊天或 echo 请求
    """
    state = request.app["state"]
    params = await request.json()

    # 手动校验 sessionid
    sessionid = params.get("sessionid", 0)
    if sessionid not in state.nerfreals:
        return web.json_response({"code": 404, "message": "无效的 sessionid"}, status=404)
    nerfreal = state.nerfreals[sessionid]
    if nerfreal is None:
        return web.json_response({"code": 400, "message": "数字人实例尚未初始化"}, status=400)

    # 手动校验 type 和 text 参数
    if "type" not in params:
        return web.json_response({"code": 400, "message": "缺少必要参数: type"}, status=400)
    if "text" not in params:
        return web.json_response({"code": 400, "message": "缺少必要参数: text"}, status=400)

    logger.info(f"会话ID: {sessionid}")

    # 处理中断请求
    if params.get("interrupt"):
        logger.info(
            f"human request interrupt=True sessionid={sessionid} type={params.get('type')}"
        )
        nerfreal.flush_talk()

    # 根据请求类型处理
    if params.get("type") == "echo":
        return await _handle_echo_request(params, sessionid, nerfreal, state)
    elif params.get("type") == "chat":
        return await _handle_chat_request(params, sessionid, nerfreal, state)
    else:
        return web.json_response(
            {"code": 400, "message": "不支持的请求类型"}, status=400
        )


async def _handle_echo_request(params, sessionid, nerfreal, state: AppState):
    """处理echo请求"""
    trace_id = params.get("trace_id") or uuid.uuid4().hex[:12]
    text = params["text"]
    logger.info(f"echo请求内容: {text}, trace_id={trace_id}, len={len(text)}")
    if hasattr(nerfreal, "set_active_chat_trace"):
        nerfreal.set_active_chat_trace(trace_id)
    log_timepoint(
        "TTS",
        "echo文本进入TTS",
        trace_id=trace_id,
        sessionid=sessionid,
        text_len=len(text),
    )
    log_perf(
        "trace",
        "echo_tts_dispatch",
        trace_id=trace_id,
        sessionid=sessionid,
        text_len=len(text),
    )
    nerfreal.put_msg_txt(text, trace_id=trace_id, segment_index=1)
    msg_id = trace_id

    ws = await _wait_for_session_ws(state, str(sessionid))
    if websocket_is_open(ws):
        await ws.send_json(
            {"data": text, "id": msg_id, "trace_id": trace_id, "finish": False}
        )
        await ws.send_json({"data": "", "id": msg_id, "trace_id": trace_id, "finish": True})
    else:
        logger.warning(f"echo文本未推送：WebSocket未就绪 sessionid={sessionid}, trace_id={trace_id}")

    return web.Response(
        content_type="application/json", text=json.dumps({"code": 0, "data": "ok"})
    )


async def _wait_for_session_ws(state: AppState, sessionid: str, timeout: float = 2.0):
    """首句问候可能比前端文本 WebSocket 早几毫秒到达，短暂等待后再推文本。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ws = state.sessionid_ws.get(sessionid)
        if websocket_is_open(ws):
            return ws
        await asyncio.sleep(0.05)
    ws = state.sessionid_ws.get(sessionid)
    return ws if websocket_is_open(ws) else None


def _get_llm_response():
    """根据 LLM_PROVIDER 环境变量选择 LLM 实现"""
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
    else:
        from llm.providers.aliyun import llm_response

    return llm_response


def _timed_llm_response(
    llm_response,
    message,
    nerfreal,
    sessionid,
    result_queue,
    trace_id=None,
):
    provider = os.environ.get("LLM_PROVIDER", "gongan")
    start = now()
    success = True
    try:
        log_perf(
            "trace",
            "llm_start",
            trace_id=trace_id,
            provider=provider,
            sessionid=sessionid,
            text_len=len(message),
        )
        log_timepoint(
            "LLM",
            "第一次请求",
            trace_id=trace_id,
            provider=provider,
            sessionid=sessionid,
            text_len=len(message),
            first_char=message[:1],
        )
        signature = inspect.signature(llm_response)
        if "trace_id" in signature.parameters:
            return llm_response(
                message,
                nerfreal,
                sessionid,
                result_queue,
                trace_id=trace_id,
            )
        return llm_response(message, nerfreal, sessionid, result_queue)
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
            text_len=len(message),
            device="external",
            trace_id=trace_id,
            success=success,
        )


async def _llm_response_consumer(state: AppState):
    """后台任务：消费 LLM 响应队列并发送 WebSocket"""
    while True:
        await asyncio.sleep(0.05)
        for sessionid in list(state.llm_response_queues.keys()):
            queue = state.llm_response_queues[sessionid]
            while not queue.empty():
                try:
                    ws = state.sessionid_ws.get(sessionid)
                    if not websocket_is_open(ws):
                        # 连接可能正处于短暂重连窗口，保留队列中的文本等待新连接。
                        break
                    msg_data = queue.get_nowait()
                    send_data = dict(msg_data)
                    enqueue_mono = send_data.pop("_perf_enqueued_mono", None)
                    trace_id = send_data.get("trace_id") or send_data.get("id")
                    finish = bool(send_data.get("finish"))
                    text = send_data.get("data") or ""
                    metric_key = f"{sessionid}:{trace_id}"
                    metric = state.llm_ws_metrics.setdefault(
                        metric_key,
                        {
                            "sessionid": sessionid,
                            "trace_id": trace_id,
                            "created_mono": now(),
                            "chunks": 0,
                            "chars": 0,
                            "first_send_logged": False,
                            "finish": False,
                        },
                    )
                    if text:
                        metric["chunks"] += 1
                        metric["chars"] += len(text)
                    send_start = now()
                    await ws.send_json(send_data)
                    send_duration_ms = elapsed_ms(send_start)
                    queue_delay_ms = (
                        elapsed_ms(enqueue_mono)
                        if isinstance(enqueue_mono, (int, float))
                        else None
                    )
                    if text and not metric.get("first_send_logged"):
                        metric["first_send_logged"] = True
                        log_timepoint(
                            "WebSocket",
                            "大模型首段文本发给前端",
                            trace_id=trace_id,
                            sessionid=sessionid,
                            text_len=len(text),
                            queue_delay_ms=(
                                f"{queue_delay_ms:.2f}"
                                if queue_delay_ms is not None
                                else None
                            ),
                        )
                        log_perf(
                            "trace",
                            "llm_first_ws_send",
                            send_duration_ms,
                            trace_id=trace_id,
                            sessionid=sessionid,
                            text_len=len(text),
                            queue_delay_ms=(
                                f"{queue_delay_ms:.2f}"
                                if queue_delay_ms is not None
                                else None
                            ),
                        )
                    elif text:
                        queue_delay_text = (
                            f"{queue_delay_ms:.2f}"
                            if queue_delay_ms is not None
                            else "unknown"
                        )
                        logger.debug(
                            f"[PIPELINE] llm_ws_chunk trace_id={trace_id} "
                            f"sessionid={sessionid} len={len(text)} "
                            f"send_ms={send_duration_ms:.2f} "
                            f"queue_delay_ms={queue_delay_text}"
                        )

                    if finish:
                        metric["finish"] = True
                        total_ms = elapsed_ms(metric.get("created_mono", now()))
                        log_perf(
                            "llm",
                            "ws_send_done",
                            total_ms,
                            trace_id=trace_id,
                            sessionid=sessionid,
                            chunks=metric.get("chunks"),
                            chars=metric.get("chars"),
                            queue_size=queue.qsize(),
                            websocket_ready=websocket_is_open(ws),
                        )
                        log_perf(
                            "trace",
                            "frontend_text_done",
                            total_ms,
                            trace_id=trace_id,
                            sessionid=sessionid,
                            chunks=metric.get("chunks"),
                            chars=metric.get("chars"),
                        )
                except asyncio.QueueEmpty:
                    break
                except Exception as e:
                    logger.error(f"发送WebSocket消息失败: {e}")


async def _handle_chat_request(params, sessionid, nerfreal, state: AppState):
    """处理chat请求"""
    llm_response = _get_llm_response()
    trace_id = params.get("trace_id") or uuid.uuid4().hex[:12]
    text = params["text"]
    if hasattr(nerfreal, "set_active_chat_trace"):
        nerfreal.set_active_chat_trace(trace_id)
    logger.info(
        f"chat请求进入LLM sessionid={sessionid}, trace_id={trace_id}, "
        f"text_len={len(text)}, provider={os.environ.get('LLM_PROVIDER', 'gongan')}"
    )
    log_timepoint(
        "LLM",
        "chat文本进入大模型",
        trace_id=trace_id,
        sessionid=sessionid,
        provider=os.environ.get("LLM_PROVIDER", "gongan"),
        text_len=len(text),
    )
    # 创建队列用于接收 LLM 响应
    result_queue = asyncio.Queue()
    state.llm_response_queues[sessionid] = result_queue

    # 注意：即使 ws 不存在，也应调用 LLM（结果通过数字人音频输出）
    asyncio.get_event_loop().run_in_executor(
        None,
        _timed_llm_response,
        llm_response,
        text,
        nerfreal,
        sessionid,
        result_queue,
        trace_id,
    )

    return web.Response(
        content_type="application/json", text=json.dumps({"code": 0, "data": "ok"})
    )


async def set_audiotype(request):
    """
    根据用户提供参数切换播放自定义视频
    """
    state = request.app["state"]
    params = await request.json()

    # 手动校验 sessionid
    sessionid = params.get("sessionid", 0)
    if sessionid not in state.nerfreals:
        return web.json_response({"code": 404, "message": "无效的 sessionid"}, status=404)
    nerfreal = state.nerfreals[sessionid]
    if nerfreal is None:
        return web.json_response({"code": 400, "message": "数字人实例尚未初始化"}, status=400)

    # 手动校验 audiotype 和 reinit 参数
    if "audiotype" not in params:
        return web.json_response({"code": 400, "message": "缺少必要参数: audiotype"}, status=400)
    if "reinit" not in params:
        return web.json_response({"code": 400, "message": "缺少必要参数: reinit"}, status=400)

    nerfreal.set_custom_state(params["audiotype"], params["reinit"])

    return web.Response(
        content_type="application/json", text=json.dumps({"code": 0, "msg": "ok"})
    )


async def is_speaking(request):
    """
    查询数字人是否正在说话
    """
    state = request.app["state"]
    params = await request.json()

    # 轮询接口不应在服务重启、旧页面残留 sessionid 时刷 404。
    # 真正需要强校验的 /human、/interrupt 仍然会返回明确错误。
    sessionid = params.get("sessionid", 0)
    if sessionid not in state.nerfreals:
        return web.json_response({"code": 0, "data": False})
    nerfreal = state.nerfreals[sessionid]
    if nerfreal is None:
        return web.json_response({"code": 0, "data": False})

    return web.Response(
        content_type="application/json",
        text=json.dumps({"code": 0, "data": nerfreal.is_speaking()}),
    )


async def list_sessions(request):
    """
    查询所有正在运行的sessionid
    """
    state = request.app["state"]
    try:
        # 获取所有活跃的sessionid
        active_sessions = list(state.nerfreals.keys())

        # 构建响应数据
        sessions_info = []
        for sessionid in active_sessions:
            session_info = {
                "sessionid": sessionid,
                "status": "active",
                "has_websocket": sessionid in state.sessionid_ws,
                "has_webrtc": sessionid in state.instanceid_pc,
            }
            sessions_info.append(session_info)

        return web.json_response(
            {
                "code": 0,
                "message": "查询成功",
                "total_sessions": len(active_sessions),
                "sessions": sessions_info,
            }
        )

    except Exception as e:
        logger.error(f"查询会话列表失败: {str(e)}")
        return web.json_response(
            {"code": 1, "message": f"查询会话列表失败: {str(e)}"}, status=500
        )


async def on_shutdown(app):
    """
    应用关闭时确保关闭所有连接与数字人实例
    """
    state = app["state"]
    logger.info("应用关闭信号触发，正在清理资源...")

    # 关闭所有WebRTC连接
    if state.pcs:
        logger.info(f"正在关闭 {len(state.pcs)} 个WebRTC连接...")
        coros = [pc.close() for pc in state.pcs]
        await asyncio.gather(*coros, return_exceptions=True)
        state.pcs.clear()

    # 关闭所有数字人实例
    if state.nerfreals:
        logger.info(f"正在关闭 {len(state.nerfreals)} 个数字人实例...")
        for sessionid, nerfreal in list(state.nerfreals.items()):
            if nerfreal:
                try:
                    stop_nerfreal_instance(nerfreal)
                except Exception as e:
                    logger.warning(f"关闭数字人实例 {sessionid} 时出错: {e}")
        state.nerfreals.clear()

    # 关闭WebSocket连接
    if state.sessionid_ws:
        logger.info(f"正在关闭 {len(state.sessionid_ws)} 个WebSocket连接...")
        for ws in state.sessionid_ws.values():
            try:
                ws.close()
            except Exception as e:
                logger.warning(f"关闭WebSocket连接时出错: {e}")
        state.sessionid_ws.clear()

    # 清理LLM响应队列
    if state.llm_response_queues:
        logger.info(f"正在清理 {len(state.llm_response_queues)} 个LLM响应队列...")
        state.llm_response_queues.clear()

    logger.info("应用资源清理完成")


async def post(url, data):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data) as response:
                return await response.text()
    except aiohttp.ClientError as e:
        logger.info(f"Error: {e}")


# aiohttp WebSocket 处理函数 - 统一使用 aiohttp
async def ws_handler(request: web.Request) -> web.StreamResponse:
    """aiohttp WebSocket 处理 - 负责和前端交互的消息推送"""
    sessionid = request.match_info.get("sessionid")
    state = request.app["state"]
    logger.info(f"WebSocket连接请求 sessionid={sessionid}")

    # 检查会话是否存在且有效
    if sessionid not in state.nerfreals or not state.nerfreals[sessionid]:
        logger.warning(f"WebSocket连接尝试但数字人实例不存在 sessionid={sessionid}")
        return web.Response(status=404, text="Session not found")

    ws = web.WebSocketResponse()
    await ws.prepare(request)

    previous_ws, ws_epoch = claim_websocket(
        state.sessionid_ws, state.sessionid_ws_epochs, sessionid, ws
    )
    logger.info(
        f"WebSocket连接已登记 sessionid={sessionid}, epoch={ws_epoch}, "
        f"replaced={previous_ws is not None}"
    )
    if previous_ws is not ws and websocket_is_open(previous_ws):
        try:
            await previous_ws.close(
                code=1000, message=b"replaced by a newer websocket"
            )
        except Exception as e:
            logger.warning(
                f"关闭被替换的 WebSocket 失败 sessionid={sessionid}: {e}"
            )

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                if msg.data == "ping":
                    continue
            elif msg.type == web.WSMsgType.ERROR:
                logger.error(f"WebSocket错误: {ws.exception()}")
    finally:
        released = release_websocket(
            state.sessionid_ws,
            state.sessionid_ws_epochs,
            sessionid,
            ws,
            ws_epoch,
        )
        logger.warning(
            f"WebSocket连接关闭 sessionid={sessionid}, epoch={ws_epoch}, "
            f"owns_current_slot={released}"
        )
        if released:
            # 短暂保留 LLM 队列供同一会话重连；超时后由统一会话清理回收。
            asyncio.create_task(
                cleanup_after_ws_close(state, sessionid, ws_epoch)
            )

    return ws


async def audio_ws_handler(request: web.Request) -> web.StreamResponse:
    """接收前端 PCM 音频流，驱动 VAD + ASR"""
    sessionid = request.match_info.get("sessionid")
    state = request.app["state"]

    if sessionid not in state.nerfreals:
        logger.warning(
            f"[PIPELINE] audio_ws_reject session={sessionid} "
            f"remote={request.remote} reason=session_not_found"
        )
        return web.Response(status=404, text="Session not found")

    ws = web.WebSocketResponse()
    await ws.prepare(request)
    connect_mono = now()
    frames = 0
    total_bytes = 0
    first_binary_logged = False
    last_metrics_mono = connect_mono
    logger.info(
        f"[PIPELINE] audio_ws_connected session={sessionid} "
        f"remote={request.remote}"
    )

    handler = ASRSessionHandler(
        session_id=sessionid, state=state, ws=state.sessionid_ws.get(sessionid)
    )
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.BINARY:
                frames += 1
                total_bytes += len(msg.data)
                current = now()
                if not first_binary_logged:
                    first_binary_logged = True
                    logger.info(
                        f"[PIPELINE] audio_ws_first_binary session={sessionid} "
                        f"bytes={len(msg.data)} elapsed_ms={elapsed_ms(connect_mono):.2f}"
                    )
                if frames <= 3 or current - last_metrics_mono >= 5.0:
                    last_metrics_mono = current
                    logger.debug(
                        f"[PIPELINE] audio_ws_recv_metrics session={sessionid} "
                        f"frames={frames} bytes={total_bytes} "
                        f"last_frame_bytes={len(msg.data)} "
                        f"elapsed_ms={elapsed_ms(connect_mono):.2f}"
                    )
                await handler.on_audio_chunk(msg.data)
            elif msg.type == web.WSMsgType.TEXT:
                logger.debug(
                    f"[PIPELINE] audio_ws_text session={sessionid} "
                    f"data={msg.data[:120]!r}"
                )
            elif msg.type in (web.WSMsgType.ERROR, web.WSMsgType.CLOSE):
                logger.warning(
                    f"[PIPELINE] audio_ws_close_msg session={sessionid} "
                    f"type={msg.type} exception={ws.exception()}"
                )
                break
    finally:
        await handler.close()
        logger.info(
            f"[PIPELINE] audio_ws_closed session={sessionid} "
            f"frames={frames} bytes={total_bytes} "
            f"duration_ms={elapsed_ms(connect_mono):.2f} "
            f"close_code={getattr(ws, 'close_code', None)} "
            f"exception={ws.exception()}"
        )

    return ws


async def update_config(request: web.Request):
    """
    根据用户 sessionid 更新数字人、背景和音色配置
    """
    state = request.app["state"]
    try:
        data = await request.json()
        required_keys = [
            "sessionid",
            "digital_human_id",
            "voice_type",
            "background_image",
        ]
        if not all(key in data for key in required_keys):
            return web.json_response({"message": "缺少必要参数"}, status=400)

        sessionid = data.get("sessionid")
        digital_human_id = data.get("digital_human_id")
        voice_type = data.get("voice_type")
        background_image = data.get("background_image")

        base_path = os.getcwd()
        avatar_id_path = os.path.join(
            base_path, f"data/avatars/wav2lip_avatar{digital_human_id}"
        )
        REF_FILE = os.path.join(base_path, f"data/ref_audios/{voice_type}.wav")
        BACKGROUND_IMAGE = os.path.join(
            base_path, f"data/customimage/{background_image}.png"
        )

        resources = {
            "模板": (os.path.isdir, avatar_id_path),
            "音色文件": (os.path.isfile, REF_FILE),
            "背景图片": (os.path.isfile, BACKGROUND_IMAGE),
        }
        for name, (check_func, path) in resources.items():
            if not check_func(path):
                return web.json_response({"message": f"{name}不存在"}, status=404)

        configs = ConfigManager.get_configs()
        if "sessions" not in configs:
            configs["sessions"] = {}
        configs["sessions"][sessionid] = {
            "avatar_id": f"wav2lip_avatar{digital_human_id}",
            "ref_file": REF_FILE,
            "bg_img": BACKGROUND_IMAGE,
        }
        ConfigManager.save_configs(configs)

        if sessionid in state.nerfreals:
            new_avatar = load_avatar(f"wav2lip_avatar{digital_human_id}")
            state.nerfreals[sessionid].change_avatar(new_avatar)
            state.nerfreals[sessionid].update_bg_img(BACKGROUND_IMAGE)

            state.nerfreals[sessionid].opt.REF_FILE = REF_FILE

        return web.json_response({"message": "设置已更新"})
    except Exception as e:
        logger.error(f"设置资源失败: {str(e)}")
        return web.json_response({"message": "服务器内部错误"}, status=500)


async def run(push_url, sessionid, state: AppState):
    nerfreal = await asyncio.get_event_loop().run_in_executor(
        None, build_nerfreal, sessionid, state.opt, state.model, state
    )
    state.nerfreals[sessionid] = nerfreal

    pc = RTCPeerConnection()
    state.pcs.add(pc)
    state.instanceid_pc[sessionid] = pc
    disconnect_cleanup_task = None

    async def cleanup_after_grace():
        await asyncio.sleep(WEBRTC_DISCONNECT_GRACE)
        if pc.connectionState in ("disconnected", "failed", "closed"):
            await cleanup_session(
                state,
                sessionid,
                pc,
                f"rtcpush {pc.connectionState} for {WEBRTC_DISCONNECT_GRACE:.1f}s",
            )

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        nonlocal disconnect_cleanup_task
        logger.info("Connection state is %s" % pc.connectionState)
        if pc.connectionState == "connected" and disconnect_cleanup_task:
            disconnect_cleanup_task.cancel()
            disconnect_cleanup_task = None
        elif pc.connectionState == "disconnected":
            if disconnect_cleanup_task is None or disconnect_cleanup_task.done():
                disconnect_cleanup_task = asyncio.create_task(cleanup_after_grace())
        elif pc.connectionState in ("failed", "closed"):
            if disconnect_cleanup_task:
                disconnect_cleanup_task.cancel()
                disconnect_cleanup_task = None
            await cleanup_session(state, sessionid, pc, f"rtcpush {pc.connectionState}")

    player = HumanPlayer(state.nerfreals[sessionid])
    state.session_players[sessionid] = player
    audio_sender = pc.addTrack(player.audio)
    video_sender = pc.addTrack(player.video)

    await pc.setLocalDescription(await pc.createOffer())
    answer = await post(push_url, pc.localDescription.sdp)
    await pc.setRemoteDescription(RTCSessionDescription(sdp=answer, type="answer"))


if __name__ == "__main__":
    try:
        current_start_method = mp.get_start_method(allow_none=True)
        if current_start_method is None:
            mp.set_start_method("spawn")
            logger.info("multiprocessing start_method set to spawn")
        else:
            logger.info(
                f"multiprocessing start_method already set: {current_start_method}"
            )
    except RuntimeError as exc:
        logger.warning(f"multiprocessing start_method setup skipped: {exc}")
    parser = argparse.ArgumentParser(description="Realtime Digital Human 应用参数说明")
    parser.add_argument("--fps", type=int, default=50, help="音频每秒帧数")
    parser.add_argument("-l", type=int, default=10, help="滑动窗口左侧长度，单位20ms")
    parser.add_argument("-m", type=int, default=8, help="滑动窗口中间长度，单位20ms")
    parser.add_argument("-r", type=int, default=10, help="滑动窗口右侧长度，单位20ms")

    # parser.add_argument('--transport', type=str, default='rtcpush') #webrtc rtcpush virtualcam

    parser.add_argument(
        "--avatar_id",
        type=str,
        # default='wav2lip_avatar2',
        default="wav2lip_avatar11",
        help="头像ID",
    )
    parser.add_argument("--bbox_shift", type=int, default=5, help="边界框偏移")
    parser.add_argument("--batch_size", type=int, default=4, help="批处理大小")
    parser.add_argument(
        "--customvideo_config", type=str, default="", help="自定义视频配置文件路径"
    )
    parser.add_argument(
        "--bg_img",
        type=str,
        # default='/Data1/home/lishuang/realtime-digitalhuman/data/customimage/2.png',
        # default='./data/customimage/2.png',
        default="./data/customimage/4.png",
        help="背景图片路径",
    )

    parser.add_argument(
        "--model", type=str, default="wav2lip"
    )  # musetalk wav2lip ultralight

    parser.add_argument(
        "--model_path",
        type=str,
        default="./wav2lip256/wav2lip.pth",
        help="wav2lip模型权重文件路径",
    )
    parser.add_argument(
        "--wav2lip_size", type=int, default=256, help="wavlip处理图像大小"
    )
    parser.add_argument(
        "--wav2lip_backend",
        type=str,
        default=os.getenv("WAV2LIP_BACKEND", "pytorch"),
        choices=["pytorch", "tensorrt", "trt"],
        help="Wav2Lip推理后端：pytorch 或 tensorrt",
    )
    parser.add_argument(
        "--wav2lip_engine_path",
        type=str,
        default=os.getenv("WAV2LIP_ENGINE_PATH", "./wav2lip256/wav2lip_fp16.engine"),
        help="TensorRT engine文件路径，仅wav2lip_backend=tensorrt时使用",
    )
    parser.add_argument(
        "--tts",
        type=str,
        default=os.environ.get("TTS_PROVIDER", "gongantts"),
        choices=[
            "edgetts",
            "gpt-sovits",
            "gpt-sovits-v2",
            "cosyvoice",
            "fishtts",
            "sparktts",
            "flashtts",
            "iflytts",
            "gongantts",
        ],
        help="语音合成类型",
    )
    parser.add_argument(
        "--REF_FILE",
        type=str,
        # default="/Data1/home/lishuang/realtime-digitalhuman/data/ref_audios/1.wav",
        # default="./data/ref_audios/1.wav",
        default="./data/ref_audios/2.wav",
        help="参考音频文件路径",
    )
    parser.add_argument(
        "--REF_TEXT",
        type=str,
        default="先帝创业未半而中道崩殂，今天下三分，益州疲弊，此诚危急存亡之秋也。",
        help="参考文本",
    )
    parser.add_argument(
        "--TTS_SERVER",
        type=str,
        default=os.environ.get("TTS_SERVER", "http://127.0.0.1:9880"),
        help="TTS服务器地址",
    )
    parser.add_argument(
        "--transport", type=str, default="rtcpush"
    )  # webrtc rtcpush virtualcam
    parser.add_argument("--max_session", type=int, default=2, help="最大会话数")
    parser.add_argument(
        "--listenport",
        type=int,
        default=int(os.environ.get("LISTEN_PORT", 8010)),
        help="监听端口号",
    )

    opt = parser.parse_args()

    if opt.model == "wav2lip":
        from lipreal import LipReal, load_model, load_avatar, warm_up

        logger.info(opt)
        model = load_model(
            opt.model_path,
            backend=opt.wav2lip_backend,
            engine_path=opt.wav2lip_engine_path,
            batch_size=opt.batch_size,
            modelres=opt.wav2lip_size,
        )
        avatar = load_avatar(opt.avatar_id)
        warm_up(opt.batch_size, model, opt.wav2lip_size)

    opt.customopt = []
    if opt.customvideo_config != "":
        with open(opt.customvideo_config, "r", encoding="utf-8") as file:
            opt.customopt = json.load(file)

    # 创建 AppState 并初始化
    state = AppState()
    state.opt = opt
    state.model = model
    state.avatar = avatar

    appasync = web.Application(client_max_size=1024**2 * 100)
    appasync.on_shutdown.append(on_shutdown)
    # 将状态容器添加到app上下文中
    appasync["state"] = state
    appasync.router.add_post("/generate_session", generate_session)
    appasync.router.add_post("/offer", offer)
    appasync.router.add_post("/human", human)
    appasync.router.add_post("/interrupt", interrupt)
    appasync.router.add_post("/client_metrics", client_metrics)
    appasync.router.add_post("/close_session", close_session)
    appasync.router.add_post("/set_audiotype", set_audiotype)
    appasync.router.add_post("/is_speaking", is_speaking)
    appasync.router.add_get("/list_sessions", list_sessions)
    appasync.router.add_static("/", path="web")

    appasync.router.add_get("/health", health_check)
    # get 查询服务通过模型预热
    appasync.router.add_get("/ready", ready)


    # aiohttp WebSocket 路由
    appasync.router.add_get("/ws/{sessionid}", ws_handler)
    appasync.router.add_get("/ws-audio/{sessionid}", audio_ws_handler)
    appasync.router.add_get("/humanaudio/{sessionid}", audio_ws_handler)

    appasync.router.add_post("/update_config", update_config)

    cors = aiohttp_cors.setup(
        appasync,
        defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*",
            )
        },
    )
    for route in list(appasync.router.routes()):
        cors.add(route)

    pagename = "webrtcapi.html"
    if opt.transport == "rtmp":
        pagename = "echoapi.html"
    elif opt.transport == "rtcpush":
        pagename = "rtcpushapi.html"
    logger.info(
        "start http server; http://<serverip>:" + str(opt.listenport) + "/" + pagename
    )
    logger.info(
        "如果使用webrtc，推荐访问webrtc集成前端: http://<serverip>:"
        + str(opt.listenport)
        + "/dashboard.html"
    )

    def run_server(runner):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        _llm_consumer_task = None
        _server_metrics_task = None

        try:
            loop.run_until_complete(runner.setup())
            site = web.TCPSite(runner, "0.0.0.0", opt.listenport)
            loop.run_until_complete(site.start())

            # 启动 LLM 响应消费者任务（后台任务，不阻塞事件循环）
            _llm_consumer_task = asyncio.ensure_future(_llm_response_consumer(state))
            if SERVER_METRICS_ENABLED:
                _server_metrics_task = asyncio.ensure_future(_server_metrics_loop(state))

            if opt.transport == "rtcpush":
                for k in range(opt.max_session):
                    push_url = opt.push_url
                    if k != 0:
                        push_url = opt.push_url + str(k)
                    loop.run_until_complete(run(push_url, k, state))

            logger.info(f"服务器已启动在 0.0.0.0:{opt.listenport}")
            logger.info("按 Ctrl-C 退出")

            loop.run_forever()

        except KeyboardInterrupt:
            logger.info("接收到关闭信号，正在优雅关闭...")
        finally:
            # 执行清理操作
            logger.info("正在清理资源...")

            # 取消 LLM 消费者后台任务
            if _llm_consumer_task is not None and not _llm_consumer_task.done():
                _llm_consumer_task.cancel()
                try:
                    loop.run_until_complete(_llm_consumer_task)
                except asyncio.CancelledError:
                    pass

            if _server_metrics_task is not None and not _server_metrics_task.done():
                _server_metrics_task.cancel()
                try:
                    loop.run_until_complete(_server_metrics_task)
                except asyncio.CancelledError:
                    pass

            # 关闭所有WebRTC连接
            if state.pcs:
                logger.info(f"正在关闭 {len(state.pcs)} 个WebRTC连接...")
                close_tasks = [pc.close() for pc in state.pcs]
                if close_tasks:
                    loop.run_until_complete(
                        asyncio.gather(*close_tasks, return_exceptions=True)
                    )
                state.pcs.clear()

            # 关闭所有数字人实例
            if state.nerfreals:
                logger.info(f"正在关闭 {len(state.nerfreals)} 个数字人实例...")
                for sessionid, nerfreal in list(state.nerfreals.items()):
                    if nerfreal:
                        try:
                            stop_nerfreal_instance(nerfreal)
                        except Exception as e:
                            logger.warning(f"关闭数字人实例 {sessionid} 时出错: {e}")
                state.nerfreals.clear()

            # 关闭WebSocket连接
            if state.sessionid_ws:
                logger.info(f"正在关闭 {len(state.sessionid_ws)} 个WebSocket连接...")
                for ws in state.sessionid_ws.values():
                    try:
                        ws.close()
                    except Exception as e:
                        logger.warning(f"关闭WebSocket连接时出错: {e}")
                state.sessionid_ws.clear()

            # 关闭aiohttp runner
            logger.info("正在关闭aiohttp服务器...")
            loop.run_until_complete(runner.cleanup())

            # 关闭事件循环
            logger.info("正在关闭事件循环...")
            loop.close()

            logger.info("服务器已优雅关闭")

    run_server(web.AppRunner(appasync))
