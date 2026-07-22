import cv2
import base64
from pathlib import Path
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]


name_mapping = {
    "ll": "罗凌"
}


class FaceRecognition:
    def __init__(self, video_path):
        self.video_path = video_path
        self.url = "http://backend.example.internal:8039/Face/DetRecTrack"

    def send_face_detection_request(self, frame):
        _, buffer = cv2.imencode('.jpg', frame)
        image_data = base64.b64encode(buffer).decode('utf-8')

        payload = {
            "images": [f"data:image/jpg;base64,{image_data}"]
        }

        try:
            response = requests.post(self.url, json=payload)
            if response.status_code == 200:
                return response.json()
            else:
                return f"请求失败，状态码：{response.status_code}"
        except requests.exceptions.RequestException as e:
            return f"请求异常：{str(e)}"
        except Exception as e:
            return f"未知错误：{str(e)}"

    def run(self):
        cap = cv2.VideoCapture(self.video_path)
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                result = self.send_face_detection_request(frame)
                if isinstance(result, dict) and result.get("code") == 200:
                    data = result.get("data", {})
                    if data.get("id_max") != "none" and data.get("id_max") != "404":
                        return data['id_max']
        finally:
            cap.release()


if __name__ == "__main__":
    video_path = PROJECT_ROOT / "videos" / "luo.mp4"
    face_recognition = FaceRecognition(str(video_path))
    name = face_recognition.run()
    print(f"检测到的人名: {name_mapping.get(name, '未知')}")
