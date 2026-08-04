import numpy as np
import queue
from baseasr import BaseASR
from wav2lip256 import audio
from loguru import logger


class LipASR(BaseASR):

    def run_step(self):
        # 获取音频帧
        real_count = 0
        silence_count = 0
        for _ in range(self.batch_size * 2):
            frame, type = self.get_audio_frame()
            self.frames.append(frame)
            self._put_drop_oldest(self.output_queue, (frame, type))
            if type == 0:
                real_count += 1
            else:
                silence_count += 1

        # 上下文不足时不运行
        if len(self.frames) <= self.stride_left_size + self.stride_right_size:
            return

        inputs = np.concatenate(self.frames)  # [N * chunk]
        mel = audio.melspectrogram(inputs)

        if real_count > 0:
            logger.debug(
                f"[AUDIO_DIAG] ASR run_step: real={real_count} silence={silence_count} "
                f"frames_buf={len(self.frames)} mel_shape={mel.shape} "
                f"asr_queue={self.queue.qsize()} out_queue={self.output_queue.qsize()} "
                f"feat_queue={self.feat_queue.qsize()}"
            )
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
        self._put_drop_oldest(self.feat_queue, mel_chunks)

        # 丢弃旧数据以节省内存
        self.frames = self.frames[-(self.stride_left_size +
                                    self.stride_right_size):]

    def _put_drop_oldest(self, target_queue, item):
        try:
            # 引入阻塞背压，让 ASR 处理速度被下游消耗速度限制，防止堆积
            target_queue.put(item, block=True, timeout=2.0)
            return
        except queue.Full:
            pass
        except Exception:
            try:
                target_queue.put(item, block=False)
                return
            except Exception:
                pass

        # 兜底死锁防护：只有在阻塞2秒后依然塞不进去，为了防止管线假死，丢弃老旧帧腾出空间
        try:
            target_queue.get_nowait()
            if target_queue is self.output_queue:
                self.output_frames_dropped += 1
                if self.output_frames_dropped <= 5 or self.output_frames_dropped % 50 == 0:
                    logger.warning(
                        f"[AUDIO_DIAG] ASR output_queue full; drop_oldest "
                        f"dropped={self.output_frames_dropped} "
                        f"queue={self.output_queue.qsize()}"
                    )
            elif target_queue is self.feat_queue:
                self.feat_batches_dropped += 1
                if self.feat_batches_dropped <= 5 or self.feat_batches_dropped % 20 == 0:
                    logger.warning(
                        f"[AUDIO_DIAG] ASR feat_queue full; drop_oldest "
                        f"dropped={self.feat_batches_dropped} "
                        f"queue={self.feat_queue.qsize()}"
                    )
        except Exception:
            pass
        try:
            target_queue.put_nowait(item)
        except Exception:
            pass
