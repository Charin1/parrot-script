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
