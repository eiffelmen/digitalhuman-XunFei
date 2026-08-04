import asyncio
import os
import threading
import time
from typing import Tuple, Optional, Set, Union
from av.frame import Frame
from av.packet import Packet
import fractions
from loguru import logger
from aiortc import MediaStreamTrack
from perf_logger import elapsed_ms, log_perf, now


def _env_video_fps(default: float = 25.0) -> float:
    try:
        return max(1.0, float(os.environ.get("WEBRTC_VIDEO_FPS", default) or default))
    except (TypeError, ValueError):
        return default


AUDIO_PTIME = 0.020  # 20ms audio packetization
VIDEO_CLOCK_RATE = 90000  # 视频系统中的采样率
WEBRTC_VIDEO_FPS = _env_video_fps()
VIDEO_PTIME = 1 / WEBRTC_VIDEO_FPS
VIDEO_TIME_BASE = fractions.Fraction(1, VIDEO_CLOCK_RATE)
SAMPLE_RATE = 16000
AUDIO_TIME_BASE = fractions.Fraction(1, SAMPLE_RATE)


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return max(0.1, float(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


WEBRTC_AUDIO_QUEUE_MAX = _env_int("WEBRTC_AUDIO_QUEUE_MAX", 24)
WEBRTC_VIDEO_QUEUE_MAX = _env_int("WEBRTC_VIDEO_QUEUE_MAX", 16)
WEBRTC_VIDEO_HIGH_WATERMARK = _env_int("WEBRTC_VIDEO_HIGH_WATERMARK", 8)
WEBRTC_VIDEO_KEEP_FRAMES = _env_int("WEBRTC_VIDEO_KEEP_FRAMES", 7)
WEBRTC_DROP_LOG_INTERVAL = _env_float("WEBRTC_DROP_LOG_INTERVAL", 5.0)
WEBRTC_VIDEO_LAG_RESET_S = _env_float("WEBRTC_VIDEO_LAG_RESET_S", 0.20)
WEBRTC_VIDEO_TRIM_LEAD_S = _env_float("WEBRTC_VIDEO_TRIM_LEAD_S", 0.20)


class PlayerStreamTrack(MediaStreamTrack):
    """
    A video track that returns an animated flag.
    """

    def __init__(self, player, kind):
        super().__init__()
        self.kind = kind
        self._player = player
        maxsize = WEBRTC_VIDEO_QUEUE_MAX if kind == "video" else WEBRTC_AUDIO_QUEUE_MAX
        self._queue = asyncio.Queue(maxsize=maxsize)
        self._dropped_frames = 0
        self._total_dropped_frames = 0
        self._last_drop_log = 0.0
        self._last_recv_wall = None
        self._recv_count = 0
        self._max_queue_size_seen = 0
        self._empty_wait_count = 0
        self._slow_wait_count = 0
        self.timelist = []  # 记录最近包的时间戳
        self.current_frame_count = 0
        if self.kind == 'video':
            self.framecount = 0
            self.lasttime = time.perf_counter()
            self.totaltime = 0

    _start: float
    _timestamp: int

    def queue_size(self) -> int:
        return self._queue.qsize()

    def queue_maxsize(self) -> int:
        return self._queue.maxsize

    def submit_frame(self, loop: asyncio.AbstractEventLoop, frame: Frame) -> None:
        """Thread-safe, non-blocking frame submit with bounded latency."""
        if loop is None or loop.is_closed() or self.readyState != "live":
            return
        loop.call_soon_threadsafe(self._enqueue_frame_nowait, frame)

    def reset_for_speech_start(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(self._reset_queue_nowait, "speech_start")
        else:
            self._reset_queue_nowait("speech_start")

    def _reset_queue_nowait(self, reason: str = "") -> None:
        cleared = 0
        while True:
            try:
                self._queue.get_nowait()
                cleared += 1
            except asyncio.QueueEmpty:
                break
        if cleared:
            logger.info(
                f"WebRTC {self.kind} queue reset before speech start; "
                f"cleared={cleared} reason={reason}"
            )
            log_perf(
                "webrtc",
                "track_queue_reset",
                kind=self.kind,
                cleared=cleared,
                reason=reason,
                queue_max=self._queue.maxsize,
            )

    def _enqueue_frame_nowait(self, frame: Frame) -> None:
        if self.readyState != "live":
            return

        dropped = 0
        if self.kind == "video":
            video_q = self._queue.qsize()
            audio_track = getattr(self._player, "audio", None)
            audio_q = audio_track.queue_size() if audio_track is not None else 0
            video_lead_s = (video_q * VIDEO_PTIME) - (audio_q * AUDIO_PTIME)
            keep_frames = min(max(1, WEBRTC_VIDEO_KEEP_FRAMES), max(1, self._queue.maxsize - 1))
            if (
                video_q >= WEBRTC_VIDEO_HIGH_WATERMARK
                and video_q > keep_frames
                and video_lead_s > WEBRTC_VIDEO_TRIM_LEAD_S
            ):
                if self._drop_oldest_frame():
                    dropped += 1

        while self._queue.full():
            if self._drop_oldest_frame():
                dropped += 1
            else:
                break

        try:
            self._queue.put_nowait(frame)
        except asyncio.QueueFull:
            if self._drop_oldest_frame():
                dropped += 1
            try:
                self._queue.put_nowait(frame)
            except asyncio.QueueFull:
                dropped += 1

        self._max_queue_size_seen = max(self._max_queue_size_seen, self._queue.qsize())
        if dropped:
            self._log_dropped_frames(dropped)

    def _drop_oldest_frame(self) -> bool:
        try:
            self._queue.get_nowait()
            return True
        except asyncio.QueueEmpty:
            return False

    def _log_dropped_frames(self, dropped: int) -> None:
        self._dropped_frames += dropped
        self._total_dropped_frames += dropped
        now = time.monotonic()
        if now - self._last_drop_log < WEBRTC_DROP_LOG_INTERVAL:
            return
        logger.warning(
            f"WebRTC {self.kind} queue dropped {self._dropped_frames} stale frames; "
            f"qsize={self._queue.qsize()}/{self._queue.maxsize}"
        )
        log_perf(
            "webrtc",
            "track_queue_drop",
            kind=self.kind,
            dropped_since_last_log=self._dropped_frames,
            total_dropped_frames=self._total_dropped_frames,
            queue_size=self._queue.qsize(),
            queue_max=self._queue.maxsize,
        )
        self._dropped_frames = 0
        self._last_drop_log = now

    async def next_timestamp(self) -> Tuple[int, fractions.Fraction]:
        if self.readyState != "live":
            raise Exception

        if self.kind == 'video':
            if hasattr(self, "_timestamp"):
                self._timestamp += int(VIDEO_PTIME * VIDEO_CLOCK_RATE)
                self.current_frame_count += 1
                wait = self._start + (self._timestamp /
                                      VIDEO_CLOCK_RATE) - time.time()
                # wait = self._start + self.current_frame_count * VIDEO_PTIME - time.time()
                if wait > 0:
                    await asyncio.sleep(wait)
                elif wait < -WEBRTC_VIDEO_LAG_RESET_S:
                    # 遇到上游推理、网络或浏览器短时 stall 时，不做长时间追帧突发发送。
                    # 保持 PTS 单调，同时把发送节奏重新锚定到当前时间，降低长时间运行后的 jitter。
                    self._start = time.time() - (self._timestamp / VIDEO_CLOCK_RATE)
            else:
                self._start = time.time()
                self._timestamp = 0
                self.timelist.append(self._start)
                logger.info('video start:', self._start)
            return self._timestamp, VIDEO_TIME_BASE
        else:  # audio
            if hasattr(self, "_timestamp"):
                self._timestamp += int(AUDIO_PTIME * SAMPLE_RATE)
                self.current_frame_count += 1
                wait = self._start + (self._timestamp /
                      SAMPLE_RATE) - time.time()
                if wait > 0:
                    await asyncio.sleep(wait)
                elif wait < -0.04:
                    # 落后超过 2 个 ptime（40ms）说明上游有一次明显的 stall。
                    # 不要继续无 sleep 突发追发——那会让前端在静默后看到一串
                    # 零间隔的包，jitter buffer 吸收不了就听感"卡一下"。
                    # 直接重置时间基准，保持 PTS 单调，从此刻起重新匀速 20ms。
                    self._start = time.time() - (self._timestamp / SAMPLE_RATE)
            else:
                self._start = time.time()
                self._timestamp = 0
                self.timelist.append(self._start)
                logger.info('audio start:', self._start)
            return self._timestamp, AUDIO_TIME_BASE

    async def recv(self) -> Union[Frame, Packet]:
        self._player._start(self)
        wait_start = now()
        queue_before = self._queue.qsize()
        frame = await self._queue.get()
        wait_ms = elapsed_ms(wait_start)
        if queue_before == 0:
            self._empty_wait_count += 1
        if wait_ms > (40 if self.kind == "video" else 30):
            self._slow_wait_count += 1
            if self._slow_wait_count <= 5 or self._slow_wait_count % 50 == 0:
                logger.warning(
                    f"[SYNC_DIAG] WebRTC {self.kind} recv waited {wait_ms:.2f}ms "
                    f"queue_before={queue_before} queue_after={self._queue.qsize()} "
                    f"empty_waits={self._empty_wait_count} slow_waits={self._slow_wait_count}"
                )
                log_perf(
                    "webrtc",
                    "track_recv_wait_slow",
                    wait_ms,
                    kind=self.kind,
                    queue_before=queue_before,
                    queue_after=self._queue.qsize(),
                    empty_waits=self._empty_wait_count,
                    slow_waits=self._slow_wait_count,
                    recv_count=self._recv_count,
                )
        if frame is None:
            self.stop()
            raise Exception
        pts, time_base = await self.next_timestamp()
        frame.pts = pts
        frame.time_base = time_base
        if self.kind == 'video':
            self.totaltime += (time.perf_counter() - self.lasttime)
            self.framecount += 1
            self.lasttime = time.perf_counter()
            if self.framecount == 100:
                logger.info(
                    f"------actual avg final fps:{self.framecount/self.totaltime:.4f}"
                )
                self.framecount = 0
                self.totaltime = 0
        self._recv_count += 1
        if self._recv_count <= 5 or self._recv_count % 500 == 0:
            log_perf(
                "webrtc",
                "track_recv",
                wait_ms,
                kind=self.kind,
                recv_count=self._recv_count,
                queue_before=queue_before,
                queue_after=self._queue.qsize(),
                empty_waits=self._empty_wait_count,
                slow_waits=self._slow_wait_count,
                total_dropped_frames=self._total_dropped_frames,
            )
        self._last_recv_wall = time.time()
        return frame

    def diagnostics(self):
        last_recv_age_s = None
        if self._last_recv_wall is not None:
            last_recv_age_s = round(time.time() - self._last_recv_wall, 3)
        return {
            "kind": self.kind,
            "ready_state": self.readyState,
            "queue_size": self._queue.qsize(),
            "queue_max": self._queue.maxsize,
            "max_queue_size_seen": self._max_queue_size_seen,
            "recv_count": self._recv_count,
            "current_frame_count": self.current_frame_count,
            "total_dropped_frames": self._total_dropped_frames,
            "pending_dropped_frames": self._dropped_frames,
            "empty_wait_count": self._empty_wait_count,
            "slow_wait_count": self._slow_wait_count,
            "last_recv_age_s": last_recv_age_s,
        }

    def stop(self):
        super().stop()
        if self._player is not None:
            self._player._stop(self)
            self._player = None


def player_worker_thread(quit_event, loop, container, audio_track,
                         video_track):
    container.render(quit_event, loop, audio_track, video_track)


class HumanPlayer:

    def __init__(self,
                 nerfreal,
                 format=None,
                 options=None,
                 timeout=None,
                 loop=False,
                 decode=True):
        self.__thread: Optional[threading.Thread] = None
        self.__thread_quit: Optional[threading.Event] = None

        # examine streams
        self.__started: Set[PlayerStreamTrack] = set()
        self.__audio: Optional[PlayerStreamTrack] = None
        self.__video: Optional[PlayerStreamTrack] = None

        self.__audio = PlayerStreamTrack(self, kind="audio")
        self.__video = PlayerStreamTrack(self, kind="video")

        self.__container = nerfreal

    @property
    def audio(self) -> MediaStreamTrack:
        """
        A :class:`aiortc.MediaStreamTrack` instance if the file contains audio.
        """
        return self.__audio

    @property
    def video(self) -> MediaStreamTrack:
        """
        A :class:`aiortc.MediaStreamTrack` instance if the file contains video.
        """
        return self.__video

    def diagnostics(self):
        return {
            "thread_alive": bool(self.__thread and self.__thread.is_alive()),
            "started_tracks": [track.kind for track in self.__started],
            "audio": self.__audio.diagnostics() if self.__audio else None,
            "video": self.__video.diagnostics() if self.__video else None,
        }

    def _start(self, track: PlayerStreamTrack) -> None:
        self.__started.add(track)
        if self.__thread is None:
            self.__log_debug("Starting worker thread")
            self.__thread_quit = threading.Event()
            self.__thread = threading.Thread(
                name="media-player",
                target=player_worker_thread,
                args=(self.__thread_quit, asyncio.get_event_loop(),
                      self.__container, self.__audio, self.__video),
                daemon=True,
            )
            self.__thread.start()

    def _stop(self, track: PlayerStreamTrack) -> None:
        self.__started.discard(track)

        if not self.__started and self.__thread is not None:
            self.__log_debug("Stopping worker thread")
            self.__thread_quit.set()
            self.__thread.join(timeout=5)
            if self.__thread.is_alive():
                logger.warning("HumanPlayer worker thread stop timeout")
            self.__thread = None

        if not self.__started and self.__container is not None:
            self.__container = None

    def __log_debug(self, msg: str, *args) -> None:
        logger.debug(f"HumanPlayer {msg}", *args)
