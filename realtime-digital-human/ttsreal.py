import os
import time
import queue
import hashlib
import json
import resampy
import requests
import asyncio
import base64
import websocket
import edge_tts

import numpy as np
import soundfile as sf
from enum import Enum
from io import BytesIO
from loguru import logger
from typing import Iterator
from threading import Thread, Event, Lock
from perf_logger import elapsed_ms, log_perf, now


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return max(0, min(100, int(value)))
    except ValueError:
        logger.warning(f"Invalid {name}={value!r}; using {default}")
        return default


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

class IflytekTTS(BaseTTS):
    _WS_BASE = "ws://wsapi.xfyun.cn/v1/aiui"

    def __init__(self, opt, parent):
        super().__init__(opt, parent)
        self._app_id = os.environ["IFLY_APP_ID"]
        self._api_key = os.environ["IFLY_API_KEY"]
        self._api_secret = os.environ.get("IFLYTEK_API_SECRET", os.environ.get("IFLY_API_SECRET", ""))
        self._vcn = os.environ.get(
            "IFLYTEK_VCN",
            os.environ.get("IFLY_VCN", getattr(opt, "ifly_vcn", "x2_xiaojuan")),
        )
        self._fallback_vcn = os.environ.get("IFLYTEK_TTS_FALLBACK_VCN", "xiaoyan")
        self._engine = os.environ.get("IFLYTEK_TTS_ENGINE", "aiui").lower()
        self._super_ws_url = os.environ.get(
            "IFLYTEK_SUPER_TTS_URL",
            "wss://cbm01.cn-huabei-1.xf-yun.com/v1/private/mcd9m97e6",
        )
        self._speed = _env_int("IFLYTEK_TTS_SPEED", 45)
        self._volume = _env_int("IFLYTEK_TTS_VOLUME", 55)
        self._pitch = _env_int("IFLYTEK_TTS_PITCH", 48)
        self._session_ready = None
        self._session_ws = None
        self._session_audio = None
        logger.info(
            f"IflytekTTS config: engine={self._engine}, vcn={self._vcn}, "
            f"fallback_vcn={self._fallback_vcn}, speed={self._speed}, "
            f"volume={self._volume}, pitch={self._pitch}"
        )

    @staticmethod
    def _get_auth_id() -> str:
        import uuid
        mac = uuid.UUID(int=uuid.getnode()).hex[-12:]
        return hashlib.md5(
            ":".join([mac[e:e + 2] for e in range(0, 11, 2)]).encode("utf-8")
        ).hexdigest()

    def _build_ws_url(self) -> str:
        from urllib.parse import urlencode
        curtime = str(int(time.time()))
        param = json.dumps({
            "auth_id": self._get_auth_id(),
            "data_type": "text",
            "vcn": self._vcn,
            "speed": str(self._speed),
            "volume": str(self._volume),
            "pitch": str(self._pitch),
            "scene": "IFLYTEK.tts",
            "tts_res_type": "url",
            "context": "{\"sdk_support\":[\"tts\"]}",
        }, ensure_ascii=False)
        param_b64 = base64.b64encode(param.encode("utf-8")).decode()
        checksum = hashlib.md5(
            (self._api_key + curtime + param_b64).encode("utf-8")
        ).hexdigest()
        qs = urlencode({
            "appid": self._app_id,
            "checksum": checksum,
            "param": param_b64,
            "curtime": curtime,
            "signtype": "md5",
        })
        return f"{self._WS_BASE}?{qs}"

    def _build_super_ws_url(self) -> str:
        import hmac
        from datetime import datetime
        from time import mktime
        from urllib.parse import urlencode, urlparse
        from wsgiref.handlers import format_date_time

        parsed = urlparse(self._super_ws_url)
        host = parsed.netloc
        path = parsed.path
        date = format_date_time(mktime(datetime.now().timetuple()))
        signature_origin = f"host: {host}\ndate: {date}\nGET {path} HTTP/1.1"
        signature = hmac.new(
            self._api_secret.encode("utf-8"),
            signature_origin.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        authorization_origin = (
            f'api_key="{self._api_key}", algorithm="hmac-sha256", '
            f'headers="host date request-line", signature="{base64.b64encode(signature).decode("utf-8")}"'
        )
        query = urlencode({
            "authorization": base64.b64encode(authorization_origin.encode("utf-8")).decode("utf-8"),
            "date": date,
            "host": host,
        })
        return f"{self._super_ws_url}?{query}"

    def _build_super_request(self, text: str) -> str:
        payload = {
            "header": {
                "app_id": self._app_id,
                "status": 2,
            },
            "parameter": {
                "tts": {
                    "vcn": self._vcn,
                    "speed": self._speed,
                    "volume": self._volume,
                    "pitch": self._pitch,
                    "bgs": 0,
                    "reg": 0,
                    "rdn": 0,
                    "rhy": 0,
                    "audio": {
                        "encoding": "lame",
                        "sample_rate": 24000,
                        "channels": 1,
                        "bit_depth": 16,
                        "frame_size": 0,
                    },
                },
            },
            "payload": {
                "text": {
                    "encoding": "utf8",
                    "compress": "raw",
                    "format": "plain",
                    "status": 2,
                    "seq": 0,
                    "text": base64.b64encode(text.encode("utf-8")).decode("utf-8"),
                },
            },
        }
        return json.dumps(payload, ensure_ascii=False)

    def _super_tts(self, text: str) -> Iterator[bytes]:
        if not self._api_secret:
            logger.warning("Iflytek super TTS disabled: missing IFLYTEK_API_SECRET")
            return

        ws = None
        try:
            ws = websocket.create_connection(self._build_super_ws_url(), timeout=20)
            ws.send(self._build_super_request(text))
            logger.info(f"Iflytek super TTS started, vcn={self._vcn}")

            while True:
                raw = ws.recv()
                if not raw:
                    continue
                data = json.loads(raw)
                header = data.get("header", {})
                code = header.get("code", 0)
                if code != 0:
                    logger.error(f"Iflytek super TTS error: {raw}")
                    break

                audio = data.get("payload", {}).get("audio", {})
                audio_b64 = audio.get("audio")
                if audio_b64 and self.state == State.RUNNING:
                    yield base64.b64decode(audio_b64)

                if header.get("status") == 2 or audio.get("status") == 2:
                    break
        except Exception as e:
            logger.error(f"Iflytek super TTS exception: {e}")
        finally:
            try:
                if ws is not None:
                    ws.close()
            except Exception:
                pass

    def open_session(self):
        self._session_audio = queue.Queue()
        self._session_ready = Event()
        self._session_ws = None

        def on_message(ws, message):
            data = json.loads(message)
            action = data.get("action")
            if action == "started":
                self._session_ws = ws
                self._session_ready.set()
            elif action == "result":
                sub = data.get("data", {}).get("sub")
                if sub == "tts":
                    url = base64.b64decode(data["data"]["content"]).decode("utf-8")
                    try:
                        resp = requests.get(url, timeout=10)
                        if resp.ok:
                            audio_content = resp.content
                            if audio_content:
                                logger.info(f"IflytekTTS: audio download OK, {len(audio_content)} bytes")
                                self._session_audio.put(audio_content)
                            else:
                                logger.error(f"IflytekTTS: audio download returned empty content")
                                self._session_audio.put(None)
                        else:
                            logger.error(f"IflytekTTS: audio download failed: {resp.status_code}")
                            self._session_audio.put(None)
                    except Exception as e:
                        logger.error(f"IflytekTTS: audio download error: {e}")
                        self._session_audio.put(None)

        def on_close(ws, close_status_code, close_msg):
            logger.warning(f"IflytekTTS: pre-connect closed: code={close_status_code}, msg={close_msg}")
            self._session_ready.set()
            self._session_audio.put(None)

        def on_error(_, error):
            logger.warning(f"IflytekTTS: pre-connect error: {error}")
            self._session_ready.set()

        ws_app = websocket.WebSocketApp(
            self._build_ws_url(),
            on_message=on_message,
            on_close=on_close,
            on_error=on_error,
            header=["Origin: https://wsapi.xfyun.cn"],
        )
        Thread(target=ws_app.run_forever, daemon=True).start()
        logger.info("IflytekTTS: pre-connecting...")

    def _txt_to_audio_session(self, msg):
        ready = self._session_ready
        self._session_ready = None
        if not ready.wait(timeout=5):
            logger.warning("IflytekTTS: pre-connect timeout, fallback")
            self.stream_tts(self._ifly_tts(msg))
            return
        ws = self._session_ws
        if ws is None:
            logger.warning("IflytekTTS: pre-connect failed, fallback")
            self.stream_tts(self._ifly_tts(msg))
            return
        logger.info("IflytekTTS: reusing pre-connected session")
        ws.send(msg.encode("utf-8"))
        ws.send("--end--".encode("utf-8"))
        self.stream_tts(self._iter_session_audio())

    def _iter_session_audio(self):
        while True:
            try:
                chunk = self._session_audio.get(timeout=15)
            except queue.Empty:
                logger.warning("IflytekTTS: session audio timeout")
                break
            if chunk is None:
                break
            if self.state == State.RUNNING:
                yield chunk

    def _ifly_tts(self, text: str, vcn: str | None = None) -> Iterator[bytes]:
        if self._engine == "super":
            received_audio = False
            for chunk in self._super_tts(text):
                received_audio = True
                yield chunk
            if received_audio:
                return
            logger.warning("Iflytek super TTS returned no audio, falling back to AIUI TTS")

        result_queue: queue.Queue = queue.Queue()
        started_event = Event()
        ws_holder: list = [None]
        original_vcn = self._vcn
        if vcn:
            self._vcn = vcn

        def on_message(ws, message):
            try:
                data = json.loads(message)
            except Exception:
                logger.warning(f"IflytekTTS: non-JSON message: {message[:100]}")
                return
            if not isinstance(data, dict):
                logger.warning(f"IflytekTTS: unexpected message format: {str(data)[:100]}")
                return
            action = data.get("action")
            logger.info(f"IflytekTTS msg: action={action}")
            if action == "started":
                ws_holder[0] = ws
                started_event.set()
            elif action == "result":
                sub = data.get("data", {}).get("sub") if isinstance(data.get("data"), dict) else None
                if sub == "tts":
                    url = base64.b64decode(data["data"]["content"]).decode("utf-8")
                    logger.info(f"IflytekTTS: downloading audio from {url}")
                    try:
                        resp = requests.get(url, timeout=10)
                        if resp.ok:
                            audio_content = resp.content
                            if audio_content:
                                logger.info(f"IflytekTTS: audio download OK, {len(audio_content)} bytes")
                                result_queue.put(audio_content)
                            else:
                                logger.error(f"IflytekTTS: audio download returned empty content")
                                result_queue.put(None)
                        else:
                            logger.error(f"IflytekTTS: audio download failed: {resp.status_code}")
                            result_queue.put(None)
                    except Exception as e:
                        logger.error(f"IflytekTTS: audio download error: {e}")
                        result_queue.put(None)
            else:
                logger.warning(f"IflytekTTS: unhandled action={action}, msg={str(data)[:200]}")

        def on_close(ws, close_status_code, close_msg):
            logger.warning(f"IflytekTTS WS closed: code={close_status_code}, msg={close_msg}")
            started_event.set()
            result_queue.put(None)

        def on_error(_, error):
            logger.error(f"IflytekTTS WS error: {error}")
            started_event.set()

        ws_app = websocket.WebSocketApp(
            self._build_ws_url(),
            on_message=on_message,
            on_close=on_close,
            on_error=on_error,
            header=["Origin: https://wsapi.xfyun.cn"],
        )
        Thread(target=ws_app.run_forever, daemon=True).start()

        try:
            if not started_event.wait(timeout=10):
                logger.warning("IflytekTTS: timeout waiting for 'started'")
                return
            if ws_holder[0] is None:
                logger.warning("IflytekTTS: connection failed before 'started'")
                return
            ws_holder[0].send(text.encode("utf-8"))
            ws_holder[0].send("--end--".encode("utf-8"))

            while True:
                try:
                    chunk = result_queue.get(timeout=15)
                except queue.Empty:
                    logger.warning("IflytekTTS: timeout waiting for audio")
                    break
                if chunk is None:
                    break
                if self.state == State.RUNNING:
                    yield chunk
        finally:
            self._vcn = original_vcn

    def txt_to_audio(self, msg: str) -> None:
        if self._session_ready is not None:
            self._txt_to_audio_session(msg)
        else:
            self.stream_tts(self._ifly_tts_with_fallback(msg))

    def _ifly_tts_with_fallback(self, msg: str) -> Iterator[bytes]:
        received_audio = False
        for chunk in self._ifly_tts(msg):
            received_audio = True
            yield chunk
        if received_audio or self._engine == "super" or self._fallback_vcn == self._vcn:
            return

        logger.warning(
            f"IflytekTTS: no audio with vcn={self._vcn}, retrying fallback_vcn={self._fallback_vcn}"
        )
        for chunk in self._ifly_tts(msg, self._fallback_vcn):
            yield chunk

    def stream_tts(self, audio_stream: Iterator[bytes]) -> None:
        for chunk in audio_stream:
            if not chunk:
                continue
            logger.info(f"IflytekTTS stream_tts: chunk {len(chunk)} bytes")
            t0 = time.time()
            try:
                stream, sample_rate = sf.read(BytesIO(chunk))
                logger.info(f"IflytekTTS stream_tts: sf.read done, sr={sample_rate}, samples={stream.shape[0]}, took {time.time()-t0:.3f}s")
                stream = stream.astype(np.float32)
                if stream.ndim > 1:
                    stream = stream[:, 0]
                if sample_rate != self.sample_rate and stream.shape[0] > 0:
                    t1 = time.time()
                    stream = resampy.resample(x=stream, sr_orig=sample_rate, sr_new=self.sample_rate)
                    logger.info(f"IflytekTTS stream_tts: resample done, samples={stream.shape[0]}, took {time.time()-t1:.3f}s")
            except Exception as e:
                logger.warning(f"IflytekTTS stream_tts: sf.read/resample failed ({e}), fallback to raw PCM")
                stream = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32767.0
            frames_pushed = 0
            idx = 0
            while idx + self.chunk <= len(stream):
                self.parent.put_audio_frame(stream[idx:idx + self.chunk])
                idx += self.chunk
                frames_pushed += 1
            logger.info(f"IflytekTTS stream_tts: pushed {frames_pushed} frames, total took {time.time()-t0:.3f}s")


class GonganTTSStream:
    def __init__(self, owner):
        self._owner = owner
        self._ws = owner._connect_ws()
        self._audio_state = owner._new_audio_state()
        self._lock = Lock()
        self._done = Event()
        self._closed = False
        self._end_sent = False
        self._segments_sent = 0
        self._segments_done = 0

        self._ws.send(json.dumps({"signal": "start"}, ensure_ascii=False))
        self._owner._mark_tts_stream_start()
        self._thread = Thread(target=self._recv_loop, daemon=True)
        self._thread.start()

    def send_text(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        with self._lock:
            if self._closed:
                return
            self._segments_sent += 1
            self._owner._mark_tts_first_text(text)
            self._ws.send(
                json.dumps(
                    {"text": text, "spk_id": self._owner._spk_id},
                    ensure_ascii=False,
                )
            )

    def finish(self, wait: bool = True) -> None:
        with self._lock:
            if not self._end_sent and not self._closed:
                try:
                    self._ws.send(json.dumps({"signal": "end"}, ensure_ascii=False))
                except Exception as exc:
                    logger.warning(f"GonganTTS stream end send failed: {exc}")
                self._end_sent = True
            has_segments = self._segments_sent > 0
            if has_segments and self._segments_done >= self._segments_sent:
                self._done.set()

        if wait and has_segments:
            self._done.wait(timeout=self._owner._finish_timeout)
        self.close()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            try:
                self._ws.close()
            except Exception:
                pass
        self._owner._clear_active_stream(self)

    def abort(self) -> None:
        self._done.set()
        self.close()

    def _recv_loop(self) -> None:
        try:
            while True:
                raw = self._ws.recv()
                if not raw:
                    break
                try:
                    data = json.loads(raw)
                except Exception:
                    logger.debug(f"GonganTTS stream non-JSON message: {raw!r}")
                    continue

                status = data.get("status")
                if status in (1, "1") and data.get("audio"):
                    self._owner._mark_tts_first_audio_packet(data["audio"])
                    self._owner._push_raw_pcm(
                        base64.b64decode(data["audio"]),
                        self._audio_state,
                    )
                elif status in (2, "2"):
                    self._segments_done += 1
                    if self._end_sent and self._segments_done >= self._segments_sent:
                        self._done.set()
                        break
                elif data.get("success") is False or data.get("code"):
                    logger.warning(f"GonganTTS stream warning: {str(data)[:200]}")
        except Exception as exc:
            if not self._closed:
                logger.warning(f"GonganTTS stream recv error: {exc}")
        finally:
            self._owner._flush_audio_state(self._audio_state)
            self._done.set()
            self.close()


class GonganTTS(BaseTTS):
    def __init__(self, opt, parent):
        super().__init__(opt, parent)
        from gongan_api import env_float, get_gongan_client

        self._client = get_gongan_client()
        self._spk_id = int(os.environ.get("GONGAN_TTS_SPK_ID", "0"))
        self._source_sample_rate = int(os.environ.get("GONGAN_TTS_SAMPLE_RATE", "24000"))
        self._finish_timeout = env_float("GONGAN_TTS_FINISH_TIMEOUT", 20.0)
        self._ws_timeout = env_float("GONGAN_TTS_WS_TIMEOUT", 60.0)
        self._active_stream = None
        self._active_lock = Lock()
        self._tts_ts_lock = Lock()
        self._reset_tts_timestamps()
        logger.info(
            f"GonganTTS config: spk_id={self._spk_id}, "
            f"sample_rate={self._source_sample_rate}"
        )

    def flush_talk(self):
        super().flush_talk()
        with self._active_lock:
            stream = self._active_stream
        if stream is not None:
            stream.abort()

    def start_text_stream(self):
        self.state = State.RUNNING
        with self._active_lock:
            old_stream = self._active_stream
            self._active_stream = None
        if old_stream is not None:
            old_stream.abort()
        self._reset_tts_timestamps()
        stream = GonganTTSStream(self)
        with self._active_lock:
            self._active_stream = stream
        return stream

    def _clear_active_stream(self, stream) -> None:
        with self._active_lock:
            if self._active_stream is stream:
                self._active_stream = None

    def _connect_ws(self):
        self._client.ensure_login()
        return websocket.create_connection(
            self._client.tokenized_url(self._client.tts_ws_url),
            header=self._client.websocket_header_list(),
            cookie=self._client.cookie_header(),
            origin=self._client.origin,
            timeout=self._ws_timeout,
        )

    def _new_audio_state(self):
        return {
            "bytes": b"",
            "samples": np.zeros(0, dtype=np.float32),
        }

    def _push_raw_pcm(self, raw: bytes, state) -> None:
        if not raw or self.state != State.RUNNING:
            return

        raw = state["bytes"] + raw
        even_len = len(raw) - (len(raw) % 2)
        if even_len <= 0:
            state["bytes"] = raw
            return

        state["bytes"] = raw[even_len:]
        samples = np.frombuffer(raw[:even_len], dtype=np.int16).astype(np.float32) / 32767.0
        if self._source_sample_rate != self.sample_rate and samples.shape[0] > 0:
            samples = resampy.resample(
                x=samples,
                sr_orig=self._source_sample_rate,
                sr_new=self.sample_rate,
            ).astype(np.float32)

        if state["samples"].shape[0] > 0:
            samples = np.concatenate([state["samples"], samples])

        idx = 0
        frames = 0
        while idx + self.chunk <= samples.shape[0] and self.state == State.RUNNING:
            self._mark_tts_first_audio_frame()
            self.parent.put_audio_frame(samples[idx: idx + self.chunk])
            idx += self.chunk
            frames += 1
        state["samples"] = samples[idx:]
        if frames:
            logger.debug(f"GonganTTS pushed {frames} audio frames")

    def _flush_audio_state(self, state) -> None:
        remain = state["samples"]
        if remain.shape[0] > 0 and self.state == State.RUNNING:
            frame = np.zeros(self.chunk, dtype=np.float32)
            frame[: min(remain.shape[0], self.chunk)] = remain[: self.chunk]
            self._mark_tts_first_audio_frame()
            self.parent.put_audio_frame(frame)
        state["bytes"] = b""
        state["samples"] = np.zeros(0, dtype=np.float32)

    def _iter_tts_once(self, text: str):
        ws = None
        try:
            ws = self._connect_ws()
            ws.send(json.dumps({"signal": "start"}, ensure_ascii=False))
            self._mark_tts_stream_start()
            self._mark_tts_first_text(text)
            ws.send(
                json.dumps(
                    {"text": text, "spk_id": self._spk_id},
                    ensure_ascii=False,
                )
            )
            ws.send(json.dumps({"signal": "end"}, ensure_ascii=False))
            logger.info(f"GonganTTS one-shot started, len={len(text)}")

            while True:
                raw = ws.recv()
                if not raw:
                    break
                data = json.loads(raw)
                status = data.get("status")
                if status in (1, "1") and data.get("audio"):
                    self._mark_tts_first_audio_packet(data["audio"])
                    yield base64.b64decode(data["audio"])
                elif status in (2, "2"):
                    break
                elif data.get("success") is False or data.get("code"):
                    logger.warning(f"GonganTTS warning: {str(data)[:200]}")
        except Exception as exc:
            logger.error(f"GonganTTS error: {exc}")
        finally:
            try:
                if ws is not None:
                    ws.close()
            except Exception:
                pass

    def txt_to_audio(self, msg: str) -> None:
        if not msg.strip():
            return
        self.state = State.RUNNING
        self._reset_tts_timestamps()
        start = time.perf_counter()
        state = self._new_audio_state()
        for chunk in self._iter_tts_once(msg):
            self._push_raw_pcm(chunk, state)
        self._flush_audio_state(state)
        logger.info(f"GonganTTS total time: {time.perf_counter() - start:.3f}s")

    def _reset_tts_timestamps(self) -> None:
        with self._tts_ts_lock:
            self._tts_first_text_logged = False
            self._tts_first_audio_packet_logged = False
            self._tts_first_audio_frame_logged = False
            self._tts_first_text_mono = None

    def _mark_tts_stream_start(self) -> None:
        wall = time.time()
        mono = time.perf_counter()
        logger.info(f"[TS] tts.stream_start wall={wall:.6f} mono={mono:.6f}")

    def _mark_tts_first_text(self, text: str) -> None:
        with self._tts_ts_lock:
            if self._tts_first_text_logged:
                return
            self._tts_first_text_logged = True
            wall = time.time()
            mono = time.perf_counter()
            self._tts_first_text_mono = mono
        logger.info(
            f"[TS] tts.first_text_segment len={len(text)} "
            f"wall={wall:.6f} mono={mono:.6f}"
        )

    def _mark_tts_first_audio_packet(self, audio_payload: str) -> None:
        with self._tts_ts_lock:
            if self._tts_first_audio_packet_logged:
                return
            self._tts_first_audio_packet_logged = True
            wall = time.time()
            mono = time.perf_counter()
            first_text_mono = self._tts_first_text_mono
        latency = mono - first_text_mono if first_text_mono is not None else -1.0
        logger.info(
            f"[TS] tts.first_audio_packet payload_chars={len(audio_payload)} "
            f"latency_from_text={latency:.6f}s wall={wall:.6f} mono={mono:.6f}"
        )

    def _mark_tts_first_audio_frame(self) -> None:
        with self._tts_ts_lock:
            if self._tts_first_audio_frame_logged:
                return
            self._tts_first_audio_frame_logged = True
            wall = time.time()
            mono = time.perf_counter()
            first_text_mono = self._tts_first_text_mono
        latency = mono - first_text_mono if first_text_mono is not None else -1.0
        logger.info(
            f"[TS] tts.first_audio_frame_pushed "
            f"latency_from_text={latency:.6f}s wall={wall:.6f} mono={mono:.6f}"
        )


class GywtTTS(GonganTTS):
    """Compatibility alias for server basereal.py versions that import GywtTTS."""


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
