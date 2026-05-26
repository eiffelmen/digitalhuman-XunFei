import numpy as np
from baseasr import BaseASR
from wav2lip256 import audio


class LipASR(BaseASR):

    def run_step(self):
        # 获取音频帧
        for _ in range(self.batch_size * 2):
            frame, type = self.get_audio_frame()
            self.frames.append(frame)
            self.output_queue.put((frame, type))

        # 上下文不足时不运行
        if len(self.frames) <= self.stride_left_size + self.stride_right_size:
            return

        inputs = np.concatenate(self.frames)  # [N * chunk]
        mel = audio.melspectrogram(inputs)
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

        # 丢弃旧数据以节省内存
        self.frames = self.frames[-(self.stride_left_size +
                                    self.stride_right_size):]
