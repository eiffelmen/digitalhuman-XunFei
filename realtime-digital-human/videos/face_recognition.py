import cv2
import base64
import requests

import numpy as np
from pydantic import BaseModel
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI()


class ImageRequest(BaseModel):
    image: str


def send_face_detection_request(frame):
    url = "http://10.100.10.31:8039/Face/DetRecTrack"
    _, buffer = cv2.imencode('.jpg', frame)
    image_data = base64.b64encode(buffer).decode('utf-8')

    payload = {
        "images": [f"data:image/jpg;base64,{image_data}"]
    }

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as http_err:
        return {"error": f"HTTP错误：{http_err}"}
    except Exception as e:
        return {"error": f"发生错误：{str(e)}"}


@app.websocket("/ws/process_frame")
async def websocket_process_frame(websocket: WebSocket):
    await websocket.accept()
    while True:
        try:
            data = await websocket.receive_text()
            image_data = data.split(',')[1]

            if not image_data:
                await websocket.send_json({"detail": "未接收到图像数据"})
                continue

            frame = base64.b64decode(image_data)
            np_arr = np.frombuffer(frame, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

            result = send_face_detection_request(frame)
        
            if isinstance(result, dict) and "error" in result:
                await websocket.send_json({"error": result["error"]})
            else:
                # 接下来通过大模型和数字人交互...
                await websocket.send_json(result)
        except WebSocketDisconnect:
            print("Client disconnected")
            break
        except Exception as e:
            await websocket.send_json({"detail": str(e)})
            break

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=5000)
