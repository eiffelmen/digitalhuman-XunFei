import os
import cv2
import time
import asyncio
import traceback
import shutil
import threading
import psutil
import uuid
import glob
import torch
import pickle
import uvicorn
import aiohttp
import argparse
import subprocess
import face_detection
import concurrent.futures
import multiprocessing
from typing import Dict, Tuple

import numpy as np
from tqdm import tqdm
from upload_api import upload_image_file
from segmentation_v2 import RMBGImageSegmentation

from fastapi import FastAPI, UploadFile, File, Body, BackgroundTasks
from fastapi.responses import JSONResponse
import logging

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

parser = argparse.ArgumentParser(
    description=
    'Inference code to lip-sync videos in the wild using Wav2Lip models')
parser.add_argument(
    '--nosmooth',
    default=False,
    action='store_true',
    help='Prevent smoothing face detections over a short temporal window')
parser.add_argument('--img_size', default=256, type=int)
parser.add_argument(
    '--pads',
    nargs='+',
    type=int,
    default=[0, 10, -10, -10],
    help=
    'Padding (top, bottom, left, right). Please adjust to include chin at least'
)
parser.add_argument('--face_det_batch_size',
                    type=int,
                    help='Batch size for face detection',
                    default=4)
parser.add_argument('--host',
                    default='0.0.0.0',
                    type=str,
                    help='IP address to listen on')
parser.add_argument('--port', default=8085, type=int, help='Port to listen on')
parser.add_argument('--num_workers',
                    default=4,
                    type=int,
                    help='Number of worker processes for parallel processing')
args = parser.parse_args()

if torch.cuda.is_available():
    multiprocessing.set_start_method('spawn', force=True)

device = 'cuda' if torch.cuda.is_available() else 'cpu'
logging.info('Using {} for inference.'.format(device))

matte = RMBGImageSegmentation()

app = FastAPI()

# 任务状态存储
tasks: Dict[str, Dict] = {}


def image_to_buffer(image_path):
    img = cv2.imread(image_path)
    _, buffer = cv2.imencode('.jpg', img)
    return buffer


async def run_command(cmd: list, timeout: int = 60) -> Tuple[str, str]:
    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(),
                                                timeout=timeout)
        return stdout.decode(), stderr.decode()
    except asyncio.TimeoutError:
        process.kill()
        stdout, stderr = await process.communicate()
        raise TimeoutError(
            f"Command {cmd} timed out. Stderr: {stderr.decode()}")


async def check_and_adjust_video_async(video_path):
    try:
        cmd = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate", "-of",
            "default=noprint_wrappers=1", video_path
        ]
        stdout, _ = await run_command(cmd, timeout=30)
        width = height = frame_rate = None

        for line in stdout.splitlines():
            if 'width=' in line:
                width = int(line.split('=')[1])
            elif 'height=' in line:
                height = int(line.split('=')[1])
            elif 'r_frame_rate=' in line:
                nums = line.split('=')[1].split('/')
                frame_rate = int(float(nums[0]) / float(nums[1]))

        # 若视频信息不符合要求则进行调整
        if width != 1080 or height != 1920 or frame_rate != 25:
            adjusted_video_path = video_path.replace(".mp4", "_adjusted.mp4")
            cmd_ffmpeg = [
                "ffmpeg", "-i", video_path, "-vf", "scale=1080:1920", "-r",
                "25", "-y", adjusted_video_path
            ]
            await run_command(cmd_ffmpeg, timeout=60)
            return adjusted_video_path
    except Exception as e:
        raise RuntimeError("Error processing video metadata: " + str(e))

    return video_path


def get_smoothened_boxes(boxes, T=5):
    for i in range(len(boxes)):
        if i + T > len(boxes):
            window = boxes[len(boxes) - T:]
        else:
            window = boxes[i:i + T]
        boxes[i] = np.mean(window, axis=0)
    return boxes


@torch.inference_mode()
def face_detect_batch(images):
    detector = face_detection.FaceAlignment(face_detection.LandmarksType._2D,
                                            flip_input=False,
                                            device=device)
    batch_size = args.face_det_batch_size

    while True:
        predictions = []
        try:
            for i in tqdm(range(0, len(images), batch_size), desc="人脸检测批处理"):
                predictions.extend(
                    detector.get_detections_for_batch(
                        np.array(images[i:i + batch_size])))
        except RuntimeError:
            if batch_size == 1:
                raise RuntimeError(
                    'Image too big to run face detection on GPU. Please use the --resize_factor argument'
                )
            batch_size //= 2
            logging.warning(
                'Recovering from OOM error; New batch size: {}'.format(
                    batch_size))
            continue
        break

    results = []
    pady1, pady2, padx1, padx2 = args.pads
    prev_rect = None
    for rect, image in zip(predictions, images):
        if rect is None:
            if prev_rect is None:
                raise ValueError('首帧人脸检测失败，请确保视频包含清晰人脸')
            logging.warning(f"警告：第{len(results)}帧使用前一帧坐标")
            rect = prev_rect
        else:
            prev_rect = rect

        y1 = max(0, rect[1] - pady1)
        y2 = min(image.shape[0], rect[3] + pady2)
        x1 = max(0, rect[0] - padx1)
        x2 = min(image.shape[1], rect[2] + padx2)

        results.append([x1, y1, x2, y2])

    boxes = np.array(results)
    if not args.nosmooth:
        boxes = get_smoothened_boxes(boxes, T=5)
    results = [[image[y1:y2, x1:x2], (y1, y2, x1, x2)]
               for image, (x1, y1, x2, y2) in zip(images, boxes)]

    del detector
    return results


def process_single_frame(frame, face_crop, coords, index, full_imgs_path,
                         full_masks_path, face_imgs_path, img_size,
                         matte_model):
    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        mask = matte_model(frame)
        cv2.imwrite(os.path.join(full_imgs_path, f"{index:08d}.png"), frame)
        cv2.imwrite(os.path.join(full_masks_path, f"{index:08d}.png"), mask)

        if face_crop is not None:
            resized_crop_frame = cv2.resize(face_crop, (img_size, img_size))
            cv2.imwrite(os.path.join(face_imgs_path, f"{index:08d}.png"),
                        resized_crop_frame)

        return coords, index
    except Exception as e:
        if 'CUDA' in str(e):
            torch.cuda.empty_cache()
        logging.error(f"处理第 {index} 帧时发生错误: {str(e)}，使用前一帧坐标")
        if torch.cuda.is_available():
            logging.info(
                f"CUDA 设备属性: {torch.cuda.get_device_properties(device)}")
            logging.info(f"CUDA 内存统计: {torch.cuda.memory_stats(device)}")
            logging.info(f"CUDA 内存摘要: {torch.cuda.memory_summary(device)}")
        logging.info(f"帧形状: {frame.shape}, 数据类型: {frame.dtype}")
        if 'CUDA error' in str(e):
            torch.cuda.synchronize()
        return None, index


def osmakedirs(path_list):
    for path in path_list:
        os.makedirs(path, exist_ok=True)


async def process_video_common(video_path, is_url=False):
    start_time = time.time()
    avatar_path = None
    processed_video_path = None
    extracted_video_path = None
    mem_monitor = None  # 内存监控对象

    class MemoryMonitor(threading.Thread):
        """新增内存监控线程类"""

        def __init__(self):
            super().__init__(daemon=True)
            self.running = True

        def run(self):
            while self.running:
                if torch.cuda.is_available():
                    logging.info(
                        f"显存使用情况: {torch.cuda.memory_allocated()/1024**2:.2f} MB"
                    )
                else:
                    logging.info(
                        f"内存使用: {psutil.Process().memory_info().rss/1024**2:.2f} MB"
                    )
                time.sleep(5)

        def stop(self):
            self.running = False

    try:
        mem_monitor = MemoryMonitor()
        mem_monitor.start()

        if is_url:
            os.makedirs("temp", exist_ok=True)
            async with aiohttp.ClientSession() as session:
                async with session.get(video_path) as response:
                    if response.status != 200:
                        return JSONResponse(
                            content={"error": "Failed to download video"},
                            status_code=400)
                    temp_path = f"temp/{uuid.uuid4()}.mp4"
                    with open(temp_path, "wb") as f:
                        f.write(await response.read())
            video_path = temp_path

        processed_video_path = await check_and_adjust_video_async(video_path)
        logging.info("使用视频路径：%s", processed_video_path)

        try:
            result = subprocess.run([
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                processed_video_path
            ],
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    timeout=30)
            duration = float(result.stdout)
        except subprocess.TimeoutExpired:
            raise RuntimeError("视频元数据检测超时")
        except ValueError:
            raise RuntimeError("无效的视频时长格式")

        max_duration = 20.0
        extracted_video_path = processed_video_path
        if duration > max_duration:
            extracted_video_path = processed_video_path.replace(
                ".mp4", "_extracted.mp4")
            try:
                subprocess.run([
                    "ffmpeg", "-i", processed_video_path, "-ss", "0", "-t",
                    str(max_duration), "-c:v", "libx264", "-preset", "fast",
                    "-y", extracted_video_path
                ],
                               check=True,
                               timeout=60)
            except subprocess.TimeoutExpired:
                raise RuntimeError("视频截取操作超时")

        base_avatar_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "avatars")
        existing_avatars = glob.glob(
            os.path.join(base_avatar_dir, "wav2lip_avatar*"))
        max_number = max(
            [int(p.split('wav2lip_avatar')[-1]) for p in existing_avatars],
            default=0) + 1

        avatar_path = os.path.join(base_avatar_dir,
                                   f"wav2lip_avatar{max_number}")
        full_imgs_path = os.path.join(avatar_path, "full_imgs")
        full_masks_path = os.path.join(avatar_path, "full_masks")
        face_imgs_path = os.path.join(avatar_path, "face_imgs")
        coords_path = os.path.join(avatar_path, "coords.pkl")
        osmakedirs(
            [avatar_path, full_imgs_path, full_masks_path, face_imgs_path])

        try:
            cap = cv2.VideoCapture(extracted_video_path)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames == 0:
                raise ValueError("视频文件无法读取或帧数为零")

            frames = []
            with tqdm(total=total_frames, desc="读取视频帧") as pbar:
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        if len(frames) == 0:
                            raise ValueError("视频帧读取失败")
                        break
                    frames.append(frame)
                    pbar.update(1)
        finally:
            cap.release()

        face_det_results = face_detect_batch(frames)

        futures_dict = {}
        batch_size = 16
        with concurrent.futures.ProcessPoolExecutor(
                max_workers=args.num_workers) as executor:
            for i in range(0, len(frames), batch_size):
                batch = frames[i:i + batch_size]
                for j, frame in enumerate(batch):
                    idx = i + j
                    face_crop = face_det_results[idx][0] if idx < len(
                        face_det_results) else None
                    face_coords = face_det_results[idx][1] if idx < len(
                        face_det_results) else None
                    future = executor.submit(process_single_frame, frame,
                                             face_crop, face_coords, idx,
                                             full_imgs_path, full_masks_path,
                                             face_imgs_path, args.img_size,
                                             matte)
                    futures_dict[future] = idx

            results = [None] * len(frames)
            completed_futures = set()

            try:
                for future in concurrent.futures.as_completed(futures_dict,
                                                              timeout=300):
                    idx = futures_dict[future]
                    try:
                        coords, _ = future.result(timeout=300)  # 单帧处理超时延长
                        results[idx] = coords
                    except concurrent.futures.TimeoutError:
                        logging.warning(f"处理第 {idx} 帧超时，跳过该帧")
                        future.cancel()
                        results[idx] = None
                    completed_futures.add(future)
            except concurrent.futures.TimeoutError:
                logging.error("整体处理超时，部分帧未完成")
            finally:
                for future in futures_dict:
                    if future not in completed_futures:
                        future.cancel()
                executor.shutdown(wait=False)

        coord_list = [None] * len(frames)
        prev_valid_coords = None
        error_count = 0
        for i, coords in enumerate(results):
            if coords is None:
                error_count += 1
                if prev_valid_coords is not None:
                    coord_list[i] = prev_valid_coords
                    if error_count > 10:
                        raise RuntimeError(f"连续{error_count}帧处理失败")
                else:
                    raise ValueError("无法获取有效初始坐标")
            else:
                coord_list[i] = coords
                prev_valid_coords = coords
                error_count = 0

        first_image_path = os.path.join(full_imgs_path, "00000000.png")
        if not os.path.exists(first_image_path):
            return JSONResponse(content={"error": "视频处理中未检测到人脸，导致无有效帧"},
                                status_code=404)

        with open(coords_path, 'wb') as f:
            pickle.dump(coord_list, f)

        max_retries = 3
        for attempt in range(max_retries):
            try:
                upload_result = upload_image_file(first_image_path)
                if not upload_result or "url" not in upload_result:
                    raise ValueError("上传返回结果无效")
                image_url = upload_result["url"]
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    return JSONResponse(
                        content={"error": f"上传首帧图片失败：{str(e)}"},
                        status_code=500)
                time.sleep(1)

        processing_time = round(time.time() - start_time, 2)
        logging.info(f"总处理时间: {processing_time}秒")

        return JSONResponse(
            content={
                "message": "视频处理完成",
                "avatar_id": f"wav2lip_avatar{max_number}",
                "templete_image_url": image_url,
                "processing_time": f"{processing_time}秒"
            })

    except Exception as e:
        processing_time = round(time.time() - start_time, 2)
        logging.error(f"处理失败: {traceback.format_exc()}")
        if avatar_path and os.path.exists(avatar_path):
            shutil.rmtree(avatar_path, ignore_errors=True)
        return JSONResponse(content={
            "error": f"{type(e).__name__}: {str(e)}",
            "processing_time": f"{processing_time}秒"
        },
                            status_code=500)
    finally:
        if mem_monitor:
            mem_monitor.stop()

        temp_files = set()
        if is_url:
            temp_files.add(video_path)
        if processed_video_path and processed_video_path != video_path:
            temp_files.add(processed_video_path)
        if extracted_video_path and extracted_video_path != processed_video_path:
            temp_files.add(extracted_video_path)

        for path in temp_files:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as ex:
                    logging.error(f"删除临时文件 {path} 时出错: {str(ex)}")

        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def process_video_common_sync(video_path, is_url):
    """
    同步封装 process_video_common（内部调用 asyncio.run 来运行异步逻辑）
    """
    return asyncio.run(process_video_common(video_path, is_url))


async def process_video_task(task_id: str, video_path: str, is_url: bool):
    try:
        tasks[task_id]["status"] = "processing"
        tasks[task_id]["start_time"] = time.time()
        # 在后台线程中执行视频处理
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, process_video_common_sync,
                                            video_path, is_url)

        task_status = "completed" if result.status_code == 200 else "failed"
        tasks[task_id].update({
            "status":
            task_status,
            "result":
            result.body.decode()
            if isinstance(result.body, bytes) else result.body,
            "processing_time":
            time.time() - tasks[task_id]["start_time"],
            "complete_time":
            time.time()
        })
    except Exception as e:
        tasks[task_id].update({
            "status":
            "failed",
            "error":
            str(e),
            "processing_time":
            time.time() - tasks[task_id]["start_time"],
            "complete_time":
            time.time()
        })


@app.post("/v1/process_video_url")
async def process_video_url(
        video_url: str = Body(..., embed=True),
        background_tasks: BackgroundTasks = BackgroundTasks()):
    task_id = str(uuid.uuid4())
    tasks[task_id] = {"status": "pending", "start_time": time.time()}
    background_tasks.add_task(process_video_task, task_id, video_url, True)

    return JSONResponse(content={
        "task_id": task_id,
        "message": "任务已提交，请轮询查看进度"
    })


@app.post("/v1/process_video")
async def process_video(video: UploadFile = File(None),
                        background_tasks: BackgroundTasks = BackgroundTasks()):
    if not video or not video.filename:
        return JSONResponse(content={"error": "必须上传视频文件"}, status_code=400)

    task_id = str(uuid.uuid4())
    tasks[task_id] = {"status": "pending", "start_time": time.time()}

    os.makedirs("temp", exist_ok=True)
    temp_path = f"temp/{uuid.uuid4()}.mp4"

    with open(temp_path, "wb") as f:
        f.write(await video.read())

    background_tasks.add_task(process_video_task, task_id, temp_path, False)
    return JSONResponse(content={
        "task_id": task_id,
        "message": "任务已提交，请轮询查看进度"
    })


@app.get("/v1/check_status/{task_id}")
async def check_status(task_id: str):
    task = tasks.get(task_id)
    if not task:
        return JSONResponse(content={"error": "任务不存在或已过期"}, status_code=404)

    if task.get("complete_time") and (time.time() -
                                      task["complete_time"]) > 86400:
        del tasks[task_id]
        return JSONResponse(content={"error": "任务记录已过期"}, status_code=404)

    response = {
        "task_id":
        task_id,
        "status":
        task.get("status", "unknown"),
        "processing_time":
        round(
            task.get("processing_time",
                     time.time() - task.get("start_time", time.time())), 2)
    }

    if task["status"] == "completed":
        response.update({
            k: v
            for k, v in task.items() if k not in ["status", "processing_time"]
        })
    elif task["status"] == "failed":
        response["error"] = task.get("error", "未知错误")

    return JSONResponse(content=response)


@app.delete("/v1/delete_avatar/{avatar_id}")
async def delete_avatar(avatar_id: int):
    try:
        if avatar_id in {1, 2, 3}:
            return JSONResponse(
                content={"error": "Cannot delete avatars 1, 2, 3"},
                status_code=403)

        avatar_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "avatars", f"wav2lip_avatar{avatar_id}")
        if not os.path.exists(avatar_path):
            return JSONResponse(content={"error": "Avatar not found"},
                                status_code=404)

        for root, dirs, files in os.walk(avatar_path, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(avatar_path)

        return JSONResponse(content={"message": "Avatar deleted successfully"})

    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


if __name__ == "__main__":
    uvicorn.run(app, host=args.host, port=args.port)
