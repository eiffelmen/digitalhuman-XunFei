from fastapi import FastAPI, BackgroundTasks,WebSocket, WebSocketDisconnect, Request
from pydantic import BaseModel
from device_service import DeviceService
from device_state import DeviceState
import httpx
import asyncio
import json
import time

from app.services.connection_manager import (
    ConnectionManager,
    ConnectionScope,
    resolve_connection_manager,
)

device_service = DeviceService()
device_state = DeviceState()

app = FastAPI()

import os
service_url = os.getenv("SERVICE_URL", "http://localhost:8010")


class RegisterItem(BaseModel):
    deviceid: str
    webid: str


class DeviceItem(BaseModel):
    deviceid: str


class ASRResultItem(BaseModel):
    deviceid: str
    result: str

def _get_connection_manager_from_ws(websocket: WebSocket) -> ConnectionManager:
    return resolve_connection_manager(websocket.app)


def _get_connection_manager_from_request(request: Request) -> ConnectionManager:
    return resolve_connection_manager(request.app)


def _resolve_scope(client_type: str) -> ConnectionScope | None:
    mapping = {
        "app": ConnectionScope.APP,
        "web": ConnectionScope.WEB,
    }
    return mapping.get(client_type)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # 解析连接参数
    client_type = websocket.query_params.get("type")  # 'app' or 'web'
    client_id = websocket.query_params.get("id")      # deviceId 或 userId
    print(f"/ws 新连接请求: type={client_type}, id={client_id}")


    if not client_type or not client_id:
        await websocket.close(code=4000)
        return

    scope = _resolve_scope(client_type)
    if not scope:
        await websocket.close(code=4001)
        return

    await websocket.accept()
    manager = _get_connection_manager_from_ws(websocket)
    connection_key = await manager.register(scope, client_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # 增加 JSON 解析容错，防止客户端发送非 JSON 字符串（例如 "[object Object]"）导致抛出异常
            try:
                msg = json.loads(data)
            except Exception as e:
                print(f"JSON解析失败: {e}, 原始消息: {data}")
                # 保护性处理：将原始文本封装为 dict，避免后续 .get 调用报错
                continue
            if msg.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                continue

            print(f"来自 {connection_key} 的消息: {data}")
            if client_type == "web":
                if msg.get("type") == "msg2app":
                    # 兼容不同字段命名
                    device_id = msg.get("userId")
                    print(f"send to app {device_id}: {json.dumps(msg)}")
                    if device_id:
                        await manager.send(ConnectionScope.APP, device_id, json.dumps(msg))
            elif client_type == "app":
                if msg.get("type") == "msg2web":
                    deviceid = msg.get("deviceid")
                    print(f"send to web {deviceid}: {json.dumps(msg)}")
                    if deviceid:
                        await manager.send(ConnectionScope.WEB, deviceid, json.dumps(msg))

    except WebSocketDisconnect:
        await manager.unregister_by_key(connection_key)
        print(f"{connection_key} 已断开")

@app.websocket("/ws/web")
async def web_subscriber(websocket: WebSocket):
    """
    浏览器端订阅 ASR 或其他消息
    """
    client_id = websocket.query_params.get("id")
    print(f"/ws/web Web 客户端连接请求: id={client_id}")
    if not client_id:
        await websocket.close(code=4000)
        return

    await websocket.accept()
    manager = _get_connection_manager_from_ws(websocket)
    connection_key = await manager.register(ConnectionScope.NEW_WEB, client_id, websocket)
    print(f"Web 客户端 {client_id} 已连接")

    try:
        while True:
            data = await websocket.receive_text()
            if not data:
                continue
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                print(f"Web 客户端 {client_id} 发送了无法解析的数据: {data}")
                continue

            if msg.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        print(f"Web 客户端 {client_id} 已断开")
    except Exception as e:
        print(f"Web 客户端 {client_id} 通道异常: {e}")
    finally:
        await manager.unregister_by_key(connection_key)

@app.websocket("/ws/asr_ifly")
async def asr_ws(websocket: WebSocket):
    """
    Jetson 设备上行实时 ASR 结果，并转发给目标 Web 端
    """
    await websocket.accept()
    device_id = websocket.query_params.get("deviceid") or "unknown"
    print(f"ASR 设备 {device_id} 已连接")

    manager = _get_connection_manager_from_ws(websocket)
    
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                print(f"ASR 数据无法解析 JSON，已忽略: {raw}")
                continue

            print(f"ASR 数据: {data}")
            text = data.get("text")
            target_id = data.get("target_id") or device_id
            
            # 如果文本为空，清空缓存并发送空数据
            if not text:
                print(f"ASR 数据text字段为空，清空缓存并发送空数据: {data}")
                msg = {
                    "type": "asr",
                    "deviceid": device_id,
                    "text": "",
                    "timestamp": data.get("timestamp", time.time()),
                    "meta": data.get("meta", {}),
                }
                print(f"ASR -> web {target_id}: {json.dumps(msg, ensure_ascii=False)}")
                await manager.send(ConnectionScope.NEW_WEB, target_id, json.dumps(msg))
                continue
            
            msg = {
                "type": "asr",
                "deviceid": device_id,
                "text": text,
                "timestamp": data.get("timestamp", time.time()),
                "meta": data.get("meta", {}),
            }

            print(f"ASR -> web {target_id}: {json.dumps(msg, ensure_ascii=False)}")
            await manager.send(ConnectionScope.NEW_WEB, target_id, json.dumps(msg))
    except WebSocketDisconnect:
        print(f"ASR 设备 {device_id} 已断开")
    except Exception as e:
        print(f"ASR WebSocket 通道异常: {e}")

@app.websocket("/ws/asr")
async def asr_ws(websocket: WebSocket):
    """
    Jetson 设备上行实时 ASR 结果，并转发给目标 Web 端
    """
    await websocket.accept()
    device_id = websocket.query_params.get("deviceid") or "unknown"
    print(f"ASR 设备 {device_id} 已连接")

    manager = _get_connection_manager_from_ws(websocket)
    # 为每个目标维护 ASR 文本缓存
    asr_cache = {}
    
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                print(f"ASR 数据无法解析 JSON，已忽略: {raw}")
                continue

            print(f"ASR 数据: {data}")
            text = data.get("text")
            target_id = data.get("target_id") or device_id
            
            # 如果文本为空，清空缓存并发送空数据
            if not text:
                print(f"ASR 数据text字段为空，清空缓存并发送空数据: {data}")
                asr_cache[target_id] = ""
                msg = {
                    "type": "asr",
                    "deviceid": device_id,
                    "text": "",
                    "timestamp": data.get("timestamp", time.time()),
                    "meta": data.get("meta", {}),
                }
                print(f"ASR -> web {target_id}: {json.dumps(msg, ensure_ascii=False)}")
                await manager.send(ConnectionScope.NEW_WEB, target_id, json.dumps(msg))
                continue
            
            # 文本不为空，与缓存叠加
            cached_text = asr_cache.get(target_id, "")
            accumulated_text = cached_text + text
            asr_cache[target_id] = accumulated_text
            
            msg = {
                "type": "asr",
                "deviceid": device_id,
                "text": accumulated_text,
                "timestamp": data.get("timestamp", time.time()),
                "meta": data.get("meta", {}),
            }

            print(f"ASR -> web {target_id}: {json.dumps(msg, ensure_ascii=False)}")
            await manager.send(ConnectionScope.NEW_WEB, target_id, json.dumps(msg))
    except WebSocketDisconnect:
        print(f"ASR 设备 {device_id} 已断开")
        # 清理该设备的缓存
        if device_id in asr_cache:
            del asr_cache[device_id]
    except Exception as e:
        print(f"ASR WebSocket 通道异常: {e}")

hasFace = False

@app.get("/getHasFace")
def get_has_face():
    """
    获取 hasFace 的当前值
    """
    return {"hasFace": hasFace}

@app.post("/updateHasFace")
async def update_has_face(request: Request):
    """
    更新 hasFace 的值
    :param face_status: 新的 hasFace 值
    """
    try:
        # 解析JSON请求体
        body = await request.json()
        face_status = body.get("face_status")
        
        if face_status is None:
            return {"status": "error", "message": "face_status field is required"}
        global hasFace
        hasFace = face_status
        return {"status": "success", "hasFace": hasFace}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/connections")
async def get_connections(request: Request):
    """
    返回当前 connections 字典中存在的连接键（例如 "app:deviceId" 或 "web:userId"）及数量。
    """
    manager = _get_connection_manager_from_request(request)
    keys = await manager.list_keys()
    return {"count": len(keys), "connections": keys}


# ========== 设备注册相关，已弃用======================

@app.websocket("/ws/device")
async def device_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        # 第一次接入需要发送 deviceId JSON，例如：
        # {"type": "register", "device_id": "A123", "model": "Pixel 8", "os_version": "34"}
        msg_text = await websocket.receive_text()
        msg = json.loads(msg_text)
        if msg.get("type") != "register" or "device_id" not in msg:
            await websocket.close(code=4001)
            return

        device_id = msg["device_id"]
        # model = msg.get("model")
        # os_version = msg.get("os_version")

        # 注册设备到数据库
        device_service.register_device(device_id)

        # 保存连接
        active_connections[device_id] = websocket
        print(f"Device {device_id} connected")

        # 循环接收消息
        while True:
            data = await websocket.receive_text()
            print(f"Received from {device_id}: {data}")
            # 可以解析消息类型，并转发到前端
            # 前端发送 animation_command
            if msg.get("type") == "animation_command":
                target_ws = active_connections.get(msg["deviceId"])
                if target_ws:
                    await target_ws.send_text(json.dumps(msg))
    except WebSocketDisconnect:
        print(f"Device {device_id} disconnected")
        active_connections.pop(device_id, None)

@app.post("/web_register_device")
def web_register_device(register_item: RegisterItem):
    """
    Register a device with an optional webid.
    If the deviceid already exists, update the webid.
    """
    device_service.register_device(register_item.deviceid, register_item.webid)
    return {
        "status": "success",
        "deviceid": register_item.deviceid,
        "webid": register_item.webid,
    }

@app.get("/ready")
async def ready():
    """查询服务是否已经完全启动"""
    return {"status": 1}

@app.post("/device_register")
def device_register(device_item: DeviceItem):
    """
    Register a device with only deviceid.
    """
    device_service.register_device(device_item.deviceid)
    return {"status": "success", "deviceid": device_item.deviceid}

# ========== 设备注册相关，已弃用======================

@app.post("/interrupt_digitalman")
async def interrupt_digitalman(device_item: DeviceItem):
    """
    interrupt the digital human interaction
    """
    # loop = asyncio.get_event_loop()
    # info = await loop.run_in_executor(
    #     None, device_service.get_device_by_deviceid, device_item.deviceid
    # )
    # webid = info[2] if info else None

    # print(
    #     f"Received interrupt request for device {device_item.deviceid} with webid {webid}"
    # )
    payload = {
        "sessionid": device_item.deviceid if device_item.deviceid else "0",
    }
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.post(service_url + "/interrupt", json=payload)
            if r.status_code != 200:
                print(
                    f"Failed to send interrupt request to human service: {r.status_code} {r.text}"
                )
    except Exception as e:
        print(f"Error sending interrupt request to human service: {e}")
        pass
    return {
        "status": "success",
    }

@app.post("/asr_result2")
async def asr_result2(asr_result_item: ASRResultItem, background_tasks: BackgroundTasks):
    """
    Receive ASR result for a device (async).
    """
    print(
        f"Received ASR result for device {asr_result_item.deviceid}: {asr_result_item.result}"
    )
    payload = {
        "text": asr_result_item.result,
        "type": "chat",
        "interrupt": True,
        "sessionid": asr_result_item.deviceid if asr_result_item.deviceid else "0",
    }

    def send_to_human(payload):
        try:
            with httpx.Client(timeout=5) as client:
                r = client.post(service_url + "/human", json=payload)
                if r.status_code != 200:
                    print(
                        f"Failed to send ASR result to human service: {r.status_code} {r.text}"
                    )
        except Exception as e:
            print(f"Error sending ASR result to human service: {e}")
            pass

    background_tasks.add_task(send_to_human, payload)
    return {
        "status": "success",
        "deviceid": asr_result_item.deviceid,
        "result": asr_result_item.result,
    }

@app.get("/restart")
def restart_service():
    """重启PM2服务(进程ID 0和1)"""
    import subprocess
    try:
        result = subprocess.run(
            ["pm2", "restart", "7"],
            capture_output=True,
            text=True,
            check=True
        )
        return {
            "status": "success",
            "output": result.stdout,
            "error": result.stderr
        }
    except subprocess.CalledProcessError as e:
        return {
            "status": "error",
            "output": e.stdout,
            "error": e.stderr,
            "returncode": e.returncode
        }, 500
