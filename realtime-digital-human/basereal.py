import os
import cv2
import glob
import soundfile as sf
from tqdm import tqdm
from loguru import logger
from concurrent.futures import ThreadPoolExecutor
from perf_logger import log_perf
from ttsreal import (EdgeTTS, VoitsTTS, GSVV2TTS,
                     CosyVoiceTTS, FishTTS, SparkTTS, FlashTTS,
                     IflytekTTS, GonganTTS, GywtTTS)


def read_imgs(img_list):
    """多线程读取图片列表，带进度条显示"""
    logger.info('Reading images...')

    def load_image(img_path):
        return cv2.imread(img_path)

    # 动态计算线程池大小（限制最大32线程）
    max_workers = min(32, (os.cpu_count() or 1) + 4)  # 处理cpu_count返回None的情况

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 使用更紧凑的列表推导式，直接返回处理结果
        return list(tqdm(
            executor.map(load_image, img_list),
            total=len(img_list),
            desc='Loading images'
        ))


class BaseReal:
    def __init__(self, opt):
        self.opt = opt
        self.sample_rate = 16000
        # 320 samples per chunk (20ms * 16000 / 1000)
        self.chunk = self.sample_rate // opt.fps
        # self.sessionid = self.opt.sessionid

        if opt.tts == "edgetts":
            self.tts = EdgeTTS(opt, self)
        elif opt.tts == "gpt-sovits":
            self.tts = VoitsTTS(opt, self)
        elif opt.tts == "gpt-sovits-v2":
            self.tts = GSVV2TTS(opt, self)
        elif opt.tts == "cosyvoice":
            self.tts = CosyVoiceTTS(opt, self)
        elif opt.tts == "fishtts":
            self.tts = FishTTS(opt, self)
        elif opt.tts == "sparktts":
            self.tts = SparkTTS(opt, self)
        elif opt.tts == "flashtts":
            self.tts = FlashTTS(opt,self)
        elif opt.tts == "iflytts":
            self.tts = IflytekTTS(opt, self)
        elif opt.tts == "gongantts":
            self.tts = GonganTTS(opt, self)
        elif opt.tts == "gywttts":
            self.tts = GywtTTS(opt, self)

        self.speaking = False

        self.curr_state = 0
        self._active_tts_trace_id = None
        self._active_tts_segment_index = None
        self._active_tts_first_audio_frame_logged = False
        self.custom_img_cycle = {}
        self.custom_audio_cycle = {}
        self.custom_audio_index = {}
        self.custom_index = {}
        self.custom_opt = {}
        self.__loadcustom()

    def flush_talk(self):
        self.tts.flush_talk()
        self.asr.flush_talk()

    def is_speaking(self) -> bool:
        return self.speaking

    def put_msg_txt(self, msg, trace_id=None, segment_index=None):
        self.tts.put_msg_txt(msg, trace_id=trace_id, segment_index=segment_index)

    def set_active_tts_trace(self, trace_id=None, segment_index=None):
        self._active_tts_trace_id = trace_id
        self._active_tts_segment_index = segment_index
        self._active_tts_first_audio_frame_logged = False

    def clear_active_tts_trace(self):
        self._active_tts_trace_id = None
        self._active_tts_segment_index = None
        self._active_tts_first_audio_frame_logged = False

    def put_audio_frame(self, audio_chunk):  # 16khz 20ms pcm
        if (
            self._active_tts_trace_id
            and not self._active_tts_first_audio_frame_logged
        ):
            self._active_tts_first_audio_frame_logged = True
            log_perf(
                "trace",
                "first_audio_frame_queued",
                trace_id=self._active_tts_trace_id,
                segment_index=self._active_tts_segment_index,
                samples=len(audio_chunk),
            )
        self.asr.put_audio_frame(audio_chunk)

    def pause_talk(self):
        self.tts.flush_talk()
        self.asr.pause_talk()

    def __loadcustom(self):
        for item in self.opt.customopt:
            input_img_list = glob.glob(os.path.join(
                item['imgpath'], '*.[jpJP][pnPN]*[gG]'))
            input_img_list = sorted(input_img_list, key=lambda x: int(
                os.path.splitext(os.path.basename(x))[0]))
            self.custom_img_cycle[item['audiotype']
                                  ] = read_imgs(input_img_list)
            self.custom_audio_cycle[item['audiotype']], sample_rate = sf.read(
                item['audiopath'], dtype='float32')
            self.custom_audio_index[item['audiotype']] = 0
            self.custom_index[item['audiotype']] = 0
            self.custom_opt[item['audiotype']] = item

    def init_customindex(self):
        self.curr_state = 0
        for key in self.custom_audio_index:
            self.custom_audio_index[key] = 0
        for key in self.custom_index:
            self.custom_index[key] = 0

    def mirror_index(self, size, index):
        turn = index // size
        res = index % size
        if turn % 2 == 0:
            return res
        else:
            return size - res - 1

    def get_audio_stream(self, audiotype):
        idx = self.custom_audio_index[audiotype]
        stream = self.custom_audio_cycle[audiotype][idx:idx+self.chunk]
        self.custom_audio_index[audiotype] += self.chunk
        if self.custom_audio_index[audiotype] >= self.custom_audio_cycle[audiotype].shape[0]:
            self.curr_state = 1  # 当前视频不循环播放，切换到静音状态
        return stream

    def set_custom_state(self, audiotype, reinit):
        logger.info(f'set_curr_state: {audiotype}')
        if self.custom_audio_index.get(audiotype) is None:
            return
        self.curr_state = audiotype
        if reinit:
            self.custom_audio_index[audiotype] = 0
            self.custom_index[audiotype] = 0
