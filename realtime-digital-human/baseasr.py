import os
import queue
import numpy as np
import torch.multiprocessing as mp
from loguru import logger


class BaseASR:
    def __init__(self, opt, parent=None):
        self.opt = opt
        self.parent = parent

        self.fps = opt.fps  # 20 ms per frame
        self.sample_rate = 16000
        # 320 samples per chunk (20ms * 16000 / 1000)
        self.chunk = self.sample_rate // self.fps
        self.queue = queue.Queue(
            maxsize=max(1, int(os.environ.get("ASR_INPUT_QUEUE_MAX", "250")))
        )
        self.output_queue = mp.Queue(
            maxsize=max(1, int(os.environ.get("ASR_OUTPUT_QUEUE_MAX", "250")))
        )

        self.batch_size = opt.batch_size

        self.frames = []
        self.stride_left_size = opt.l
        self.stride_right_size = opt.r
        self.feat_queue = mp.Queue(2)
        self.input_frames_received = 0
        self.input_frames_dropped = 0
        self.output_frames_dropped = 0
        self.feat_batches_dropped = 0

    def flush_talk(self):
        cleared = self.queue.qsize()
        self.queue.queue.clear()
        if cleared:
            logger.info(f"[AUDIO_DIAG] ASR input queue flushed frames={cleared}")

    def reset(self):
        # 清空所有队列
        cleared_input = self.queue.qsize()
        self.queue.queue.clear()
        cleared_output = 0
        while not self.output_queue.empty():
            try:
                self.output_queue.get_nowait()
                cleared_output += 1
            except:
                break
        cleared_feat = 0
        while not self.feat_queue.empty():
            try:
                self.feat_queue.get_nowait()
                cleared_feat += 1
            except:
                break
        logger.info(
            f"[AUDIO_DIAG] ASR reset queues cleared input={cleared_input} "
            f"output={cleared_output} feat={cleared_feat}"
        )

        # 重置帧缓存
        self.frames = []

        # 重新预热
        self.warm_up()

    def pause_talk(self):
        cleared = self.queue.qsize()
        self.queue.queue.clear()
        if cleared:
            logger.info(f"[AUDIO_DIAG] ASR pause_talk cleared input frames={cleared}")

    def put_audio_frame(self, audio_chunk):  # 16khz 20ms pcm
        self.input_frames_received += 1
        try:
            # 引入阻塞式背压，最多等待2秒。如果下游（Wav2Lip推理）处理太慢，
            # 这里会卡住上游TTS继续塞入，防止无限积压产生严重延迟或吃字
            self.queue.put(audio_chunk, block=True, timeout=2.0)
        except queue.Full:
            # 极端保护机制：只有当等待2秒依旧满载（说明整条管线发生死锁或彻底崩溃），
            # 才丢弃这一帧（不再丢老帧），保证系统不会被无限挂起。
            self.input_frames_dropped += 1
            if self.input_frames_dropped <= 5 or self.input_frames_dropped % 50 == 0:
                logger.warning(
                    f"[AUDIO_DIAG] ASR input queue put timeout (2s); blocked! "
                    f"received={self.input_frames_received} dropped={self.input_frames_dropped} "
                    f"queue={self.queue.qsize()}/{self.queue.maxsize} "
                    f"chunk_samples={len(audio_chunk)}"
                )

    def get_audio_frame(self):
        try:
            frame = self.queue.get(block=True, timeout=0.01)
            type = 0
        except queue.Empty:
            if self.parent and self.parent.curr_state > 1:  # 播放自定义音频
                frame = self.parent.get_audio_stream(self.parent.curr_state)
                type = self.parent.curr_state
            else:
                frame = np.zeros(self.chunk, dtype=np.float32)
                type = 1

        return frame, type

    def is_audio_frame_empty(self) -> bool:
        return self.queue.empty()

    def get_audio_out(self):  # et origin audio pcm to nerf
        return self.output_queue.get()

    def warm_up(self):
        for _ in range(self.stride_left_size + self.stride_right_size):
            audio_frame, type = self.get_audio_frame()
            self.frames.append(audio_frame)
            self.output_queue.put((audio_frame, type))
        for _ in range(self.stride_left_size):
            self.output_queue.get()

    def run_step(self):
        pass

    def get_next_feat(self, block, timeout):
        return self.feat_queue.get(block, timeout)
