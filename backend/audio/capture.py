from __future__ import annotations

import asyncio
import contextlib
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
        self._resolved_device_index: int | str | None = None

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
        try:
            self._process = subprocess.Popen(
                self._build_ffmpeg_cmd(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
            )
        except FileNotFoundError as exc:
            self._cleanup_start_failure()
            raise AudioCaptureError(
                "FFmpeg is not installed or not available on PATH. Install ffmpeg and retry."
            ) from exc
        except Exception as exc:
            self._cleanup_start_failure()
            raise AudioCaptureError(f"Failed to start ffmpeg audio capture process: {exc}") from exc

        # Fast-fail if ffmpeg exits immediately (invalid device index, permissions, etc).
        await asyncio.sleep(0.45)
        if self._process.poll() is not None:
            stderr_output = ""
            if self._process.stderr is not None:
                with contextlib.suppress(Exception):
                    stderr_output = self._process.stderr.read().decode(errors="replace")
            message = self._format_start_error(self._process.returncode, stderr_output)
            self._cleanup_start_failure()
            raise AudioCaptureError(message)

        if self._process.stdout is None:
            self._cleanup_start_failure()
            raise AudioCaptureError("Failed to open ffmpeg stdout pipe for audio capture.")

        self._running = True
        # Pass the process handle into the thread so `stop()` can safely clear `self._process`
        # without racing the reader loop.
        self._reader_thread_handle = threading.Thread(target=self._reader_thread, args=(self._process,), daemon=True)
        self._reader_thread_handle.start()

        if self._process.stderr is not None:
            self._stderr_thread_handle = threading.Thread(target=self._stderr_thread, args=(self._process,), daemon=True)
            self._stderr_thread_handle.start()

    async def stop(self) -> None:
        """Terminate FFmpeg process and stop reader threads."""
        self._running = False

        proc = self._process
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()

        if self._reader_thread_handle is not None and self._reader_thread_handle.is_alive():
            self._reader_thread_handle.join(timeout=1.0)

        if self._stderr_thread_handle is not None and self._stderr_thread_handle.is_alive():
            self._stderr_thread_handle.join(timeout=1.0)

        # Clear after threads have had a chance to exit cleanly.
        self._process = None

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

        resolved_device = self._resolve_device_index()
        self._resolved_device_index = resolved_device

        if sys.platform == "darwin":
            fmt = "avfoundation"
            input_device = f":{resolved_device}"
        elif sys.platform == "win32":
            fmt = "dshow"
            input_device = f"audio={resolved_device}"
        else:
            fmt = "pulse" # Default to pulse on linux
            input_device = "default" if str(resolved_device) == "0" else str(resolved_device)

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

    def _resolve_device_index(self) -> int | str:
        import sys

        configured = self.device_index
        if sys.platform != "darwin":
            return configured

        from backend.audio.devices import find_blackhole_device, list_audio_devices

        devices = list_audio_devices()
        if not devices:
            raise AudioCaptureError(
                "No macOS AVFoundation audio devices were detected. "
                "Check microphone permissions and ensure at least one input/system-routing device exists."
            )

        available_indexes: list[int] = []
        for device in devices:
            index = device.get("index")
            if isinstance(index, int):
                available_indexes.append(index)
                continue
            try:
                available_indexes.append(int(index))
            except (TypeError, ValueError):
                continue

        if not available_indexes:
            raise AudioCaptureError(
                "Audio devices were listed, but no valid numeric device indexes were parsed for macOS capture."
            )

        if configured in available_indexes:
            return configured

        blackhole = find_blackhole_device()
        if blackhole is not None:
            logger.warning(
                "AUDIO_DEVICE_INDEX=%s is not available. Falling back to detected BlackHole index %s.",
                configured,
                blackhole,
            )
            return blackhole

        fallback = available_indexes[0]
        logger.warning(
            "AUDIO_DEVICE_INDEX=%s is not available. Falling back to first detected audio device index %s.",
            configured,
            fallback,
        )
        return fallback

    def _cleanup_start_failure(self) -> None:
        self._running = False

        if self._process is not None:
            with contextlib.suppress(Exception):
                self._process.terminate()
                self._process.wait(timeout=1)
            with contextlib.suppress(Exception):
                self._process.kill()
            self._process = None

        if self._wav_file is not None:
            with contextlib.suppress(Exception):
                self._wav_file.close()
            self._wav_file = None

    def _format_start_error(self, exit_code: int | None, stderr_output: str) -> str:
        import sys

        stderr_lower = stderr_output.lower()
        tail_lines = [line.strip() for line in stderr_output.splitlines() if line.strip()]
        tail = " | ".join(tail_lines[-6:]) if tail_lines else "No ffmpeg stderr output."

        if sys.platform == "darwin":
            if (
                "invalid audio device index" in stderr_lower
                or "cannot open input device" in stderr_lower
                or "input/output error" in stderr_lower
                or "device not found" in stderr_lower
            ):
                resolved_hint = (
                    f"Resolved index was {self._resolved_device_index}. "
                    if self._resolved_device_index is not None
                    else ""
                )
                return (
                    "Unable to open macOS audio capture device. "
                    f"{resolved_hint}Run `.venv/bin/python scripts/list_audio_devices.py`, set `AUDIO_DEVICE_INDEX`, "
                    "and route meeting audio to that device (for example BlackHole). "
                    f"ffmpeg exit={exit_code}. Details: {tail}"
                )
            if "not authorized" in stderr_lower or "permission" in stderr_lower:
                return (
                    "macOS blocked audio capture permissions for the host process. "
                    "Allow Microphone access for Terminal/iTerm/Python in System Settings > Privacy & Security > Microphone, "
                    "then restart the app. "
                    f"ffmpeg exit={exit_code}. Details: {tail}"
                )

        return f"Audio capture failed to start (ffmpeg exit={exit_code}). Details: {tail}"

    def _stderr_thread(self, proc: subprocess.Popen) -> None:
        stderr = proc.stderr
        if stderr is None:
            return

        while self._running:
            line = stderr.readline()
            if not line:
                break
            logger.debug("ffmpeg: %s", line.decode(errors="replace").strip())

    def _enqueue_event(self, event: AudioChunkEvent) -> None:
        if self._loop is None or not self._loop.is_running():
            return
        future = asyncio.run_coroutine_threadsafe(self.queue.put(event), self._loop)
        try:
            future.result(timeout=2)
        except Exception as exc:
            # If the event loop is shutting down or overloaded, drop the chunk rather than
            # crashing the reader thread (which would stop all future transcript updates).
            logger.warning("Failed to enqueue audio chunk: %r", exc)

    def _reader_thread(self, proc: subprocess.Popen) -> None:
        stdout = proc.stdout
        if stdout is None:
            return

        try:
            while self._running:
                data = stdout.read(4096)
                if not data:
                    if not self._running:
                        break
                    exit_code = proc.poll()
                    if exit_code is not None:
                        logger.error("FFmpeg process exited unexpectedly with code %s", exit_code)
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
            self._running = False
            with contextlib.suppress(Exception):
                proc.terminate()
