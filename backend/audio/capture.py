from __future__ import annotations

import asyncio
import logging
import subprocess
import threading
import time
from typing import Optional

from backend.audio.vad import VoiceActivityDetector
from backend.config import settings
from backend.core.events import AudioChunkEvent
from backend.core.exceptions import AudioCaptureError

logger = logging.getLogger(__name__)


class AudioCapture:
    def __init__(self, device_index: int, sample_rate: int = 16000, chunk_seconds: int = 5):
        self.device_index = device_index
        self.sample_rate = sample_rate
        self.chunk_seconds = chunk_seconds

        self.queue: asyncio.Queue[AudioChunkEvent] = asyncio.Queue()
        self._process: Optional[subprocess.Popen] = None
        self._reader_thread_handle: Optional[threading.Thread] = None
        self._stderr_thread_handle: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._running = False
        self._chunk_index: int = 0
        self._buffer = bytearray()
        self._chunk_size_bytes = int(self.chunk_seconds * self.sample_rate * 2)
        self._vad = VoiceActivityDetector(
            aggressiveness=settings.audio_vad_aggressiveness,
            sample_rate=self.sample_rate,
        )

    async def start(self) -> None:
        """Launch FFmpeg subprocess and start background reader thread."""
        if self._running:
            return

        self._loop = asyncio.get_running_loop()
        self._process = subprocess.Popen(
            self._build_ffmpeg_cmd(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )

        if self._process.stdout is None:
            raise AudioCaptureError("Failed to open FFmpeg stdout pipe")

        self._running = True
        self._reader_thread_handle = threading.Thread(target=self._reader_thread, daemon=True)
        self._reader_thread_handle.start()

        if self._process.stderr is not None:
            self._stderr_thread_handle = threading.Thread(target=self._stderr_thread, daemon=True)
            self._stderr_thread_handle.start()

    async def stop(self) -> None:
        """Terminate FFmpeg process and stop reader threads."""
        self._running = False

        if self._process is not None:
            try:
                self._process.terminate()
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
            finally:
                self._process = None

        if self._reader_thread_handle is not None and self._reader_thread_handle.is_alive():
            self._reader_thread_handle.join(timeout=1.0)

        if self._stderr_thread_handle is not None and self._stderr_thread_handle.is_alive():
            self._stderr_thread_handle.join(timeout=1.0)

    def _build_ffmpeg_cmd(self) -> list[str]:
        import sys
        
        if sys.platform == "darwin":
            fmt = "avfoundation"
            input_device = f":{self.device_index}"
        elif sys.platform == "win32":
            fmt = "dshow"
            input_device = f"audio={self.device_index}" # Note: Windows users often need string names, but index works in some builds. We use the config value.
            # Usually dshow expects "audio=Stereo Mix (Realtek(R) Audio)", but we'll try to pass the env string directly
            input_device = f"audio={settings.audio_device_index}" if isinstance(settings.audio_device_index, str) else f"audio={self.device_index}"
        else:
            fmt = "pulse" # Default to pulse on linux
            input_device = "default" if str(self.device_index) == "0" else str(self.device_index)

        return [
            "ffmpeg",
            "-f",
            fmt,
            "-i",
            input_device,
            "-ac",
            "1",
            "-ar",
            str(self.sample_rate),
            "-acodec",
            "pcm_s16le",
            "-f",
            "s16le",
            "-bufsize",
            "65536",
            "pipe:1",
        ]

    def _stderr_thread(self) -> None:
        assert self._process is not None
        assert self._process.stderr is not None

        while self._running:
            line = self._process.stderr.readline()
            if not line:
                break
            logger.debug("ffmpeg: %s", line.decode(errors="replace").strip())

    def _enqueue_event(self, event: AudioChunkEvent) -> None:
        if self._loop is None or not self._loop.is_running():
            return
        future = asyncio.run_coroutine_threadsafe(self.queue.put(event), self._loop)
        future.result(timeout=2)

    def _reader_thread(self) -> None:
        assert self._process is not None
        assert self._process.stdout is not None

        try:
            while self._running:
                data = self._process.stdout.read(4096)
                if not data:
                    if self._process.poll() is not None:
                        logger.error("FFmpeg process exited unexpectedly with code %s", self._process.poll())
                        break
                    time.sleep(0.01)
                    continue

                self._buffer.extend(data)

                while len(self._buffer) >= self._chunk_size_bytes:
                    chunk = bytes(self._buffer[: self._chunk_size_bytes])
                    del self._buffer[: self._chunk_size_bytes]

                    if not self._vad.filter_silent_chunks(chunk):
                        continue

                    event = AudioChunkEvent(
                        data=chunk,
                        timestamp=time.time(),
                        chunk_index=self._chunk_index,
                    )
                    self._chunk_index += 1
                    self._enqueue_event(event)
        except Exception as exc:  # pragma: no cover - hard to unit test thread failures
            logger.exception("Audio reader thread failed: %s", exc)
