import os
import requests
import logging

logging.basicConfig(level=logging.INFO)


def test_upload_video(video_path):
    url = "http://10.100.10.31:8086/v1/upload"

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"文件未找到: {video_path}")

    with open(video_path, "rb") as video_file:
        files = {
            "file": (os.path.basename(video_path), video_file, "video/mp4")
        }

        response = requests.post(url, files=files)
        logging.info(response.json())

        assert response.status_code == 200
        assert "文件上传成功" in response.json()["message"]
        assert "url" in response.json()


if __name__ == "__main__":
    video_path = "../data/videos/xinhe.mp4"

    test_upload_video(video_path)
