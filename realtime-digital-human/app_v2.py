import os
import time
import json
import inspect
from typing import Dict
import uuid
import asyncio
import argparse
import torch.multiprocessing as mp
from dotenv import load_dotenv

# 加载 .env 环境变量
load_dotenv()

from tomlkit import dumps, parse

from lipreal import LipReal, load_model, load_avatar, warm_up
from basereal import BaseReal
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
from perf_logger import elapsed_ms, log_perf, now, perf_timer


class AppState:
    def __init__(self):
        self.nerfreals: Dict[str, BaseReal] = {}
        self.pcs: set = set()
        self.instanceid_pc: Dict[str, RTCPeerConnection] = {}
        self.sessionid_ws: Dict[str, web.WebSocketResponse] = {}
        self.opt = None
        self.model = None
        self.avatar = None
        self.llm_response_queues: Dict[str, asyncio.Queue] = {}


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


async def health_check(request):
    """检查服务状态"""
    return web.json_response({"code": 0, "message": "服务正常"})

async def ready(request):
    """查询服务是否已经完全启动（包括模型已经预热）"""
    return web.json_response({"status": 1})

def build_nerfreal(session_id, opt, model, state: AppState):
    """
    创建并返回一个 LipReal 实例
    """
    with perf_timer("business", "build_nerfreal", sessionid=session_id, model=opt.model):
        opt.sessionid = session_id
        if opt.model == "wav2lip":
            from lipreal import LipReal

            nerfreal = LipReal(opt, state.model, state.avatar)
        return nerfreal

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
    request_start = now()
    state = request.app["state"]
    parse_start = now()
    params = await request.json()
    parse_duration_ms = elapsed_ms(parse_start)
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    sessionid = params["sessionid"]
    logger.info(f"接收到offer请求 sessionid={sessionid}")

    try:
        build_start = now()
        # 创建数字人实例并添加到 session_manager
        nerfreal = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(
                None, build_nerfreal, sessionid, state.opt, state.model, state
            ),
            timeout=120.0,
        )
        build_duration_ms = elapsed_ms(build_start)

        state.nerfreals[sessionid] = nerfreal
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

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        logger.info(f"连接状态 {pc.connectionState}")
        # 开始清理会话
        if pc.connectionState == "failed" or pc.connectionState == "closed":
            if sessionid in state.nerfreals and state.nerfreals[sessionid] is not None:
                stop_nerfreal_instance(state.nerfreals[sessionid])
            state.nerfreals.pop(sessionid, None)
            state.pcs.discard(pc)
            state.instanceid_pc.pop(sessionid, None)

    player = HumanPlayer(state.nerfreals[sessionid])
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
        webrtc_start = now()
        await pc.setRemoteDescription(offer)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        webrtc_duration_ms = elapsed_ms(webrtc_start)
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
    log_perf(
        "business",
        "offer",
        elapsed_ms(request_start),
        sessionid=sessionid,
        parse_ms=f"{parse_duration_ms:.2f}",
        build_nerfreal_ms=f"{build_duration_ms:.2f}",
        webrtc_ms=f"{webrtc_duration_ms:.2f}",
        device="cpu",
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
    nerfreal.flush_talk()

    return web.Response(
        content_type="application/json",
        text=json.dumps({"code": 0, "data": "ok"}),
    )


async def human(request):
    """
    大模型回复接口
    处理用户发送的聊天或 echo 请求
    """
    request_start = now()
    state = request.app["state"]
    parse_start = now()
    params = await request.json()
    parse_duration_ms = elapsed_ms(parse_start)

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
    log_perf(
        "business",
        "human_validate",
        elapsed_ms(request_start),
        sessionid=sessionid,
        request_type=params.get("type"),
        parse_ms=f"{parse_duration_ms:.2f}",
        text_len=len(params.get("text", "")),
        device="cpu",
    )

    # 处理中断请求
    if params.get("interrupt"):
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
    start = now()
    logger.info(f"echo请求内容: {params['text']}")
    nerfreal.put_msg_txt(params["text"])
    msg_id = str(uuid.uuid4())

    # 发送WebSocket消息 - 使用 aiohttp WebSocket 协程方法
    ws = state.sessionid_ws.get(str(sessionid), None)
    if ws:
        await ws.send_json({"data": params["text"], "id": msg_id, "finish": False})
        await ws.send_json({"data": "", "id": msg_id, "finish": True})

    response = web.Response(
        content_type="application/json", text=json.dumps({"code": 0, "data": "ok"})
    )
    log_perf(
        "business",
        "echo",
        elapsed_ms(start),
        sessionid=sessionid,
        text_len=len(params["text"]),
        device="cpu",
    )
    return response


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
                    msg_data = queue.get_nowait()
                    ws = state.sessionid_ws.get(sessionid)
                    if ws:
                        await ws.send_json(msg_data)
                except asyncio.QueueEmpty:
                    break
                except Exception as e:
                    logger.error(f"发送WebSocket消息失败: {e}")


async def _handle_chat_request(params, sessionid, nerfreal, state: AppState):
    """处理chat请求"""
    start = now()
    trace_id = params.get("trace_id") or uuid.uuid4().hex[:12]
    if hasattr(nerfreal, "set_active_chat_trace"):
        nerfreal.set_active_chat_trace(trace_id)
    llm_response = _get_llm_response()
    # 创建队列用于接收 LLM 响应
    result_queue = asyncio.Queue()
    state.llm_response_queues[sessionid] = result_queue

    # 注意：即使 ws 不存在，也应调用 LLM（结果通过数字人音频输出）
    asyncio.get_event_loop().run_in_executor(
        None,
        _timed_llm_response,
        llm_response,
        params["text"],
        nerfreal,
        sessionid,
        result_queue,
        trace_id,
    )

    response = web.Response(
        content_type="application/json", text=json.dumps({"code": 0, "data": "ok"})
    )
    log_perf(
        "business",
        "chat_dispatch",
        elapsed_ms(start),
        sessionid=sessionid,
        provider=os.environ.get("LLM_PROVIDER", "gongan"),
        text_len=len(params["text"]),
        trace_id=trace_id,
        device="cpu",
    )
    log_perf(
        "trace",
        "chat_dispatched",
        elapsed_ms(start),
        trace_id=trace_id,
        sessionid=sessionid,
        text_len=len(params["text"]),
    )
    return response


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

    # 手动校验 sessionid
    sessionid = params.get("sessionid", 0)
    if sessionid not in state.nerfreals:
        return web.json_response({"code": 404, "message": "无效的 sessionid"}, status=404)
    nerfreal = state.nerfreals[sessionid]
    if nerfreal is None:
        return web.json_response({"code": 400, "message": "数字人实例尚未初始化"}, status=400)

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

    state.sessionid_ws[sessionid] = ws

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                if msg.data == "ping":
                    continue
            elif msg.type == web.WSMsgType.ERROR:
                logger.error(f"WebSocket错误: {ws.exception()}")
    finally:
        logger.warning(f"WebSocket连接关闭 sessionid={sessionid}")
        state.sessionid_ws.pop(sessionid, None)
        state.llm_response_queues.pop(sessionid, None)

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

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        logger.info("Connection state is %s" % pc.connectionState)
        if pc.connectionState == "failed":
            await pc.close()
            state.pcs.discard(pc)

    player = HumanPlayer(state.nerfreals[sessionid])
    audio_sender = pc.addTrack(player.audio)
    video_sender = pc.addTrack(player.video)

    await pc.setLocalDescription(await pc.createOffer())
    answer = await post(push_url, pc.localDescription.sdp)
    await pc.setRemoteDescription(RTCSessionDescription(sdp=answer, type="answer"))


if __name__ == "__main__":
    mp.set_start_method("spawn")
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
    parser.add_argument("--batch_size", type=int, default=16, help="批处理大小")
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
        "--tts",
        type=str,
        default="flashtts",
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
            "gywttts",
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
        default=os.getenv("TTS_SERVER", "http://localhost:8779"),
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
        model = load_model(opt.model_path)
        avatar = load_avatar(opt.avatar_id)
        warm_up(opt.batch_size, model, 256)

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
    appasync.router.add_post("/set_audiotype", set_audiotype)
    appasync.router.add_post("/is_speaking", is_speaking)
    appasync.router.add_get("/list_sessions", list_sessions)
    appasync.router.add_static("/", path="web")

    appasync.router.add_get("/health", health_check)
    # get 查询服务通过模型预热
    appasync.router.add_get("/ready", ready)


    # aiohttp WebSocket 路由
    appasync.router.add_get("/ws/{sessionid}", ws_handler)

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

        try:
            loop.run_until_complete(runner.setup())
            site = web.TCPSite(runner, "0.0.0.0", opt.listenport)
            loop.run_until_complete(site.start())

            # 启动 LLM 响应消费者任务
            loop.run_until_complete(asyncio.ensure_future(_llm_response_consumer(state)))

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
