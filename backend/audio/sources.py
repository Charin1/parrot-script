from __future__ import annotations

from typing import Protocol

from backend.audio.capture import AudioCapture
from backend.config import settings


class CaptureSource(Protocol):
    @property
    def queue(self):
        ...

    @property
    def kind(self) -> str:
        ...

    async def start(self) -> None:
        ...

    async def stop(self) -> None:
        ...


class LocalAudioSource:
    def __init__(self, meeting_id: str):
        from pathlib import Path

        audio_path = Path(settings.db_path).parent / f"{meeting_id}.wav"
        self._capture = AudioCapture(
            device_index=settings.audio_device_index,
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
