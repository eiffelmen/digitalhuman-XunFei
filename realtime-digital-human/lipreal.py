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
from threading import Thread, Event, Lock

import asyncio
from lipasr import LipASR
from av import AudioFrame, VideoFrame
from wav2lip256.models import Wav2Lip
from basereal import BaseReal
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
from loguru import logger
from collections import OrderedDict
from perf_logger import elapsed_ms, log_perf, log_timepoint, now

import warnings

warnings.filterwarnings("ignore", category=UserWarning)

device = 'cuda' if torch.cuda.is_available() else 'cpu'
logger.info('正在使用{}进行推理。'.format(device))
torch.backends.cudnn.benchmark = True


def _device_name():
    if device == 'cuda':
        return torch.cuda.get_device_name(0)
    return 'cpu'


def _cuda_mem_mb():
    if device != 'cuda':
        return None
    return f"{torch.cuda.memory_allocated() / 1024 / 1024:.1f}"


def _sync_device():
    if device == 'cuda':
        torch.cuda.synchronize()


def _env_float(name, default):
    try:
        return max(0.1, float(os.getenv(name, default) or default))
    except (TypeError, ValueError):
        return default


log_perf("wav2lip", "device", device=device, device_name=_device_name())


def _normalize_backend(backend=None):
    return (backend or os.getenv("WAV2LIP_BACKEND", "pytorch")).strip().lower()


def _model_backend(model):
    return getattr(model, "backend_name", "pytorch")


def _load(checkpoint_path):
    if device == 'cuda':
        checkpoint = torch.load(checkpoint_path)
    else:
        checkpoint = torch.load(checkpoint_path,
                                map_location=lambda storage, loc: storage)
    return checkpoint


def load_model(path, backend=None, engine_path=None, batch_size=16, modelres=256):
    start = now()
    backend = _normalize_backend(backend)
    if backend in {"trt", "tensorrt"}:
        engine_path = engine_path or os.getenv(
            "WAV2LIP_ENGINE_PATH", "./wav2lip256/wav2lip_fp16.engine"
        )
        logger.info("从 {} 加载 TensorRT Wav2Lip engine。".format(engine_path))
        from wav2lip_tensorrt import TensorRTWav2Lip

        model = TensorRTWav2Lip(engine_path, device=device)
        _sync_device()
        log_perf(
            "wav2lip",
            "load_model",
            elapsed_ms(start),
            backend="tensorrt",
            engine_path=engine_path,
            device=device,
            device_name=_device_name(),
            batch_size=batch_size,
            modelres=modelres,
            cuda_mem_mb=_cuda_mem_mb(),
        )
        return model

    if backend != "pytorch":
        raise ValueError(
            f"Unsupported Wav2Lip backend: {backend}. Use pytorch or tensorrt."
        )

    model = Wav2Lip()
    logger.info("从 {} 加载检查点。".format(path))
    checkpoint = _load(path)
    s = checkpoint["state_dict"]
    new_s = {}
    for k, v in s.items():
        new_s[k.replace('module.', '')] = v
    model.load_state_dict(new_s)

    model = model.to(device)
    model = model.eval()
    _sync_device()
    log_perf(
        "wav2lip",
        "load_model",
        elapsed_ms(start),
        backend="pytorch",
        device=device,
        device_name=_device_name(),
        cuda_mem_mb=_cuda_mem_mb(),
    )
    return model


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
    start = now()
    logger.info('模型预热中...')
    img_batch = torch.ones(batch_size, 6, modelres, modelres).to(device)
    mel_batch = torch.ones(batch_size, 1, 80, 16).to(device)
    model(mel_batch, img_batch)
    _sync_device()
    log_perf(
        "wav2lip",
        "warm_up",
        elapsed_ms(start),
        backend=_model_backend(model),
        device=device,
        device_name=_device_name(),
        batch_size=batch_size,
        modelres=modelres,
        cuda_mem_mb=_cuda_mem_mb(),
    )


# def read_imgs(img_list, flag=False):
#     logger.info('读取图像中...')

#     def load_image(img_path):
#         return cv2.imread(img_path, cv2.IMREAD_GRAYSCALE if flag else cv2.IMREAD_COLOR)

#     with ThreadPoolExecutor(max_workers=min(32, os.cpu_count() + 4)) as executor:
#         return list(tqdm(executor.map(load_image, img_list), total=len(img_list)))


class LazyImageCycle:
    def __init__(self, img_list, flag=False, cache_size=None, prefetch=None):
        self.paths = list(img_list)
        self.flag = flag
        self.cache_size = max(1, int(cache_size or os.getenv("LS_IMAGE_CACHE_SIZE", "1200")))
        self.prefetch = max(0, int(prefetch or os.getenv("LS_IMAGE_PREFETCH", "32")))
        self._cache = OrderedDict()
        self._futures = OrderedDict()
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=max(2, min(8, (os.cpu_count() or 4))),
            thread_name_prefix="lazy_img_loader",
        )
        self.is_lazy = True
        logger.info(
            f"LazyImageCycle initialized frames={len(self.paths)} "
            f"flag={self.flag} cache_size={self.cache_size} prefetch={self.prefetch}"
        )

    def __len__(self):
        return len(self.paths)

    def __bool__(self):
        return bool(self.paths)

    def _normalize_index(self, idx):
        if not self.paths:
            raise IndexError("empty image cycle")
        return int(idx) % len(self.paths)

    def _load_image(self, idx):
        img = cv2.imread(
            self.paths[idx],
            cv2.IMREAD_GRAYSCALE if self.flag else cv2.IMREAD_COLOR,
        )
        if img is None:
            raise RuntimeError(f"failed to read image: {self.paths[idx]}")
        return img

    def _remember(self, idx, img):
        self._cache[idx] = img
        self._cache.move_to_end(idx)
        while len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)

    def _schedule_prefetch_locked(self, center_idx):
        if self.prefetch <= 0:
            return
        for offset in range(1, self.prefetch + 1):
            for candidate in (
                self._normalize_index(center_idx + offset),
                self._normalize_index(center_idx - offset),
            ):
                if candidate in self._cache or candidate in self._futures:
                    continue
                self._futures[candidate] = self._executor.submit(
                    self._load_image,
                    candidate,
                )
        while len(self._futures) > self.cache_size:
            _, future = self._futures.popitem(last=False)
            future.cancel()

    def __getitem__(self, idx):
        idx = self._normalize_index(idx)
        future = None
        with self._lock:
            cached = self._cache.get(idx)
            if cached is not None:
                self._cache.move_to_end(idx)
                self._schedule_prefetch_locked(idx)
                return cached
            future = self._futures.pop(idx, None)

        img = future.result() if future is not None else self._load_image(idx)
        with self._lock:
            self._remember(idx, img)
            self._schedule_prefetch_locked(idx)
        return img

    def prefetch_indices(self, center_idx):
        with self._lock:
            self._schedule_prefetch_locked(self._normalize_index(center_idx))


def read_imgs(img_list, flag=False):
    return LazyImageCycle(img_list, flag=flag)


def __mirror_index(size, index):
    turn = index // size
    res = index % size
    if turn % 2 == 0:
        return res
    else:
        return size - res - 1

def _drain_queue_nowait(target_queue):
    cleared = 0
    while True:
        try:
            target_queue.get_nowait()
            cleared += 1
        except Exception:
            break
    return cleared


def _is_idle_frame_item(item):
    try:
        res_frame = item[0]
        audio_frames = item[2]
    except Exception:
        return False

    if res_frame is not None:
        return False
    if audio_frames is None:
        return True
    try:
        return all(audio_type != 0 for _, audio_type in audio_frames)
    except Exception:
        return False


def _consume_latest_queue_value(target_queue):
    if target_queue is None:
        return None

    value = None
    while True:
        try:
            value = target_queue.get_nowait()
        except Exception:
            break
    return value


def _replace_queue_value(target_queue, value):
    if target_queue is None:
        return

    _consume_latest_queue_value(target_queue)
    try:
        target_queue.put_nowait(value)
    except Exception:
        pass


@torch.inference_mode()
def inference(quit_event, batch_size, face_list_cycle, audio_feat_queue,
              audio_out_queue, res_frame_queue, model, ready_event,
              reset_event=None, fast_speech_event=None,
              speech_start_index_queue=None):
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
        _inf_count = 0
        _inf_idle_count = 0
        _inf_silence_count = 0
        _inf_real_count = 0
        _inf_audio_miss_count = 0
        queue_put_diag_interval_s = float(
            os.environ.get("RESULT_QUEUE_PUT_DIAG_INTERVAL_S", "5")
        )
        _queue_put_has_logged = False
        _last_queue_put_diag_mono = 0.0
        _queue_put_slow_count = 0
        _queue_put_slow_total_ms = 0.0
        _queue_put_slow_max_ms = 0.0
        _queue_put_slow_kind_counts = {}

        def _put_res_frame(item, frame_kind):
            nonlocal _queue_put_has_logged
            nonlocal _last_queue_put_diag_mono
            nonlocal _queue_put_slow_count
            nonlocal _queue_put_slow_total_ms
            nonlocal _queue_put_slow_max_ms
            nonlocal _queue_put_slow_kind_counts

            put_start = now()
            before_size = res_frame_queue.qsize()
            res_frame_queue.put(item)
            put_ms = elapsed_ms(put_start)
            after_size = res_frame_queue.qsize()
            if put_ms > 20 or after_size >= getattr(res_frame_queue, "maxsize", 0):
                _queue_put_slow_count += 1
                _queue_put_slow_total_ms += put_ms
                _queue_put_slow_max_ms = max(_queue_put_slow_max_ms, put_ms)
                _queue_put_slow_kind_counts[frame_kind] = (
                    _queue_put_slow_kind_counts.get(frame_kind, 0) + 1
                )

                current = now()
                if (
                    not _queue_put_has_logged
                    or current - _last_queue_put_diag_mono >= queue_put_diag_interval_s
                ):
                    _queue_put_has_logged = True
                    _last_queue_put_diag_mono = current
                    avg_put_ms = _queue_put_slow_total_ms / max(1, _queue_put_slow_count)
                    kind_counts = ",".join(
                        f"{kind}:{count}"
                        for kind, count in sorted(_queue_put_slow_kind_counts.items())
                    )
                    logger.warning(
                        f"[SYNC_DIAG] wav2lip result queue put slow/blocked "
                        f"events={_queue_put_slow_count} kinds={kind_counts} "
                        f"latest_kind={frame_kind} latest_blocked_ms={put_ms:.2f} "
                        f"avg_blocked_ms={avg_put_ms:.2f} "
                        f"max_blocked_ms={_queue_put_slow_max_ms:.2f} "
                        f"before={before_size} after={after_size} "
                        f"max={getattr(res_frame_queue, 'maxsize', None)} "
                        f"interval_s={queue_put_diag_interval_s:.1f}"
                    )
                    log_perf(
                        "wav2lip",
                        "result_queue_put_slow",
                        put_ms,
                        slow_events=_queue_put_slow_count,
                        kind_counts=kind_counts,
                        latest_frame_kind=frame_kind,
                        before_size=before_size,
                        after_size=after_size,
                        queue_max=getattr(res_frame_queue, "maxsize", None),
                        avg_blocked_ms=f"{avg_put_ms:.2f}",
                        max_blocked_ms=f"{_queue_put_slow_max_ms:.2f}",
                        interval_s=f"{queue_put_diag_interval_s:.1f}",
                    )
                    _queue_put_slow_count = 0
                    _queue_put_slow_total_ms = 0.0
                    _queue_put_slow_max_ms = 0.0
                    _queue_put_slow_kind_counts = {}

        _audio_leftover = []

        while not quit_event.is_set():
            if reset_event is not None and reset_event.is_set():
                last_mel_batch = None
                _audio_leftover = []
                start_index = _consume_latest_queue_value(speech_start_index_queue)
                if start_index is not None:
                    index = max(0, int(start_index))
                reset_event.clear()
            fast_first_pending = (
                fast_speech_event is not None and fast_speech_event.is_set()
            )

            _inf_count += 1
            if last_mel_batch is None:
                try:
                    # 恢复超时时间为 0.04s，匹配 Batch 16 的节奏
                    mel_batch = audio_feat_queue.get(block=True, timeout=0.04)
                except queue.Empty:
                    if fast_first_pending:
                        time.sleep(0.001)
                        continue
                    # 队列为空，推送一帧待机帧以维持 WebRTC 心跳
                    _inf_idle_count += 1
                    if _inf_idle_count <= 3 or _inf_idle_count % 250 == 0:
                        logger.debug(
                            f"[AUDIO_DIAG] inference #{_inf_count}: feat_queue EMPTY → idle frame "
                            f"idle_total={_inf_idle_count} out_queue={audio_out_queue.qsize()} "
                            f"res_queue={res_frame_queue.qsize()}"
                        )
                    _put_res_frame(
                        (None, __mirror_index(length, index), None, index),
                        "idle_no_feat",
                    )
                    index += 1
                    continue
            else:
                mel_batch = last_mel_batch
                last_mel_batch = None
            current_batch_size = len(mel_batch)
            current_batch_size = max(1, min(current_batch_size, batch_size))

            # 尝试获取对应的原始音频帧
            is_all_silence = True
            audio_frames = []
            try:
                for _ in range(current_batch_size * 2):
                    if _audio_leftover:
                        frame, type = _audio_leftover.pop(0)
                    else:
                        frame, type = audio_out_queue.get(block=False)
                    audio_frames.append((frame, type))
                    if type == 0:
                        is_all_silence = False
            except queue.Empty:
                # 原始音频还没准备好（TTS传输中或ASR计算中）
                # 此时不能丢弃 mel_batch，存起来下次循环再试，本次先发待机帧
                last_mel_batch = mel_batch
                _inf_audio_miss_count += 1
                got = len(audio_frames)
                
                # 核心修复：把刚才取出来的没凑够的音频存回缓冲，防止吞掉部分开头和中间的声音
                _audio_leftover = audio_frames + _audio_leftover

                if _inf_audio_miss_count <= 5 or _inf_audio_miss_count % 250 == 0:
                    logger.debug(
                        f"[AUDIO_DIAG] inference #{_inf_count}: audio MISS "
                        f"need={current_batch_size * 2} got={got} "
                        f"mel_batch_size={current_batch_size} "
                        f"out_queue={audio_out_queue.qsize()} "
                        f"leftover={len(_audio_leftover)} "
                        f"miss_total={_inf_audio_miss_count}"
                    )
                # 等待几毫秒让ASR队列填满，而不是插入导致画面抽搐和时间轴错乱的发呆帧
                time.sleep(0.002)
                continue

            if is_all_silence:
                _inf_silence_count += 1
                if _inf_silence_count <= 3 or _inf_silence_count % 250 == 0:
                    logger.debug(
                        f"[AUDIO_DIAG] inference #{_inf_count}: SILENCE batch={current_batch_size} "
                        f"silence_total={_inf_silence_count} real_total={_inf_real_count} "
                        f"feat_queue={audio_feat_queue.qsize()} out_queue={audio_out_queue.qsize()}"
                    )
                for i in range(current_batch_size):
                    _put_res_frame(
                        (
                            None,
                            __mirror_index(length, index),
                            audio_frames[i * 2:i * 2 + 2],
                            index,
                        ),
                        "silence",
                    )
                    index += 1
            else:
                _inf_real_count += 1
                logger.debug(
                    f"[AUDIO_DIAG] inference #{_inf_count}: REAL batch={current_batch_size} "
                    f"real_total={_inf_real_count} silence_total={_inf_silence_count} "
                    f"audio_miss_total={_inf_audio_miss_count} "
                    f"feat_queue={audio_feat_queue.qsize()} out_queue={audio_out_queue.qsize()}"
                )
                if fast_first_pending:
                    start_index = _consume_latest_queue_value(
                        speech_start_index_queue
                    )
                    if start_index is not None:
                        index = max(0, int(start_index))
                t = time.perf_counter()
                img_batch = []
                batch_start_index = index
                for i in range(current_batch_size):
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

                _sync_device()
                model_start = now()
                with torch.no_grad():
                    pred = model(mel_batch, img_batch)
                _sync_device()
                model_duration_ms = elapsed_ms(model_start)
                pred = pred.cpu().numpy().transpose(0, 2, 3, 1) * 255.
                if fast_first_pending:
                    cleared_frames = _drain_queue_nowait(res_frame_queue)
                    fast_speech_event.clear()
                    log_perf(
                        "wav2lip",
                        "fast_first_frame_inference",
                        model_duration_ms,
                        backend=_model_backend(model),
                        device=device,
                        device_name=_device_name(),
                        batch_size=batch_size,
                        first_batch_size=current_batch_size,
                        start_index=batch_start_index,
                        start_avatar_index=__mirror_index(length, batch_start_index),
                        cleared_wav2lip_frames=cleared_frames,
                        cuda_mem_mb=_cuda_mem_mb(),
                    )

                counttime += (time.perf_counter() - t)
                count += current_batch_size
                if count >= 100: # 恢复日志打印频率
                    fps = count / counttime
                    logger.info(f"实际平均推理FPS:{fps:.4f}")
                    log_perf(
                        "wav2lip",
                        "inference",
                        counttime * 1000,
                        backend=_model_backend(model),
                        device=device,
                        device_name=_device_name(),
                        frames=count,
                        batch_size=batch_size,
                        last_batch_size=current_batch_size,
                        fps=f"{fps:.4f}",
                        avg_frame_ms=f"{counttime * 1000 / count:.2f}",
                        last_model_ms=f"{model_duration_ms:.2f}",
                        cuda_mem_mb=_cuda_mem_mb(),
                    )
                    count = 0
                    counttime = 0

                for i, res_frame in enumerate(pred):
                    _put_res_frame(
                        (res_frame, __mirror_index(length, index),
                         audio_frames[i * 2:i * 2 + 2], index),
                        "real",
                    )
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
        self.bg_img_path = opt.bg_img
        self.bg_fallback_bgr = self._parse_bgr_env(
            os.getenv("WEBRTC_BG_FALLBACK_BGR"),
            (160, 68, 10),
        )
        self.bg_img = cv2.imread(self.bg_img_path) if self.bg_img_path else None
        if self.bg_img is None:
            logger.warning(
                f"背景图读取失败: {self.bg_img_path}, "
                f"将使用兜底背景 BGR={self.bg_fallback_bgr}"
            )

        self.batch_size = opt.batch_size  # 恢复为原始批次大小以提升稳定性
        self.res_frame_queue = queue.Queue(self.batch_size * 2)
        self.model = model
        self._media_loop = None
        self._audio_track = None
        self._video_track = None
        self.inference_reset_event = Event()
        self.fast_speech_event = Event()
        self.speech_start_index_queue = queue.Queue(maxsize=1)
        self._idle_frame_index = 0
        self._next_render_linear_index = 0
        self._last_render_linear_index = None
        self._last_render_avatar_index = None
        self._speech_start_reset_trace_id = None
        self.video_queue_max = int(
            os.getenv(
                "WEBRTC_VIDEO_BACKPRESSURE_FRAMES",
                os.getenv("WEBRTC_VIDEO_QUEUE_MAX", "16"),
            )
            or 16
        )
        self.sync_speech_start_index = os.getenv(
            "WAV2LIP_SYNC_SPEECH_START_INDEX", "1"
        ).lower() not in {"0", "false", "no"}
        self.speech_start_bridge_frames = max(
            0, int(os.getenv("WAV2LIP_SPEECH_START_BRIDGE_FRAMES", "0") or 0)
        )
        self.clear_tracks_on_speech = os.getenv(
            "WEBRTC_CLEAR_TRACKS_ON_SPEECH", "0"
        ).lower() in {"1", "true", "yes"}
        self.video_max_width = int(os.getenv("WEBRTC_VIDEO_MAX_WIDTH", "540") or 0)
        self.video_max_height = int(os.getenv("WEBRTC_VIDEO_MAX_HEIGHT", "960") or 0)
        self.video_scale = float(os.getenv("WEBRTC_VIDEO_SCALE", "1.0") or 1.0)
        self.render_fps = _env_float(
            "WEBRTC_RENDER_FPS",
            _env_float("WEBRTC_VIDEO_FPS", 25.0),
        )
        self.render_frame_interval = 1.0 / self.render_fps
        self.render_cache_size = int(os.getenv("WEBRTC_RENDER_CACHE_SIZE", "1024") or 0)
        self.render_preload = os.getenv("WEBRTC_RENDER_PRELOAD", "1").lower() not in {
            "0",
            "false",
            "no",
        }
        self._render_cache = OrderedDict()
        self._render_src_size = (0, 0)
        self._render_output_size = (0, 0)
        self._render_output_scale = 1.0
        self._render_bg_img = None
        logger.info(
            "WebRTC output config: "
            f"queue_backpressure_frames={self.video_queue_max}, "
            f"sync_speech_start_index={self.sync_speech_start_index}, "
            f"speech_start_bridge_frames={self.speech_start_bridge_frames}, "
            f"clear_tracks_on_speech={self.clear_tracks_on_speech}, "
            f"max_width={self.video_max_width}, "
            f"max_height={self.video_max_height}, "
            f"scale={self.video_scale}, "
            f"render_fps={self.render_fps:.2f}, "
            f"render_cache_size={self.render_cache_size}, "
            f"render_preload={self.render_preload}"
        )

        self._init_avatar(avatar)

        self.asr = LipASR(opt, self)
        self.asr.batch_size = self.batch_size  # 同步 ASR 批次大小，防止维数不匹配报错
        self.asr.warm_up()

        self.inference_ready = Event()
        self._init_inference_thread()

    def update_bg_img(self, bg_img_path):
        logger.info(f'更新背景图片到: {bg_img_path}')
        self.bg_img_path = bg_img_path
        self.bg_img = cv2.imread(bg_img_path)
        if self.bg_img is None:
            logger.warning(
                f"背景图读取失败: {bg_img_path}, "
                f"将使用兜底背景 BGR={self.bg_fallback_bgr}"
            )
        self._configure_render_assets(reset_cache=False)

    def _init_avatar(self, avatar):
        self.frame_list_cycle, self.face_list_cycle, self.coord_list_cycle, self.mask_list_cycle = avatar
        self._configure_render_assets(reset_cache=True)

    def _init_inference_thread(self):
        self.inference_quit_event = Event()
        self.inference_ready.clear()
        self.inference_thread = Thread(
            target=inference,
            args=(self.inference_quit_event, self.batch_size,
                  self.face_list_cycle, self.asr.feat_queue,
                  self.asr.output_queue, self.res_frame_queue, self.model,
                  self.inference_ready, self.inference_reset_event,
                  self.fast_speech_event, self.speech_start_index_queue),
            daemon=True)
        self.inference_thread.start()
        self.inference_ready.wait(timeout=5.0)  # 添加超时以防止死锁

    def _drain_queue(self, q):
        size = 0
        try:
            while True:
                q.get_nowait()
                size += 1
        except Exception:
            pass
        return size

    def _clear_frame_queue(self):
        return self._drain_queue(self.res_frame_queue)

    def _clear_frame_queue_keep_idle_tail(self, keep_tail=0):
        drained = []
        while True:
            try:
                drained.append(self.res_frame_queue.get_nowait())
            except Exception:
                break

        if keep_tail <= 0 or not drained:
            return len(drained), 0, None

        idle_tail = []
        for item in reversed(drained):
            if not _is_idle_frame_item(item):
                break
            idle_tail.append(item)
            if len(idle_tail) >= keep_tail:
                break

        idle_tail.reverse()
        retained = 0
        last_retained_linear_index = None
        for item in idle_tail:
            try:
                self.res_frame_queue.put_nowait(item)
                retained += 1
                if len(item) >= 4:
                    last_retained_linear_index = item[3]
            except Exception:
                break

        return len(drained) - retained, retained, last_retained_linear_index

    def _clear_audio_queues(self):
        # 清理ASR相关的队列
        input_size = self.asr.queue.qsize()
        self.asr.queue.queue.clear()
        output_size = self._drain_queue(self.asr.output_queue)
        feat_size = self._drain_queue(self.asr.feat_queue)
        return input_size, output_size, feat_size

    def _media_track_queue_sizes(self):
        audio_size = 0
        video_size = 0
        for name, track in (("audio", self._audio_track), ("video", self._video_track)):
            q = getattr(track, "_queue", None)
            if q is None:
                continue
            try:
                if name == "audio":
                    audio_size = q.qsize()
                else:
                    video_size = q.qsize()
            except Exception:
                pass
        return audio_size, video_size

    def _clear_media_track_queues(self):
        if self._audio_track is None and self._video_track is None:
            return 0, 0

        done = Event()
        cleared = {"audio": 0, "video": 0}

        def clear_track_queues():
            for name, track in (("audio", self._audio_track), ("video", self._video_track)):
                q = getattr(track, "_queue", None)
                if q is None:
                    continue
                try:
                    cleared[name] = q.qsize()
                    q._queue.clear()
                except Exception:
                    cleared[name] = 0
            done.set()

        if self._media_loop is not None:
            try:
                self._media_loop.call_soon_threadsafe(clear_track_queues)
                done.wait(timeout=0.3)
            except Exception:
                clear_track_queues()
        else:
            clear_track_queues()

        return cleared["audio"], cleared["video"]

    def _speech_start_linear_index(self, retained_bridge_frames=0,
                                   last_retained_linear_index=None):
        if not self.sync_speech_start_index:
            return None

        start_index = max(0, int(self._next_render_linear_index))
        if last_retained_linear_index is not None:
            start_index = max(start_index, int(last_retained_linear_index) + 1)
        else:
            start_index += max(0, int(retained_bridge_frames or 0))
        return start_index

    def _prepare_first_audio_frame(self):
        enabled = os.getenv("WAV2LIP_FAST_FIRST_FRAME", "1").lower() not in {
            "0",
            "false",
            "no",
        }
        if not enabled or self.speaking:
            logger.info(f"LipReal._prepare_first_audio_frame: skipping (enabled={enabled}, speaking={self.speaking})")
            return

        logger.info("LipReal._prepare_first_audio_frame: not speaking, clearing queues for fast first frame")
        start = now()
        first_batch_size = int(os.getenv("WAV2LIP_FIRST_BATCH_SIZE", "4") or 4)
        first_batch_size = max(1, min(first_batch_size, self.batch_size))

        # 不清空 asr.queue：保留 TTS 已推送的音频帧，避免吞掉开头的语音。
        # 只清空 output_queue 和 feat_queue：去掉暖机阶段的静音数据，
        # 让推理线程尽快拿到真正的音频特征。
        input_size = self.asr.queue.qsize()
        output_size = self._drain_queue(self.asr.output_queue)
        feat_size = self._drain_queue(self.asr.feat_queue)
        frame_size, retained_bridge_frames, last_retained_linear_index = (
            self._clear_frame_queue_keep_idle_tail(
                self.speech_start_bridge_frames
            )
        )
        if self.clear_tracks_on_speech:
            audio_track_size, video_track_size = self._clear_media_track_queues()
            preserved_audio_track_size = 0
            preserved_video_track_size = 0
        else:
            audio_track_size = 0
            video_track_size = 0
            preserved_audio_track_size, preserved_video_track_size = (
                self._media_track_queue_sizes()
            )
        speech_start_index = self._speech_start_linear_index(
            retained_bridge_frames=retained_bridge_frames,
            last_retained_linear_index=last_retained_linear_index,
        )
        if speech_start_index is not None:
            _replace_queue_value(self.speech_start_index_queue, speech_start_index)

        self.asr.force_next_batch_size = first_batch_size
        self.inference_reset_event.set()
        self.fast_speech_event.set()
        log_perf(
            "wav2lip",
            "fast_first_frame_prepare",
            elapsed_ms(start),
            device="cpu",
            trace_id=self._pending_wav2lip_trace_id,
            segment_index=self._pending_wav2lip_segment_index,
            first_batch_size=first_batch_size,
            cleared_asr_input=input_size,
            cleared_asr_output=output_size,
            cleared_asr_feat=feat_size,
            cleared_wav2lip_frames=frame_size,
            retained_bridge_frames=retained_bridge_frames,
            last_retained_linear_index=last_retained_linear_index,
            speech_start_index=speech_start_index,
            speech_start_avatar_index=(
                self.mirror_index(len(self.frame_list_cycle), speech_start_index)
                if speech_start_index is not None else None
            ),
            last_render_linear_index=self._last_render_linear_index,
            last_render_avatar_index=self._last_render_avatar_index,
            cleared_webrtc_audio=audio_track_size,
            cleared_webrtc_video=video_track_size,
            preserved_webrtc_audio=preserved_audio_track_size,
            preserved_webrtc_video=preserved_video_track_size,
        )

    def flush_talk(self):
        self.tts.flush_talk()
        input_size, output_size, feat_size = self._clear_audio_queues()
        frame_size = self._clear_frame_queue()
        audio_track_size, video_track_size = self._clear_media_track_queues()
        self.inference_reset_event.set()
        self.speaking = False
        logger.info(
            "interrupt flush: cleared queues "
            f"asr_input={input_size}, asr_output={output_size}, "
            f"asr_feat={feat_size}, wav2lip_frames={frame_size}, "
            f"webrtc_audio={audio_track_size}, webrtc_video={video_track_size}"
        )

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
        # OpenCV uint8 路径比逐帧 float32 矩阵转换更省内存，也更稳定。
        if mask_image.ndim == 2:
            mask3 = cv2.cvtColor(mask_image, cv2.COLOR_GRAY2BGR)
        else:
            mask3 = mask_image
        inv_mask3 = cv2.bitwise_not(mask3)
        fg = cv2.multiply(person_image, mask3, scale=1.0 / 255.0)
        bg = cv2.multiply(background_image, inv_mask3, scale=1.0 / 255.0)
        return cv2.add(fg, bg)

    def _target_output_size(self, w, h):
        scale = self.video_scale if self.video_scale > 0 else 1.0
        scale = min(scale, 1.0)

        if self.video_max_width > 0 and w * scale > self.video_max_width:
            scale = min(scale, self.video_max_width / w)
        if self.video_max_height > 0 and h * scale > self.video_max_height:
            scale = min(scale, self.video_max_height / h)

        if scale >= 0.999:
            return w, h, 1.0

        target_w = max(2, int(w * scale))
        target_h = max(2, int(h * scale))
        # 偶数尺寸对 H264/VP8 编码更友好。
        target_w -= target_w % 2
        target_h -= target_h % 2
        return target_w, target_h, scale

    def _resize_output_frame(self, frame):
        h, w = frame.shape[:2]
        target_w, target_h, scale = self._target_output_size(w, h)
        if scale >= 0.999:
            return frame, w, h, w, h, 1.0
        resized = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)
        return resized, w, h, target_w, target_h, scale

    def _parse_bgr_env(self, raw_value, default):
        if not raw_value:
            return default

        try:
            values = [int(part.strip()) for part in raw_value.split(",")]
            if len(values) != 3:
                raise ValueError("expected 3 comma separated values")
            return tuple(max(0, min(255, value)) for value in values)
        except Exception:
            logger.warning(
                f"WEBRTC_BG_FALLBACK_BGR={raw_value} 格式无效，"
                f"使用默认值 {default}"
            )
            return default

    def _fallback_background(self, width, height):
        return np.full((height, width, 3), self.bg_fallback_bgr, dtype=np.uint8)

    def _configure_render_assets(self, reset_cache=False):
        if not hasattr(self, "frame_list_cycle") or not self.frame_list_cycle:
            return

        src_h, src_w = self.frame_list_cycle[0].shape[:2]
        out_w, out_h, out_scale = self._target_output_size(src_w, src_h)
        self._render_src_size = (src_w, src_h)
        self._render_output_size = (out_w, out_h)
        self._render_output_scale = out_scale

        bg_img = self.bg_img
        if bg_img is None:
            bg_img = self._fallback_background(src_w, src_h)
        if bg_img.shape[1] != out_w or bg_img.shape[0] != out_h:
            bg_img = cv2.resize(bg_img, (out_w, out_h), interpolation=cv2.INTER_AREA)
        self._render_bg_img = bg_img

        if reset_cache:
            self._render_cache.clear()

        logger.info(
            "WebRTC render assets: "
            f"source={src_w}x{src_h}, output={out_w}x{out_h}, "
            f"scale={out_scale:.3f}, cache_size={self.render_cache_size}, "
            f"lazy_images={getattr(self.frame_list_cycle, 'is_lazy', False)}"
        )

        if hasattr(self.frame_list_cycle, "prefetch_indices"):
            self.frame_list_cycle.prefetch_indices(0)
        if hasattr(self.mask_list_cycle, "prefetch_indices"):
            self.mask_list_cycle.prefetch_indices(0)
        if hasattr(self.face_list_cycle, "prefetch_indices"):
            self.face_list_cycle.prefetch_indices(0)

        if (
            reset_cache
            and self.render_preload
            and not getattr(self.frame_list_cycle, "is_lazy", False)
            and out_scale < 0.999
            and self.render_cache_size > 0
        ):
            preload_start = now()
            preload_count = min(len(self.frame_list_cycle), self.render_cache_size)
            for idx in range(preload_count):
                self._get_render_assets(idx)
            log_perf(
                "webrtc",
                "preload_render_assets",
                elapsed_ms(preload_start),
                device="cpu",
                frames=preload_count,
                source_size=f"{src_w}x{src_h}",
                output_size=f"{out_w}x{out_h}",
                output_scale=f"{out_scale:.3f}",
                cached=len(self._render_cache),
            )

    def _scale_bbox(self, bbox):
        src_w, src_h = self._render_src_size
        out_w, out_h = self._render_output_size
        y1, y2, x1, x2 = bbox
        scale_x = out_w / src_w if src_w else 1.0
        scale_y = out_h / src_h if src_h else 1.0
        y1 = max(0, min(out_h, int(round(y1 * scale_y))))
        y2 = max(y1 + 1, min(out_h, int(round(y2 * scale_y))))
        x1 = max(0, min(out_w, int(round(x1 * scale_x))))
        x2 = max(x1 + 1, min(out_w, int(round(x2 * scale_x))))
        return y1, y2, x1, x2

    def _get_render_assets(self, idx):
        src_w, src_h = self._render_src_size
        out_w, out_h = self._render_output_size
        out_scale = self._render_output_scale
        if out_scale >= 0.999:
            return (
                self.frame_list_cycle[idx],
                self.mask_list_cycle[idx],
                self.coord_list_cycle[idx],
                src_w,
                src_h,
                out_w,
                out_h,
                out_scale,
            )

        cached = self._render_cache.get(idx)
        if cached is not None:
            self._render_cache.move_to_end(idx)
            return (*cached, src_w, src_h, out_w, out_h, out_scale)

        frame = cv2.resize(self.frame_list_cycle[idx], (out_w, out_h), interpolation=cv2.INTER_AREA)
        mask = cv2.resize(self.mask_list_cycle[idx], (out_w, out_h), interpolation=cv2.INTER_AREA)
        bbox = self._scale_bbox(self.coord_list_cycle[idx])
        if self.render_cache_size > 0:
            self._render_cache[idx] = (frame, mask, bbox)
            while len(self._render_cache) > self.render_cache_size:
                self._render_cache.popitem(last=False)
        return frame, mask, bbox, src_w, src_h, out_w, out_h, out_scale

    def _put_track_frame(self, track, frame, loop):
        if track is None or loop is None:
            return

        submit_frame = getattr(track, "submit_frame", None)
        if callable(submit_frame):
            submit_frame(loop, frame)
            return

        def put_frame():
            try:
                track._queue.put_nowait(frame)
            except Exception as exc:
                logger.debug(f"WebRTC queue put skipped: {exc}")

        try:
            loop.call_soon_threadsafe(put_frame)
        except Exception as exc:
            logger.debug(f"WebRTC loop put skipped: {exc}")

    def _reset_webrtc_for_speech_start(self, trace_key, audio_track, video_track, loop, linear_idx, avatar_idx):
        reset_counts = {}
        for name, track in (("audio", audio_track), ("video", video_track)):
            if track is None:
                continue
            reset = getattr(track, "reset_for_speech_start", None)
            if callable(reset):
                try:
                    reset(loop)
                    reset_counts[name] = "scheduled"
                    continue
                except Exception as exc:
                    logger.debug(f"WebRTC {name} speech reset skipped: {exc}")
            q = getattr(track, "_queue", None)
            if q is not None:
                reset_counts[name] = q.qsize()
                try:
                    q._queue.clear()
                except Exception:
                    pass
        self._speech_start_reset_trace_id = trace_key
        logger.info(
            f"[SYNC_DIAG] reset_for_speech_start trace_key={trace_key} "
            f"linear_idx={linear_idx} avatar_idx={avatar_idx} queues={reset_counts}"
        )
        log_perf(
            "webrtc",
            "speech_start_reset",
            trace_id=trace_key,
            linear_idx=linear_idx,
            avatar_idx=avatar_idx,
            queues=reset_counts,
        )

    def process_frames(self,
                       quit_event,
                       loop=None,
                       audio_track=None,
                       video_track=None):
        self._media_loop = loop
        self._audio_track = audio_track
        self._video_track = video_track
        render_start = now()
        render_count = 0
        render_speaking_count = 0
        render_idle_count = 0
        next_render_time = time.perf_counter()
        _render_audio_push = 0
        _render_audio_silence = 0
        _render_video_skip = 0
        _last_speaking_state = None
        _render_backpressure_count = 0

        while not quit_event.is_set():
            # 视频队列背压：音视频必须同步推进，避免音画漂移。
            # 视频队列已从 6 帧增大到 12 帧，背压触发频率大幅降低。
            if video_track is not None and video_track._queue.qsize() >= self.video_queue_max:
                _render_backpressure_count += 1
                if _render_backpressure_count <= 5 or _render_backpressure_count % 200 == 0:
                    logger.warning(
                        f"[SYNC_DIAG] render backpressure video_queue={video_track._queue.qsize()} "
                        f"limit={self.video_queue_max} audio_queue={audio_track._queue.qsize() if audio_track else -1} "
                        f"trace_id={getattr(self, '_pending_wav2lip_trace_id', None)} "
                        f"linear_idx={getattr(self, '_next_render_linear_index', None)} "
                        f"count={_render_backpressure_count}"
                    )
                time.sleep(0.005)
                continue

            try:
                frame_item = self.res_frame_queue.get(block=True, timeout=0.04)
                if len(frame_item) >= 4:
                    res_frame, idx, audio_frames, linear_idx = frame_item[:4]
                else:
                    res_frame, idx, audio_frames = frame_item
                    linear_idx = self._next_render_linear_index
            except queue.Empty:
                linear_idx = self._next_render_linear_index
                idx = self.mirror_index(len(self.frame_list_cycle), linear_idx)
                res_frame = None
                audio_frames = None
            combine_needs_resize = False
            idle_frame = (
                audio_frames is None
                or (audio_frames[0][1] != 0 and audio_frames[1][1] != 0)
            )
            if idle_frame:
                linear_idx = self._next_render_linear_index
                idx = self.mirror_index(len(self.frame_list_cycle), linear_idx)

            # 连续两帧均为静音数据，或者没有音频数据（处于等待状态）
            if idle_frame:
                self.speaking = False
                audiotype = audio_frames[0][1] if audio_frames is not None else 0
                # 自定义视频播放
                if self.custom_index.get(audiotype) is not None:
                    mirindex = self.mirror_index(
                        len(self.custom_img_cycle[audiotype]),
                        self.custom_index[audiotype])
                    combine_frame = self.custom_img_cycle[audiotype][mirindex]
                    self.custom_index[audiotype] += 1
                    combine_needs_resize = True
                    src_h, src_w = combine_frame.shape[:2]
                    out_w, out_h, out_scale = self._target_output_size(src_w, src_h)
                else:
                    (
                        combine_frame,
                        mask_frame,
                        _,
                        src_w,
                        src_h,
                        out_w,
                        out_h,
                        out_scale,
                    ) = self._get_render_assets(idx)
                    combine_frame = self.blend_images(combine_frame,
                                                      mask_frame, self._render_bg_img)
            else:
                self.speaking = True
                (
                    base_frame,
                    mask_frame,
                    bbox,
                    src_w,
                    src_h,
                    out_w,
                    out_h,
                    out_scale,
                ) = self._get_render_assets(idx)
                # 性能优化：禁止使用 copy.deepcopy，改用高效的 .copy()
                combine_frame = base_frame.copy()
                y1, y2, x1, x2 = bbox
                try:
                    res_frame = cv2.resize(res_frame.astype(np.uint8),
                                           (x2 - x1, y2 - y1))
                except:
                    continue

                combine_frame[y1:y2, x1:x2] = res_frame
                combine_frame = self.blend_images(combine_frame, mask_frame,
                                                  self._render_bg_img)

            trace_id = getattr(self, "_pending_wav2lip_trace_id", None)
            if self.speaking:
                if trace_id:
                    should_reset = self._speech_start_reset_trace_id != trace_id
                    reset_key = trace_id
                else:
                    should_reset = _last_speaking_state is not True
                    reset_key = f"linear:{linear_idx}"
                if should_reset:
                    self._reset_webrtc_for_speech_start(
                        reset_key,
                        audio_track,
                        video_track,
                        loop,
                        linear_idx,
                        idx,
                    )

            if _last_speaking_state is None or _last_speaking_state != self.speaking:
                logger.info(
                    f"[SYNC_DIAG] speaking_state_change speaking={self.speaking} "
                    f"trace_id={getattr(self, '_pending_wav2lip_trace_id', None)} "
                    f"segment_index={getattr(self, '_pending_wav2lip_segment_index', None)} "
                    f"linear_idx={linear_idx} avatar_idx={idx} idle={idle_frame} "
                    f"res_queue={self.res_frame_queue.qsize()} "
                    f"audio_queue={audio_track._queue.qsize() if audio_track else -1} "
                    f"video_queue={video_track._queue.qsize() if video_track else -1}"
                )
                log_timepoint(
                    "Wav2Lip",
                    "说话状态切换",
                    trace_id=getattr(self, "_pending_wav2lip_trace_id", None),
                    segment_index=getattr(self, "_pending_wav2lip_segment_index", None),
                    speaking=self.speaking,
                    linear_idx=linear_idx,
                    avatar_idx=idx,
                )
                _last_speaking_state = self.speaking

            # 音画同步优化：优先推送音频包
            if audio_frames is not None:
                _has_real_audio = any(t == 0 for _, t in audio_frames)
                if _has_real_audio:
                    _render_audio_push += 1
                else:
                    _render_audio_silence += 1
                if _render_audio_push <= 5 or _render_audio_push % 250 == 0:
                    logger.debug(
                        f"[AUDIO_DIAG] render: real_audio={_render_audio_push} "
                        f"silence={_render_audio_silence} video_skip={_render_video_skip} "
                        f"speaking={self.speaking} idle={idle_frame} "
                        f"vq={video_track._queue.qsize() if video_track else -1} "
                        f"aq={audio_track._queue.qsize() if audio_track else -1}"
                    )
                for audio_frame in audio_frames:
                    frame, _ = audio_frame
                    frame = (frame * 32767).astype(np.int16)
                    new_frame = AudioFrame(format='s16',
                                           layout='mono',
                                           samples=frame.shape[0])
                    new_frame.planes[0].update(frame.tobytes())
                    new_frame.sample_rate = 16000
                    self._put_track_frame(audio_track, new_frame, loop)
            else:
                _render_audio_silence += 1
                # 维持 40ms 的静音（20ms * 2）以匹配 25fps 的视频节奏
                silence_frame = np.zeros(self.chunk, dtype=np.int16)
                for _ in range(2):
                    new_frame = AudioFrame(format='s16', layout='mono', samples=self.chunk)
                    new_frame.planes[0].update(silence_frame.tobytes())
                    new_frame.sample_rate = 16000
                    self._put_track_frame(audio_track, new_frame, loop)

            # 音频包推送后再进行耗时的视频转换，确保声音优先
            if combine_needs_resize:
                combine_frame, src_w, src_h, out_w, out_h, out_scale = (
                    self._resize_output_frame(combine_frame)
                )
            new_frame = VideoFrame.from_ndarray(combine_frame, format="bgr24")
            if (
                self.speaking
                and getattr(self, "_pending_wav2lip_waiting", False)
                and not getattr(self, "_pending_wav2lip_first_output_logged", False)
            ):
                self._pending_wav2lip_first_output_logged = True
                self._pending_wav2lip_waiting = False
                log_timepoint(
                    "Wav2Lip",
                    "流式输出第一帧",
                    trace_id=self._pending_wav2lip_trace_id,
                    segment_index=self._pending_wav2lip_segment_index,
                    source_size=f"{src_w}x{src_h}",
                    output_size=f"{out_w}x{out_h}",
                    output_scale=f"{out_scale:.3f}",
                    video_queue=video_track._queue.qsize() if video_track is not None else -1,
                    audio_queue=audio_track._queue.qsize() if audio_track is not None else -1,
                )
                log_perf(
                    "trace",
                    "wav2lip_first_output_frame",
                    trace_id=self._pending_wav2lip_trace_id,
                    segment_index=self._pending_wav2lip_segment_index,
                    linear_idx=linear_idx,
                    avatar_idx=idx,
                    source_size=f"{src_w}x{src_h}",
                    output_size=f"{out_w}x{out_h}",
                    output_scale=f"{out_scale:.3f}",
                    video_queue=video_track._queue.qsize() if video_track is not None else -1,
                    audio_queue=audio_track._queue.qsize() if audio_track is not None else -1,
                    res_queue=self.res_frame_queue.qsize(),
                )
            self._put_track_frame(video_track, new_frame, loop)
            self._last_render_linear_index = linear_idx
            self._last_render_avatar_index = idx
            self._next_render_linear_index = max(
                self._next_render_linear_index, int(linear_idx) + 1
            )
            self._idle_frame_index = self._next_render_linear_index
            if (
                not self.speaking
                and getattr(self, "_pending_wav2lip_waiting", False)
                and not getattr(self, "_pending_wav2lip_first_output_logged", False)
            ):
                _replace_queue_value(
                    self.speech_start_index_queue,
                    self._next_render_linear_index,
                )

            render_count += 1
            if self.speaking:
                render_speaking_count += 1
            else:
                render_idle_count += 1
            if render_count >= 100:
                render_ms = elapsed_ms(render_start)
                log_perf(
                    "webrtc",
                    "render_frames",
                    render_ms,
                    device="cpu",
                    fps=f"{render_count / max(render_ms / 1000, 0.001):.2f}",
                    source_size=f"{src_w}x{src_h}",
                    output_size=f"{out_w}x{out_h}",
                    output_scale=f"{out_scale:.3f}",
                    video_queue=video_track._queue.qsize() if video_track is not None else -1,
                    audio_queue=audio_track._queue.qsize() if audio_track is not None else -1,
                    speaking_frames=render_speaking_count,
                    idle_frames=render_idle_count,
                )
                render_start = now()
                render_count = 0
                render_speaking_count = 0
                render_idle_count = 0

            if self.render_frame_interval > 0:
                next_render_time += self.render_frame_interval
                sleep_s = next_render_time - time.perf_counter()
                if sleep_s > 0:
                    time.sleep(min(sleep_s, self.render_frame_interval))
                elif sleep_s < -self.render_frame_interval * 2:
                    next_render_time = time.perf_counter()

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
                                      video_track),
                                daemon=True)
        process_thread.start()

        # 核心修复：将 ASR 运行移至独立线程。
        # 避免在下方 while 循环中因为 video_track 积压导致 sleep 时，连带把声音生产也给停了。
        def asr_worker():
            while not quit_event.is_set():
                self.asr.run_step()
                time.sleep(0.001)

        asr_thread = Thread(target=asr_worker, daemon=True)
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
