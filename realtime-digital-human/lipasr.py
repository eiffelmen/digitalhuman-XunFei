import os

import numpy as np
from baseasr import BaseASR
from wav2lip256 import audio
from perf_logger import elapsed_ms, log_perf, now


class LipASR(BaseASR):

    def run_step(self):
        total_start = now()
        batch_size = int(getattr(self, "force_next_batch_size", 0) or self.batch_size)
        batch_size = max(1, min(batch_size, self.batch_size))
        self.force_next_batch_size = 0

        # 获取音频帧
        target_chunks = batch_size * 2
        step_frames = []
        step_types = []
        while len(step_frames) < target_chunks:
            forced_batch_size = int(getattr(self, "force_next_batch_size", 0) or 0)
            if forced_batch_size:
                batch_size = max(1, min(forced_batch_size, self.batch_size))
                target_chunks = batch_size * 2
                self.force_next_batch_size = 0
                step_frames = []
                step_types = []

            frame, type = self.get_audio_frame()
            step_frames.append(frame)
            step_types.append(type)

        for frame, type in zip(step_frames, step_types):
            self.frames.append(frame)
            self.output_queue.put((frame, type))

        # 上下文不足时不运行
        if len(self.frames) <= self.stride_left_size + self.stride_right_size:
            return

        inputs = np.concatenate(self.frames)  # [N * chunk]
        mel_start = now()
        mel = audio.melspectrogram(inputs)
        mel_duration_ms = elapsed_ms(mel_start)
        # 截取步长部分
        left = max(0, self.stride_left_size * 80 / 50)
        mel_idx_multiplier = 80. * 2 / self.fps
        mel_step_size = 16
        i = 0
        mel_chunks = []

        while i < (len(self.frames) - self.stride_left_size -
                   self.stride_right_size) / 2:
            start_idx = int(left + i * mel_idx_multiplier)
            if start_idx + mel_step_size > len(mel[0]):
                mel_chunks.append(mel[:, len(mel[0]) - mel_step_size:])
            else:
                mel_chunks.append(mel[:, start_idx:start_idx + mel_step_size])
            i += 1
        self.feat_queue.put(mel_chunks)
        self._log_perf(elapsed_ms(total_start), mel_duration_ms, len(mel_chunks), batch_size)

        # 丢弃旧数据以节省内存
        self.frames = self.frames[-(self.stride_left_size +
                                    self.stride_right_size):]

    def _log_perf(self, duration_ms, mel_duration_ms, mel_chunks, batch_size):
        every = max(1, int(os.environ.get("PERF_ASR_EVERY_N", "50")))
        self._perf_asr_count = getattr(self, "_perf_asr_count", 0) + 1
        self._perf_asr_total_ms = getattr(self, "_perf_asr_total_ms", 0.0) + duration_ms
        self._perf_asr_mel_ms = getattr(self, "_perf_asr_mel_ms", 0.0) + mel_duration_ms

        if self._perf_asr_count < every:
            return

        log_perf(
            "asr",
            "mel_feature",
            self._perf_asr_total_ms,
            device="cpu",
            steps=self._perf_asr_count,
            avg_step_ms=f"{self._perf_asr_total_ms / self._perf_asr_count:.2f}",
            avg_mel_ms=f"{self._perf_asr_mel_ms / self._perf_asr_count:.2f}",
            batch_size=self.batch_size,
            last_batch_size=batch_size,
            mel_chunks=mel_chunks,
        )
        self._perf_asr_count = 0
        self._perf_asr_total_ms = 0.0
        self._perf_asr_mel_ms = 0.0
