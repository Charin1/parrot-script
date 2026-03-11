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
import wave
from pathlib import Path

logger = logging.getLogger(__name__)


class AudioCapture:
    def __init__(self, device_index: int, sample_rate: int = 16000, chunk_seconds: int = 5, record_to_file: Optional[Path] = None):
        self.device_index = device_index
        self.sample_rate = sample_rate
        self.chunk_seconds = chunk_seconds
        self.record_to_file = record_to_file

        self.queue: asyncio.Queue[AudioChunkEvent] = asyncio.Queue()
        self._wav_file: Optional[wave.Wave_write] = None
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
        self._start_offset_s: float = 0.0

    async def start(self) -> None:
        """Launch FFmpeg subprocess and start background reader thread."""
        if self._running:
            return

        if self.record_to_file:
            self.record_to_file.parent.mkdir(parents=True, exist_ok=True)
            if self.record_to_file.exists():
                logger.info("Resuming audio capture: appending to existing %s", self.record_to_file)
                try:
                    with wave.open(str(self.record_to_file), 'rb') as old_wav:
                        old_nframes = old_wav.getnframes()
                        old_rate = old_wav.getframerate()
                        old_channels = old_wav.getnchannels()
                        old_sampwidth = old_wav.getsampwidth()
                        old_frames = old_wav.readframes(old_nframes)
                        self._start_offset_s = old_nframes / old_rate
                    logger.info(
                        "Read %d old frames (%.1fs, %d bytes) from existing WAV",
                        old_nframes, self._start_offset_s, len(old_frames)
                    )
                    self._wav_file = wave.open(str(self.record_to_file), 'wb')
                    self._wav_file.setnchannels(old_channels)
                    self._wav_file.setsampwidth(old_sampwidth)
                    self._wav_file.setframerate(old_rate)
                    # Do NOT call setnframes — leave at 0 so the wave module
                    # calculates data length dynamically as frames are written.
                    self._wav_file.writeframes(old_frames)
                    logger.info("Re-wrote old frames to WAV; file ready for appending")
                except Exception as e:
                    logger.error("Failed to append to existing wav file: %s", e)
                    self._wav_file = wave.open(str(self.record_to_file), 'wb')
                    self._wav_file.setnchannels(1)
                    self._wav_file.setsampwidth(2)
                    self._wav_file.setframerate(self.sample_rate)
            else:
                self._wav_file = wave.open(str(self.record_to_file), 'wb')
                self._wav_file.setnchannels(1)
                self._wav_file.setsampwidth(2) # 16-bit
                self._wav_file.setframerate(self.sample_rate)

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

        if self._wav_file:
            try:
                nframes = self._wav_file.getnframes() if hasattr(self._wav_file, 'getnframes') else 'unknown'
                logger.info("Closing WAV file. Frames written: %s", nframes)
                self._wav_file.close()
                if self.record_to_file:
                    file_size = self.record_to_file.stat().st_size if self.record_to_file.exists() else 0
                    logger.info("WAV file closed. Final size: %d bytes (%.1f KB)", file_size, file_size / 1024)
            except Exception as e:
                logger.error("Failed to close wav file: %s", e)
            finally:
                self._wav_file = None

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
                        if self._running:
                            logger.error("FFmpeg process exited unexpectedly with code %s", self._process.poll())
                        break
                    time.sleep(0.01)
                    continue

                self._buffer.extend(data)
                
                if self._wav_file:
                    try:
                        self._wav_file.writeframes(data)
                    except Exception as e:
                        logger.error("Failed writing frames to wav: %s", e)

                while len(self._buffer) >= self._chunk_size_bytes:
                    chunk = bytes(self._buffer[: self._chunk_size_bytes])
                    del self._buffer[: self._chunk_size_bytes]

                    if not self._vad.filter_silent_chunks(chunk):
                        continue

                    # The timestamp should be the exact position in the final WAV file.
                    # This prevents offsets when the meeting is stopped and resumed.
                    relative_ts = self._start_offset_s + (self._chunk_index * self.chunk_seconds)

                    event = AudioChunkEvent(
                        data=chunk,
                        timestamp=relative_ts,
                        chunk_index=self._chunk_index,
                    )
                    self._chunk_index += 1
                    self._enqueue_event(event)
        except Exception as exc:  # pragma: no cover - hard to unit test thread failures
            logger.exception("Audio reader thread failed: %s", exc)
