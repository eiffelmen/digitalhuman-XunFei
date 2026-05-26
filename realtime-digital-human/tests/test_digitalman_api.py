import time
import requests


def main():
    base_url = "http://10.100.10.31:8085"
    video_url = "https://oss.minio.ratuads.com:8143/laboratory/file/2940d3f1-eed6-4c77-a2fa-5edfad62151a.mp4"

    submit_url = f"{base_url}/v1/process_video_url"
    response = requests.post(submit_url, json={"video_url": video_url})
    if response.status_code != 200:
        print("任务提交失败：", response.text, flush=True)
        return

    data = response.json()
    task_id = data["task_id"]
    print("任务提交成功，task_id:", task_id, flush=True)

    # 轮询检查任务状态
    status_url = f"{base_url}/v1/check_status/{task_id}"
    polling_counter = 0
    max_polling = 100 

    while polling_counter < max_polling:
        time.sleep(5)
        status_response = requests.get(status_url)
        if status_response.status_code != 200:
            print("检查状态失败：", status_response.text, flush=True)
            break
        status_data = status_response.json()
        print("当前状态：", status_data, flush=True)

        if status_data.get("status") in ["completed", "failed"]:
            print("任务已结束，状态：", status_data.get("status"), flush=True)
            break

        polling_counter += 1

    if polling_counter == max_polling:
        print("超过最大轮询次数，任务可能未及时完成", flush=True)


if __name__ == "__main__":
    main()
