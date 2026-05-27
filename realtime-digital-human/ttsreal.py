import os
import time
import queue
import resampy
import requests
import asyncio
import base64
import edge_tts

import numpy as np
import soundfile as sf
from enum import Enum
from io import BytesIO
from loguru import logger
from typing import Iterator
from threading import Thread
from perf_logger import elapsed_ms, log_perf, now


class State(Enum):
    RUNNING = 0
    PAUSE = 1


class BaseTTS(object):
    def __init__(self, opt, parent):
        self.opt = opt
        self.parent = parent

        self.fps = opt.fps  # 20 ms per frame
        self.sample_rate = 16000
        # 320 samples per chunk (20ms * 16000 / 1000)
        self.chunk = self.sample_rate // self.fps
        self.input_stream = BytesIO()

        self.msgqueue = queue.Queue()
        self.state = State.RUNNING

    def flush_talk(self):
        self.msgqueue.queue.clear()
        self.state = State.PAUSE

    def put_msg_txt(self, msg):
        if len(msg) > 0:
            self.msgqueue.put(msg)

    def render(self, quit_event):
        process_thread = Thread(target=self.process_tts, args=(quit_event,))
        process_thread.start()

    def process_tts(self, quit_event):
        while not quit_event.is_set():
            try:
                msg = self.msgqueue.get(block=True, timeout=1)
                self.state = State.RUNNING
            except queue.Empty:
                continue
            start = now()
            success = True
            try:
                self.txt_to_audio(msg)
            except Exception:
                success = False
                raise
            finally:
                log_perf(
                    "tts",
                    "synthesize",
                    elapsed_ms(start),
                    device="external",
                    sessionid=getattr(self.opt, "sessionid", None),
                    tts_type=getattr(self.opt, "tts", None),
                    tts_server=getattr(self.opt, "TTS_SERVER", None),
                    text_len=len(msg),
                    success=success,
                )
        logger.info('ttsreal thread stop')

    def txt_to_audio(self, msg):
        pass


class EdgeTTS(BaseTTS):
    def txt_to_audio(self, msg):
        t = time.time()
        asyncio.new_event_loop().run_until_complete(
            self.__main(self.opt.voicename, msg))
        logger.info(f'-------Edge-TTS time:{time.time()-t:.3f}s')

        # TODO: fix bug, stream size is 0
        self.input_stream.seek(0, os.SEEK_END)  # 移动到流的末尾
        size = self.input_stream.tell()  # 获取当前的流位置，实际上是流的大小
        logger.info(f'Audio stream size: {size} bytes')

        self.input_stream.seek(0)
        if size > 0:
            stream = self.__create_bytes_stream(self.input_stream)
            streamlen = stream.shape[0]
            idx = 0
            while streamlen >= self.chunk and self.state == State.RUNNING:
                self.parent.put_audio_frame(stream[idx: idx + self.chunk])
                streamlen -= self.chunk
                idx += self.chunk

        self.input_stream.seek(0)
        self.input_stream.truncate()

    def __create_bytes_stream(self, byte_stream):
        stream, sample_rate = sf.read(byte_stream)  # [T*sample_rate,] float64
        logger.info(f'[INFO] tts audio stream {sample_rate}: {stream.shape}')
        stream = stream.astype(np.float32)

        if stream.ndim > 1:
            logger.warning(
                f'[WARN] audio has {stream.shape[1]} channels, only use the first.')
            stream = stream[:, 0]

        if sample_rate != self.sample_rate and stream.shape[0] > 0:
            logger.warning(
                f'[WARN] audio sample rate is {sample_rate}, resampling into {self.sample_rate}.')
            stream = resampy.resample(
                x=stream, sr_orig=sample_rate, sr_new=self.sample_rate)

        return stream

    async def __main(self, voicename: str, text: str):
        communicate = edge_tts.Communicate(text, voicename)

        first = True
        async for chunk in communicate.stream():
            if first:
                first = False
            if chunk["type"] == "audio" and self.state == State.RUNNING:
                self.input_stream.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                pass


class VoitsTTS(BaseTTS):
    def txt_to_audio(self, msg):
        self.stream_tts(
            self.gpt_sovits(
                msg,
                self.opt.REF_FILE,
                self.opt.REF_TEXT,
                "zh",
                self.opt.TTS_SERVER,
            )
        )

    def gpt_sovits(self, text, reffile, reftext, language, server_url) -> Iterator[bytes]:
        start = time.perf_counter()
        req = {
            'text': text,
            'text_lang': language,
            'ref_audio_path': reffile,
            'prompt_text': reftext,
            'prompt_lang': language,
            # 'media_type': 'raw',
            'media_type': 'ogg',
            'streaming_mode': True
        }

        try:
            res = requests.post(
                f"{server_url}/tts",
                json=req,
                stream=True,
            )
            end = time.perf_counter()
            logger.info(f"gpt_sovits Time to make POST: {end-start}s")

            if res.status_code != 200:
                logger.error("Error:", res.text)
                return

            first = True

            # for chunk in res.iter_content(chunk_size=12800):  # 1280 32K*20ms*2
            for chunk in res.iter_content(chunk_size=None):
                logger.info(f"gpt_sovits chunk: {len(chunk)}")

                if first:
                    end = time.perf_counter()
                    logger.info(
                        f"gpt_sovits Time to first chunk: {end-start}s")
                    first = False
                if chunk and self.state == State.RUNNING:
                    yield chunk
        except Exception as e:
            logger.error(e)

    def __create_bytes_stream(self, byte_stream):
        stream, sample_rate = sf.read(byte_stream)  # [T*sample_rate,] float64
        logger.info(f'[INFO]tts audio stream {sample_rate}: {stream.shape}')
        stream = stream.astype(np.float32)
        if stream.ndim > 1:
            logger.warning(
                f'[WARN] audio has {stream.shape[1]} channels, only use the first.')
            stream = stream[:, 0]

        if sample_rate != self.sample_rate and stream.shape[0] > 0:
            logger.warning(
                f'[WARN] audio sample rate is {sample_rate}, resampling into {self.sample_rate}.')
            stream = resampy.resample(
                x=stream, sr_orig=sample_rate, sr_new=self.sample_rate)
        return stream

    def stream_tts(self, audio_stream):
        for chunk in audio_stream:
            if chunk is not None and len(chunk) > 0:
                # stream = np.frombuffer(
                #     chunk, dtype=np.int16).astype(np.float32) / 32767
                # stream = resampy.resample(
                #     x=stream, sr_orig=32000, sr_new=self.sample_rate)
                byte_stream = BytesIO(chunk)
                stream = self.__create_bytes_stream(byte_stream)
                streamlen = stream.shape[0]
                idx = 0
                while streamlen >= self.chunk:
                    self.parent.put_audio_frame(stream[idx:idx+self.chunk])
                    streamlen -= self.chunk
                    idx += self.chunk


class GSVV2TTS(BaseTTS):
    def __init__(self, opt, parent):
        super().__init__(opt, parent)
        self._warm_up_tts()

    def _warm_up_tts(self):
        """预热TTS模型"""
        test_text = "欢迎使用数字人系统。"
        for _ in range(1):
            list(self.gpt_sovits(test_text, self.opt.REF_FILE,
                                 self.opt.REF_TEXT, "zh",
                                 self.opt.TTS_SERVER))

    def txt_to_audio(self, msg):
        self.stream_tts(
            self.gpt_sovits(
                msg,
                self.opt.REF_FILE,
                self.opt.REF_TEXT,
                "zh",
                self.opt.TTS_SERVER,
            )
        )

    # GPT-Sovits-v2 版本
    def gpt_sovits(self, text, reffile, reftext, language, server_url) -> Iterator[bytes]:
        start = time.perf_counter()
        req = {
            'text': text,
            "text_lang": language,
            "ref_audio_path": reffile,
            "aux_ref_audio_paths": [],
            "prompt_lang": "zh",
            "prompt_text": reftext,
            "top_k": 5,
            "top_p": 1.0,
            "temperature": 1.0,
            "text_split_method": "cut0",
            "batch_size": 1,
            "batch_threshold": 0.75,
            "split_bucket": True,
            "speed_factor": 1.0,
            "fragment_interval": 0.3,
            "seed": -1,
            "media_type": "wav",
            "streaming_mode": True,
            "parallel_infer": True,
            "repetition_penalty": 1.35
        }
        res = requests.post(
            f"{server_url}/tts",
            json=req,
            stream=True,
        )
        end = time.perf_counter()
        logger.info(f"gpt_sovits Time to make POST: {end - start}s")

        if res.status_code != 200:
            logger.error("Error:", res.text)
            return

        first_chunk = True
        for chunk in res.iter_content(chunk_size=128000):  # 32000 * 20 * 2
            if chunk:
                if first_chunk:
                    yield chunk
                    first_chunk = False
                    continue

                if self.state == State.RUNNING:
                    yield chunk

        logger.info(f"gpt_sovits v2 response.elapsed: {res.elapsed}")

    def stream_tts(self, audio_stream):
        for chunk in audio_stream:
            if chunk is not None and len(chunk) > 0:
                stream = np.frombuffer(chunk, dtype=np.int16).astype(
                    np.float32) / 32767
                stream = resampy.resample(
                    x=stream, sr_orig=32000, sr_new=self.sample_rate)
                streamlen = stream.shape[0]
                idx = 0
                while streamlen >= self.chunk:
                    self.parent.put_audio_frame(
                        stream[idx:idx + self.chunk])
                    streamlen -= self.chunk
                    idx += self.chunk

    # TODO: GPT-Sovits-v3 版本优化
    # def gpt_sovits(self, text, reffile, reftext, language, server_url) -> Iterator[bytes]:
    #     start = time.perf_counter()
    #     req = {
    #         "text": text,
    #         "text_lang": language,
    #         "prompt_lang": language,
    #         "ref_audio_path": reffile,
    #         "prompt_text": reftext,
    #         "streaming_mode": True,
    #         "media_type": "wav",
    #         "threshold": 30,
    #     }

    #     res = requests.get(
    #         f"{server_url}/tts",
    #         params=req,
    #         stream=True,
    #     )

    #     end = time.perf_counter()
    #     logger.info(f"gpt_sovits Time to make GET request: {end - start}s")

    #     if res.status_code != 200:
    #         logger.error(f"API Error: {res.text}")
    #         return

    #     self.server_sample_rate = int(res.headers.get('sample_rate', 32000))
    #     for chunk in res.iter_content(chunk_size=32000):
    #         if chunk and self.state == State.RUNNING:
    #             yield chunk

    #     logger.info(f"gpt_sovits v3 response latency: {res.elapsed}")

    # def stream_tts(self, audio_stream):
    #     for chunk in audio_stream:
    #         if chunk and len(chunk) > 0:
    #             audio_data = np.frombuffer(
    #                 chunk, dtype=np.int16).astype(np.float32) / 32767
    #             resampled = resampy.resample(
    #                 x=audio_data,
    #                 sr_orig=self.server_sample_rate,
    #                 sr_new=self.sample_rate
    #             )
    #             total_samples = resampled.shape[0]
    #             for offset in range(0, total_samples, self.chunk):
    #                 end_idx = offset + self.chunk
    #                 self.parent.put_audio_frame(resampled[offset:end_idx])


class CosyVoiceTTS(BaseTTS):
    def txt_to_audio(self, msg):
        self.stream_tts(
            self.cosy_voice(
                msg,
                self.opt.REF_FILE,
                self.opt.REF_TEXT,
                self.opt.TTS_SERVER,
            )
        )

    def cosy_voice(self, text, reffile, reftext, server_url) -> Iterator[bytes]:
        start = time.perf_counter()
        payload = {
            'tts_text': text,
            'prompt_text': reftext
        }
        files = [('prompt_wav', ('prompt_wav', open(
            reffile, 'rb'), 'application/octet-stream'))]
        res = requests.request(
            "GET", f"{server_url}/inference_zero_shot", data=payload, files=files, stream=True)

        end = time.perf_counter()
        logger.info(f"cosy_voice Time to make POST: {end-start}s")

        if res.status_code != 200:
            logger.error("Error:", res.text)
            return

        first = True
        for chunk in res.iter_content(chunk_size=None):
            if first:
                end = time.perf_counter()
                logger.info(f"cosy_voice Time to first chunk: {end-start}s")
                first = False
            if chunk and self.state == State.RUNNING:
                yield chunk

    def stream_tts(self, audio_stream):
        for chunk in audio_stream:
            if chunk is not None and len(chunk) > 0:
                stream = np.frombuffer(
                    chunk, dtype=np.int16).astype(np.float32) / 32767
                stream = resampy.resample(
                    x=stream, sr_orig=24000, sr_new=self.sample_rate)
                streamlen = stream.shape[0]
                idx = 0
                while streamlen >= self.chunk:
                    self.parent.put_audio_frame(stream[idx: idx + self.chunk])
                    streamlen -= self.chunk
                    idx += self.chunk


class FishTTS(BaseTTS):
    def txt_to_audio(self, msg):
        self.stream_tts(
            self.fish_speech(
                msg,
                self.opt.REF_FILE,
                self.opt.REF_TEXT,
                self.opt.TTS_SERVER,
            ),
        )

    def fish_speech(self, text, reffile, reftext, server_url) -> Iterator[bytes]:
        start = time.perf_counter()
        req = {
            'text': text,
            'reference_audio': reffile,
            'reference_text': reftext,
            'format': 'wav',
            'streaming': True,
            'use_memory_cache': 'on',
            'latency': 'balanced',
            'temperature': 0,
        }
        try:
            res = requests.post(
                f"{server_url}/v1/tts",
                json=req,
                stream=True,
                headers={
                    "content-type": "application/json",
                },
            )
            end = time.perf_counter()
            logger.info(f"fish_speech Time to make POST: {end-start}s")
            if res.status_code != 200:
                logger.error("Error:", res.text)
                return

            first = True
            for chunk in res.iter_content(chunk_size=17640):  # 1764 44100*20ms*2
                if first:
                    end = time.perf_counter()
                    logger.info(
                        f"fish_speech Time to first chunk: {end-start}s")
                    first = False
                if chunk and self.state == State.RUNNING:
                    yield chunk
        except Exception as e:
            logger.info(e)

    def stream_tts(self, audio_stream):
        first = True
        for chunk in audio_stream:
            if chunk is not None and len(chunk) > 0:
                stream = np.frombuffer(
                    chunk, dtype=np.int16).astype(np.float32) / 32767
                stream = resampy.resample(
                    x=stream, sr_orig=44100, sr_new=self.sample_rate)
                streamlen = stream.shape[0]
                idx = 0
                while streamlen >= self.chunk:
                    if first:
                        first = False
                    self.parent.put_audio_frame(
                        stream[idx:idx+self.chunk])
                    streamlen -= self.chunk
                    idx += self.chunk

        self.parent.put_audio_frame(
            np.zeros(self.chunk, np.float32))


class SparkTTS(BaseTTS):
    def __init__(self, opt, parent):
        super().__init__(opt, parent)
        self._warm_up_tts()

    def _warm_up_tts(self):
        """预热TTS模型"""
        test_text = "欢迎使用数字人系统"
        for _ in range(1):
            list(self.spark_tts(
                test_text,
                self.opt.REF_FILE,
                self.opt.TTS_SERVER
            ))

    def txt_to_audio(self, msg):
        self.stream_tts(
            self.spark_tts(
                msg,
                self.opt.REF_FILE,
                self.opt.TTS_SERVER
            )
        )

    def spark_tts(self, text, reffile, server_url) -> Iterator[bytes]:
        start = time.perf_counter()

        try:
            with open(reffile, "rb") as f:
                audio_bytes = f.read()
            audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
        except Exception as e:
            logger.error(f"读取参考音频失败: {e}")
            return

        payload = {
            "text": text,
            "reference_text": None,
            "reference_audio": audio_base64,
            "temperature": 0.9,
            "top_p": 0.95,
            "top_k": 50,
            "max_tokens": 2048,
            "stream": True
        }

        res = requests.post(
            f"{server_url}/clone_voice",
            json=payload,
            stream=True
        )
        end = time.perf_counter()
        logger.info(f"spark_tts Time to make POST: {end-start}s")

        if res.status_code != 200:
            logger.error(f"请求失败: {res.status_code}, {res.text}")
            return

        first_chunk = True
        for chunk in res.iter_content(chunk_size=6400):  # 16K * 20ms * 2
            if chunk:
                if first_chunk:
                    first_chunk = False
                    continue

                if self.state == State.RUNNING:
                    yield chunk

    def stream_tts(self, audio_stream):
        for chunk in audio_stream:
            if chunk is not None and len(chunk) > 0:
                stream = np.frombuffer(chunk, dtype=np.int16).astype(
                    np.float32) / 32767
                stream = resampy.resample(
                    x=stream, sr_orig=16000, sr_new=self.sample_rate)
                streamlen = stream.shape[0]
                idx = 0
                while streamlen >= self.chunk:
                    self.parent.put_audio_frame(
                        stream[idx:idx + self.chunk])
                    streamlen -= self.chunk
                    idx += self.chunk

class FlashTTS(BaseTTS):
    def __init__(self, opt, parent):
        super().__init__(opt, parent)
        self._warm_up_tts()

    def _warm_up_tts(self):
        """预热TTS模型"""
        test_text = "欢迎使用数字人系统"
        for _ in range(1):
            list(self.flash_tts(
                test_text,
                self.opt.REF_FILE,
                self.opt.TTS_SERVER
            ))

    def txt_to_audio(self, msg):
        text = msg
        self.stream_tts(
            self.flash_tts(
                text,
                self.opt.REF_FILE,
                self.opt.TTS_SERVER
            )
        )

    def flash_tts(self, text, reffile, server_url) -> Iterator[bytes]:
        print(f"text: {text}")
        text = (text,)
        start = time.perf_counter()

        # 读取参考音频文件并转换为base64
        try:
            with open(reffile, "rb") as f:
                audio_bytes = f.read()
            audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
        except Exception as e:
            logger.error(f"读取参考音频失败: {e}")
            return

        payload = {
            "text": text,
            "reference_text": None,
            "reference_audio": audio_base64,
            "temperature": 0.9,
            "top_p": 0.95,
            "top_k": 50,
            "max_tokens": 2048,
            "stream": True,
            "response_format": 'wav'
        }

        logger.info(f"FlashTTS payload text type: {type(text)}, text: {text}")
        logger.info(f"FlashTTS payload keys: {payload.keys()}")

        try:
            res = requests.post(
                f"{server_url}/clone_voice",
                data=payload,
                stream=True
            )
            logger.info(
                f"flash_tts status={res.status_code}, headers={res.headers}")
        except Exception as e:
            logger.error(f"FlashTTS请求失败: {e}")
            return

        end = time.perf_counter()
        logger.info(f"flash_tts Time to make POST: {end-start}s")

        if res.status_code != 200:
            logger.error(f"请求失败: {res.status_code}, {res.text}")
            return

        for chunk in res.iter_content(chunk_size=6400):  # 16K * 20ms * 2
            if chunk:
                if self.state == State.RUNNING:
                    yield chunk

    def stream_tts(self, audio_stream):
        for chunk in audio_stream:
            if chunk is not None and len(chunk) > 0:
                stream = np.frombuffer(chunk, dtype=np.int16).astype(
                    np.float32) / 32767
                stream = resampy.resample(
                    x=stream, sr_orig=16000, sr_new=self.sample_rate)
                streamlen = stream.shape[0]
                idx = 0
                while streamlen >= self.chunk:
                    self.parent.put_audio_frame(
                        stream[idx:idx + self.chunk])
                    streamlen -= self.chunk
                    idx += self.chunk
