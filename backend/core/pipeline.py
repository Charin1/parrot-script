from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict
from typing import Optional
from uuid import uuid4

from backend.api.websocket import manager
from backend.audio.capture import AudioCapture
from backend.config import settings
from backend.core.events import MeetingStatusEvent, TranscriptSegmentEvent
from backend.diarization.speaker_cluster import SpeakerClusterer
from backend.storage.repositories.segments import SegmentsRepository
from backend.storage.repositories.speakers import SpeakersRepository
from backend.transcription.whisper_stream import WhisperTranscriber

logger = logging.getLogger(__name__)


class MeetingPipeline:
    def __init__(self, meeting_id: str):
        self.meeting_id = meeting_id
        self.capture = AudioCapture(
            device_index=settings.audio_device_index,
            sample_rate=settings.audio_sample_rate,
            chunk_seconds=settings.audio_chunk_seconds,
        )
        self.transcriber = WhisperTranscriber()
        self.clusterer = SpeakerClusterer()
        self.segments_repo = SegmentsRepository()
        self.speakers_repo = SpeakersRepository()

        self.running = False
        self.start_epoch: float = 0.0
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if self.running:
            return

        self.clusterer.reset()
        loop = asyncio.get_running_loop()

        await loop.run_in_executor(None, self.transcriber.load_model)
        await loop.run_in_executor(None, self.clusterer.embedder.load)

        await self.capture.start()
        self.running = True
        self.start_epoch = time.time()
        self._task = asyncio.create_task(self._process_loop())

        await manager.broadcast(
            self.meeting_id,
            {
                "type": "status",
                "data": asdict(
                    MeetingStatusEvent(
                        meeting_id=self.meeting_id,
                        recording=True,
                        speakers_detected=0,
                        duration_s=0.0,
                    )
                ),
            },
        )

    async def stop(self) -> None:
        self.running = False
        await self.capture.stop()

        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except asyncio.TimeoutError:
                self._task.cancel()
                logger.warning("Pipeline loop did not stop in time for %s", self.meeting_id)
            finally:
                self._task = None

        while not self.capture.queue.empty():
            chunk = self.capture.queue.get_nowait()
            await self._process_chunk(chunk)

        await manager.broadcast(
            self.meeting_id,
            {
                "type": "status",
                "data": asdict(
                    MeetingStatusEvent(
                        meeting_id=self.meeting_id,
                        recording=False,
                        speakers_detected=len(self.clusterer.unique_speakers),
                        duration_s=max(0.0, time.time() - self.start_epoch),
                    )
                ),
            },
        )

    async def _process_loop(self) -> None:
        while self.running:
            try:
                chunk = await asyncio.wait_for(self.capture.queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            try:
                await self._process_chunk(chunk)
            except Exception as exc:
                logger.exception("Failed to process audio chunk: %s", exc)

    async def _process_chunk(self, chunk) -> None:
        segments = await self.transcriber.transcribe_async(chunk.data)
        if not segments:
            return

        speaker = self.clusterer.assign_speaker(chunk.data)

        for segment in segments:
            event = TranscriptSegmentEvent(
                meeting_id=self.meeting_id,
                speaker=speaker,
                text=segment.text,
                start_time=(chunk.timestamp - self.start_epoch) + segment.start,
                end_time=(chunk.timestamp - self.start_epoch) + segment.end,
                confidence=segment.confidence,
                segment_id=str(uuid4()),
            )

            await self.segments_repo.insert(event)
            await self.speakers_repo.upsert(self.meeting_id, speaker)
            await manager.broadcast(
                self.meeting_id,
                {
                    "type": "transcript",
                    "data": {
                        "id": event.segment_id,
                        **asdict(event),
                    },
                },
            )

        await manager.broadcast(
            self.meeting_id,
            {
                "type": "status",
                "data": asdict(
                    MeetingStatusEvent(
                        meeting_id=self.meeting_id,
                        recording=True,
                        speakers_detected=len(self.clusterer.unique_speakers),
                        duration_s=max(0.0, time.time() - self.start_epoch),
                    )
                ),
            },
        )
