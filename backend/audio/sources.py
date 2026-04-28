from __future__ import annotations

import asyncio
import contextlib
from typing import Protocol

from backend.audio.capture import AudioCapture
from backend.config import settings
from backend.core.events import AudioChunkEvent


class CaptureSource(Protocol):
    @property
    def queue(self):
        ...

    @property
    def kind(self) -> str:
        ...

    async def stop(self) -> None:
        ...

    def get_current_duration(self) -> float:
        ...


class LocalAudioSource:
    def __init__(self, meeting_id: str):
        from pathlib import Path

        audio_path = Path(settings.db_path).parent / f"{meeting_id}.wav"
        self._capture = AudioCapture(
            device_index=settings.audio_device_index,
            mic_index=settings.audio_mic_index,
            system_index=settings.audio_system_index,
            sample_rate=settings.audio_sample_rate,
            chunk_seconds=settings.audio_chunk_seconds,
            record_to_file=audio_path,
        )

    @property
    def queue(self):
        return self._capture.queue

    @property
    def kind(self) -> str:
        return "local_audio"

    async def start(self) -> None:
        await self._capture.start()

    async def stop(self) -> None:
        await self._capture.stop()

    def get_current_duration(self) -> float:
        return self._capture._start_offset_s + (self._capture._chunk_index * self._capture.chunk_seconds)


class LocalVideoAudioSource:
    """Runs audio capture + screen capture in parallel.

    The pipeline only consumes audio chunks via ``queue``.  The screen
    capture writes directly to disk as an MP4 — it is a recording-only
    side-effect and does not feed into the transcription pipeline.
    """

    def __init__(
        self,
        meeting_id: str,
        resolution: str | None = None,
        ghost_mode: bool = True,
        target_window_title: str | None = None,
    ):
        from pathlib import Path
        from backend.video.video_capture import ScreenCapture

        audio_path = Path(settings.db_path).parent / f"{meeting_id}.wav"
        self._audio = AudioCapture(
            device_index=settings.audio_device_index,
            mic_index=settings.audio_mic_index,
            system_index=settings.audio_system_index,
            sample_rate=settings.audio_sample_rate,
            chunk_seconds=settings.audio_chunk_seconds,
            record_to_file=audio_path,
        )
        self._video = ScreenCapture(
            meeting_id=meeting_id,
            resolution=resolution,
            ghost_mode=ghost_mode,
            target_window_title=target_window_title,
        )

    @property
    def queue(self):
        return self._audio.queue

    @property
    def kind(self) -> str:
        return "local_video_audio"

    async def start(self) -> None:
        await self._audio.start()
        try:
            await self._video.start()
        except Exception:
            # Prevent dangling audio capture when video startup fails.
            await self._audio.stop()
            raise

    async def stop(self) -> None:
        await self._video.stop()
        await self._audio.stop()

    def get_current_duration(self) -> float:
        return self._audio._start_offset_s + (self._audio._chunk_index * self._audio.chunk_seconds)


class ImportedFileAudioSource:
    """Feeds audio chunks from a pre-existing WAV file.

    This is used for "Upload Meeting" imports where the backend should process
    a static media file in the background.
    """

    def __init__(self, wav_path, *, sample_rate: int | None = None, chunk_seconds: int | None = None):
        from pathlib import Path

        self.wav_path = Path(wav_path)
        self.sample_rate = sample_rate or settings.audio_sample_rate
        self.chunk_seconds = chunk_seconds or settings.audio_chunk_seconds
        self._queue: asyncio.Queue[AudioChunkEvent | None] = asyncio.Queue(maxsize=12)
        self._task: asyncio.Task | None = None
        self._running = False
        self._total_chunks: int | None = None

    @property
    def queue(self):
        return self._queue

    @property
    def kind(self) -> str:
        return "imported_file"

    @property
    def total_chunks(self) -> int | None:
        return self._total_chunks

    async def start(self) -> None:
        if self._running:
            return
        if not self.wav_path.exists():
            raise FileNotFoundError(f"WAV not found: {self.wav_path}")
        self._running = True
        self._task = asyncio.create_task(self._feed())

    async def stop(self) -> None:
        self._running = False
        if self._task is not None and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        self._task = None
        # Best-effort: ensure pipeline can exit if it's waiting.
        with contextlib.suppress(Exception):
            self._queue.put_nowait(None)

    def get_current_duration(self) -> float:
        return self._total_chunks * self.chunk_seconds if self._total_chunks else 0.0

    async def _read_wav_total_frames(self) -> tuple[int, int]:
        import wave

        def _read() -> tuple[int, int]:
            with wave.open(str(self.wav_path), "rb") as wf:
                return wf.getnframes(), wf.getframerate()

        return await asyncio.to_thread(_read)

    async def _feed(self) -> None:
        import wave
        import contextlib

        frames_total, rate = await self._read_wav_total_frames()
        # Prefer the WAV's framerate if it differs.
        if rate and rate != self.sample_rate:
            self.sample_rate = rate

        frames_per_chunk = int(self.chunk_seconds * self.sample_rate)
        total_chunks = (frames_total + frames_per_chunk - 1) // frames_per_chunk if frames_per_chunk > 0 else 0
        self._total_chunks = int(total_chunks)

        def _open_wav():
            return wave.open(str(self.wav_path), "rb")

        wf = await asyncio.to_thread(_open_wav)
        try:
            chunk_index = 0
            while self._running:
                frames = await asyncio.to_thread(wf.readframes, frames_per_chunk)
                if not frames:
                    break
                timestamp = chunk_index * float(self.chunk_seconds)
                event = AudioChunkEvent(
                    data=frames,
                    timestamp=timestamp,
                    chunk_index=chunk_index,
                    total_chunks=self._total_chunks,
                )
                await self._queue.put(event)
                chunk_index += 1
        finally:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(wf.close)

        # Signal end-of-stream to the pipeline.
        with contextlib.suppress(Exception):
            await self._queue.put(None)
