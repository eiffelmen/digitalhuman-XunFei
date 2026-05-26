import os

# 如果未指定则默认使用0卡，避免覆盖容器或宿主机传入的 GPU 设备设置
os.environ.setdefault('CUDA_VISIBLE_DEVICES', "0")

import torch
import gc
import time
import cv2
import glob
import pickle
import copy
import queue
import numpy as np
from threading import Thread, Event

import asyncio
from lipasr import LipASR
from av import AudioFrame, VideoFrame
from wav2lip256.models import Wav2Lip
from basereal import BaseReal
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
from loguru import logger
from functools import lru_cache
from collections import OrderedDict

import warnings

warnings.filterwarnings("ignore", category=UserWarning)

device = 'cuda' if torch.cuda.is_available() else 'cpu'
logger.info('正在使用{}进行推理。'.format(device))
torch.backends.cudnn.benchmark = True


def _load(checkpoint_path):
    if device == 'cuda':
        checkpoint = torch.load(checkpoint_path)
    else:
        checkpoint = torch.load(checkpoint_path,
                                map_location=lambda storage, loc: storage)
    return checkpoint


def load_model(path):
    model = Wav2Lip()
    logger.info("从 {} 加载检查点。".format(path))
    checkpoint = _load(path)
    s = checkpoint["state_dict"]
    new_s = {}
    for k, v in s.items():
        new_s[k.replace('module.', '')] = v
    model.load_state_dict(new_s)

    model = model.to(device)
    return model.eval()


def load_avatar(avatar_id):
    # 例如：wav2lip_avatar*， *代表数字
    avatar_path = f"./data/avatars/{avatar_id}"
    full_imgs_path = f"{avatar_path}/full_imgs"
    face_imgs_path = f"{avatar_path}/face_imgs"
    full_masks_path = f"{avatar_path}/full_masks"
    coords_path = f"{avatar_path}/coords.pkl"

    with open(coords_path, 'rb') as f:
        coord_list_cycle = pickle.load(f)

    # 原来从硬盘读取的方式
    input_img_list = glob.glob(
        os.path.join(full_imgs_path, '*.[jpJP][pnPN]*[gG]'))
    input_img_list = sorted(
        input_img_list,
        key=lambda x: int(os.path.splitext(os.path.basename(x))[0]))
    frame_list_cycle = read_imgs(input_img_list)

    input_face_list = glob.glob(
        os.path.join(face_imgs_path, '*.[jpJP][pnPN]*[gG]'))
    input_face_list = sorted(
        input_face_list,
        key=lambda x: int(os.path.splitext(os.path.basename(x))[0]))
    face_list_cycle = read_imgs(input_face_list)

    input_mask_list = glob.glob(
        os.path.join(full_masks_path, '*.[jpJP][pnPN]*[gG]'))
    input_mask_list = sorted(
        input_mask_list,
        key=lambda x: int(os.path.splitext(os.path.basename(x))[0]))
    mask_list_cycle = read_imgs(input_mask_list, flag=True)

    return frame_list_cycle, face_list_cycle, coord_list_cycle, mask_list_cycle


@torch.no_grad()
def warm_up(batch_size, model, modelres):
    logger.info('模型预热中...')
    img_batch = torch.ones(batch_size, 6, modelres, modelres).to(device)
    mel_batch = torch.ones(batch_size, 1, 80, 16).to(device)
    model(mel_batch, img_batch)


# def read_imgs(img_list, flag=False):
#     logger.info('读取图像中...')

#     def load_image(img_path):
#         return cv2.imread(img_path, cv2.IMREAD_GRAYSCALE if flag else cv2.IMREAD_COLOR)

#     with ThreadPoolExecutor(max_workers=min(32, os.cpu_count() + 4)) as executor:
#         return list(tqdm(executor.map(load_image, img_list), total=len(img_list)))


def read_imgs(img_list, flag=False):
    logger.info('读取图像中...')

    max_workers = min(64, os.cpu_count() * 4)

    @lru_cache(maxsize=1024)
    def load_image_cached(img_path):
        return cv2.imread(img_path,
                          cv2.IMREAD_GRAYSCALE if flag else cv2.IMREAD_COLOR)

    for img in img_list[:min(100, len(img_list))]:
        load_image_cached(img)

    future_order = OrderedDict()

    with ThreadPoolExecutor(max_workers=max_workers,
                            thread_name_prefix="img_loader") as executor:
        for idx, img in enumerate(img_list):
            future = executor.submit(load_image_cached, img)
            future_order[idx] = future

        results = [None] * len(img_list)
        for idx, future in tqdm(future_order.items(), total=len(img_list)):
            results[idx] = future.result()

    return results


def __mirror_index(size, index):
    turn = index // size
    res = index % size
    if turn % 2 == 0:
        return res
    else:
        return size - res - 1


@torch.inference_mode()
def inference(quit_event, batch_size, face_list_cycle, audio_feat_queue,
              audio_out_queue, res_frame_queue, model, ready_event):
    try:
        length = len(face_list_cycle)
        index = 0
        count = 0
        counttime = 0
        logger.info('开始推理...')

        # 线程级别的强制预热：防止每次首次说话时的冷启动显存分配延迟
        try:
            face = face_list_cycle[0]
            dummy_img = np.zeros((batch_size, face.shape[0], face.shape[1], 3), dtype=np.uint8)
            dummy_img_masked = dummy_img.copy()
            dummy_img_masked[:, face.shape[0] // 2:] = 0
            dummy_img_batch = np.concatenate((dummy_img_masked, dummy_img), axis=3) / 255.0
            dummy_mel_batch = np.zeros((batch_size, 1, 80, 16), dtype=np.float32)
            
            dummy_img_tensor = torch.FloatTensor(np.transpose(dummy_img_batch, (0, 3, 1, 2))).to(device)
            dummy_mel_tensor = torch.FloatTensor(dummy_mel_batch).to(device)
            model(dummy_mel_tensor, dummy_img_tensor)
            logger.info('线程内模型预热完成')
        except Exception as e:
            logger.warning(f"线程内预热失败: {e}")

        # 设置准备就绪标志
        ready_event.set()

        last_mel_batch = None
        while not quit_event.is_set():
            if last_mel_batch is None:
                try:
                    # 恢复超时时间为 0.04s，匹配 Batch 16 的节奏
                    mel_batch = audio_feat_queue.get(block=True, timeout=0.04)
                except queue.Empty:
                    # 队列为空，推送一帧待机帧以维持 WebRTC 心跳
                    res_frame_queue.put((None, __mirror_index(length, index), None))
                    index += 1
                    continue
            else:
                mel_batch = last_mel_batch
                last_mel_batch = None

            # 尝试获取对应的原始音频帧
            is_all_silence = True
            audio_frames = []
            try:
                for _ in range(batch_size * 2):
                    # 改为非阻塞，防止进入推理时被 ASR 的瞬时延迟卡住
                    frame, type = audio_out_queue.get(block=False)
                    audio_frames.append((frame, type))
                    if type == 0:
                        is_all_silence = False
            except queue.Empty:
                # 原始音频还没准备好（TTS传输中或ASR计算中）
                # 此时不能丢弃 mel_batch，存起来下次循环再试，本次先发待机帧
                last_mel_batch = mel_batch
                res_frame_queue.put((None, __mirror_index(length, index), None))
                index += 1
                continue

            if is_all_silence:
                for i in range(batch_size):
                    res_frame_queue.put((None, __mirror_index(length, index),
                                         audio_frames[i * 2:i * 2 + 2]))
                    index += 1
            else:
                t = time.perf_counter()
                img_batch = []
                for i in range(batch_size):
                    idx = __mirror_index(length, index + i)
                    face = face_list_cycle[idx]
                    img_batch.append(face)

                img_batch, mel_batch = np.asarray(img_batch), np.asarray(
                    mel_batch)

                img_masked = img_batch.copy()
                img_masked[:, face.shape[0] // 2:] = 0

                img_batch = np.concatenate(
                    (img_masked, img_batch), axis=3) / 255.
                mel_batch = np.reshape(mel_batch, [
                    len(mel_batch), mel_batch.shape[1], mel_batch.shape[2], 1
                ])

                img_batch = torch.FloatTensor(
                    np.transpose(img_batch, (0, 3, 1, 2))).to(device)
                mel_batch = torch.FloatTensor(
                    np.transpose(mel_batch, (0, 3, 1, 2))).to(device)

                with torch.no_grad():
                    pred = model(mel_batch, img_batch)
                pred = pred.cpu().numpy().transpose(0, 2, 3, 1) * 255.

                counttime += (time.perf_counter() - t)
                count += batch_size
                if count >= 100: # 恢复日志打印频率
                    logger.info(f"实际平均推理FPS:{count/counttime:.4f}")
                    count = 0
                    counttime = 0

                for i, res_frame in enumerate(pred):
                    res_frame_queue.put(
                        (res_frame, __mirror_index(length, index),
                         audio_frames[i * 2:i * 2 + 2]))
                    index += 1

        logger.info('lipreal inference processor stop')
    except Exception as e:
        logger.error(f"推理过程发生错误: {e}")
        ready_event.set()
    finally:
        logger.info('Wav2Lip 推理处理停止')


class LipReal(BaseReal):

    @torch.inference_mode()
    def __init__(self, opt, model, avatar):
        super().__init__(opt)
        self.fps = opt.fps
        self.bg_img = cv2.imread(opt.bg_img)  # 背景图

        self.batch_size = opt.batch_size  # 恢复为原始批次大小以提升稳定性
        self.res_frame_queue = queue.Queue(self.batch_size * 2)
        self.model = model

        self._init_avatar(avatar)

        self.asr = LipASR(opt, self)
        self.asr.batch_size = self.batch_size  # 同步 ASR 批次大小，防止维数不匹配报错
        self.asr.warm_up()

        self.inference_ready = Event()
        self._init_inference_thread()

    def update_bg_img(self, bg_img_path):
        logger.info(f'更新背景图片到: {bg_img_path}')
        self.bg_img = cv2.imread(bg_img_path)

    def _init_avatar(self, avatar):
        self.frame_list_cycle, self.face_list_cycle, self.coord_list_cycle, self.mask_list_cycle = avatar

    def _init_inference_thread(self):
        self.inference_quit_event = Event()
        self.inference_ready.clear()
        self.inference_thread = Thread(
            target=inference,
            args=(self.inference_quit_event, self.batch_size,
                  self.face_list_cycle, self.asr.feat_queue,
                  self.asr.output_queue, self.res_frame_queue, self.model,
                  self.inference_ready))
        self.inference_thread.start()
        self.inference_ready.wait(timeout=5.0)  # 添加超时以防止死锁

    def _clear_frame_queue(self):
        while not self.res_frame_queue.empty():
            try:
                self.res_frame_queue.get_nowait()
            except queue.Empty:
                break

    def _clear_audio_queues(self):
        # 清理ASR相关的队列
        self.asr.queue.queue.clear()
        while not self.asr.output_queue.empty():
            try:
                self.asr.output_queue.get_nowait()
            except:
                break
        while not self.asr.feat_queue.empty():
            try:
                self.asr.feat_queue.get_nowait()
            except:
                break

    def __del__(self):
        logger.info(f'lipreal() delete')

    def change_avatar(self, avatar):
        # 停止当前推理线程
        self.inference_quit_event.set()
        self.inference_thread.join()

        # 清理所有相关队列
        self._clear_frame_queue()
        self._clear_audio_queues()

        # 更新形象数据
        self._init_avatar(avatar)

        logger.info('数字人形象切换完成')

        # 重置ASR状态
        self.asr.reset()

        # 重新启动推理线程
        self._init_inference_thread()

    def blend_images(self, person_image, mask_image, background_image):
        # 优化混合逻辑，直接使用 NumPy 矩阵运算，减少 OpenCV 函数调用开销
        mask = mask_image.astype(np.float32) / 255.0
        if len(mask.shape) == 2:
            mask = np.expand_dims(mask, axis=-1)
        
        # 核心公式：out = src * mask + bg * (1 - mask)
        # 这种方式在 NumPy 中并行度更高，且避免了多次 bitwise_and 拷贝
        combined = (person_image.astype(np.float32) * mask + 
                    background_image.astype(np.float32) * (1.0 - mask))
        return combined.astype(np.uint8)

    def process_frames(self,
                       quit_event,
                       loop=None,
                       audio_track=None,
                       video_track=None):
        while not quit_event.is_set():
            # 流量控制：增加缓冲区深度到 10 帧 (400ms)，提高对瞬间波动的耐受性
            if audio_track._queue.qsize() > 15 or video_track._queue.qsize() > 10:
                time.sleep(0.01)
                continue

            try:
                res_frame, idx, audio_frames = self.res_frame_queue.get(
                    block=True, timeout=1)
            except queue.Empty:
                continue

            # 连续两帧均为静音数据，或者没有音频数据（处于等待状态）
            if audio_frames is None or (audio_frames[0][1] != 0 and audio_frames[1][1] != 0):
                self.speaking = False
                audiotype = audio_frames[0][1] if audio_frames is not None else 0
                # 自定义视频播放
                if self.custom_index.get(audiotype) is not None:
                    mirindex = self.mirror_index(
                        len(self.custom_img_cycle[audiotype]),
                        self.custom_index[audiotype])
                    combine_frame = self.custom_img_cycle[audiotype][mirindex]
                    self.custom_index[audiotype] += 1
                else:
                    combine_frame = self.frame_list_cycle[idx]
                    mask_frame = self.mask_list_cycle[idx]
                    combine_frame = self.blend_images(combine_frame,
                                                      mask_frame, self.bg_img)
            else:
                self.speaking = True
                bbox = self.coord_list_cycle[idx]
                # 性能优化：禁止使用 copy.deepcopy，改用高效的 .copy()
                combine_frame = self.frame_list_cycle[idx].copy()
                y1, y2, x1, x2 = bbox
                try:
                    res_frame = cv2.resize(res_frame.astype(np.uint8),
                                           (x2 - x1, y2 - y1))
                except:
                    continue

                combine_frame[y1:y2, x1:x2] = res_frame
                mask_frame = self.mask_list_cycle[idx]
                combine_frame = self.blend_images(combine_frame, mask_frame,
                                                  self.bg_img)

            # 音画同步优化：优先推送音频包
            if audio_frames is not None:
                for audio_frame in audio_frames:
                    frame, _ = audio_frame
                    frame = (frame * 32767).astype(np.int16)
                    new_frame = AudioFrame(format='s16',
                                           layout='mono',
                                           samples=frame.shape[0])
                    new_frame.planes[0].update(frame.tobytes())
                    new_frame.sample_rate = 16000
                    asyncio.run_coroutine_threadsafe(
                        audio_track._queue.put(new_frame), loop)
            else:
                # 维持 40ms 的静音（20ms * 2）以匹配 25fps 的视频节奏
                silence_frame = np.zeros(self.chunk, dtype=np.int16)
                for _ in range(2):
                    new_frame = AudioFrame(format='s16', layout='mono', samples=self.chunk)
                    new_frame.planes[0].update(silence_frame.tobytes())
                    new_frame.sample_rate = 16000
                    asyncio.run_coroutine_threadsafe(audio_track._queue.put(new_frame), loop)

            # 音频包推送后再进行耗时的视频转换，确保声音优先
            new_frame = VideoFrame.from_ndarray(combine_frame, format="bgr24")
            asyncio.run_coroutine_threadsafe(video_track._queue.put(new_frame),
                                             loop)

        logger.info('Wav2Lip 处理帧线程停止...')

    def render(self,
               quit_event,
               loop=None,
               audio_track=None,
               video_track=None):
        self.tts.render(quit_event)
        self.init_customindex()
        process_thread = Thread(target=self.process_frames,
                                args=(quit_event, loop, audio_track,
                                      video_track))
        process_thread.start()

        # 核心修复：将 ASR 运行移至独立线程。
        # 避免在下方 while 循环中因为 video_track 积压导致 sleep 时，连带把声音生产也给停了。
        def asr_worker():
            while not quit_event.is_set():
                self.asr.run_step()
                time.sleep(0.001)

        asr_thread = Thread(target=asr_worker)
        asr_thread.start()

        while not quit_event.is_set():
            # 这里不再需要复杂的休眠逻辑，交给 process_frames 的队列机制处理即可
            time.sleep(1)

    def stop(self):
        if hasattr(self, 'inference_quit_event'):
            self.inference_quit_event.set()
            try:
                self.inference_thread.join(timeout=5)
                if self.inference_thread.is_alive():
                    logger.error("推理线程停止超时")
            except Exception as e:
                logger.error(f"停止推理线程异常: {e}")

        # 清理队列
        self._clear_frame_queue()
        self._clear_audio_queues()

        logger.info('Wav2Lip 线程终止...')
    def clear_queue(self):
        # 清理队列
        self._clear_frame_queue()
        self._clear_audio_queues()
