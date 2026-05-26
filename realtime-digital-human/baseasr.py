import queue
import numpy as np
import torch.multiprocessing as mp


class BaseASR:
    def __init__(self, opt, parent=None):
        self.opt = opt
        self.parent = parent

        self.fps = opt.fps  # 20 ms per frame
        self.sample_rate = 16000
        # 320 samples per chunk (20ms * 16000 / 1000)
        self.chunk = self.sample_rate // self.fps
        self.queue = queue.Queue()
        self.output_queue = mp.Queue()

        self.batch_size = opt.batch_size

        self.frames = []
        self.stride_left_size = opt.l
        self.stride_right_size = opt.r
        self.feat_queue = mp.Queue(2)

    def flush_talk(self):
        self.queue.queue.clear()

    def reset(self):
        # 清空所有队列
        self.queue.queue.clear()
        while not self.output_queue.empty():
            try:
                self.output_queue.get_nowait()
            except:
                break
        while not self.feat_queue.empty():
            try:
                self.feat_queue.get_nowait()
            except:
                break

        # 重置帧缓存
        self.frames = []

        # 重新预热
        self.warm_up()

    def pause_talk(self):
        self.queue.queue.clear()

    def put_audio_frame(self, audio_chunk):  # 16khz 20ms pcm
        self.queue.put(audio_chunk)

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
