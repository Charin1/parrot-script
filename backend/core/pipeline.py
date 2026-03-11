from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from typing import Optional
from uuid import uuid4

from backend.api.websocket import manager
from backend.audio.capture import AudioCapture
from backend.config import settings
from backend.core.events import MeetingStatusEvent, TranscriptSegmentEvent
from backend.diarization.speaker_cluster import SpeakerClusterer
from pathlib import Path
from backend.storage.repositories.segments import SegmentsRepository
from backend.storage.repositories.speakers import SpeakersRepository
from backend.transcription.whisper_stream import WhisperTranscriber

logger = logging.getLogger(__name__)

# Shared executor for CPU-bound work (Whisper + Resemblyzer).
# max_workers=4 allows 2-3 Whisper transcriptions + speaker embeddings in parallel.
_cpu_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="pipeline-cpu")

# Max number of chunks processed concurrently per pipeline.
MAX_CONCURRENT_CHUNKS = 3


class MeetingPipeline:
    def __init__(self, meeting_id: str):
        self.meeting_id = meeting_id
        audio_path = Path(settings.db_path).parent / f"{meeting_id}.wav"
        
        self.capture = AudioCapture(
            device_index=settings.audio_device_index,
            sample_rate=settings.audio_sample_rate,
            chunk_seconds=settings.audio_chunk_seconds,
            record_to_file=audio_path,
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
        
        existing_speakers = await self.speakers_repo.get_by_meeting(self.meeting_id)
        if existing_speakers:
            self.clusterer.speaker_count = len(existing_speakers)

        await loop.run_in_executor(_cpu_executor, self.transcriber.load_model)
        await loop.run_in_executor(_cpu_executor, self.clusterer.embedder.load)

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

        # Drain any remaining chunks sequentially (pipeline is stopping)
        loop = asyncio.get_running_loop()
        while not self.capture.queue.empty():
            chunk = self.capture.queue.get_nowait()
            try:
                segments_future = loop.run_in_executor(
                    _cpu_executor, self.transcriber.transcribe, chunk.data
                )
                speaker_future = loop.run_in_executor(
                    _cpu_executor, self.clusterer.assign_speaker, chunk.data
                )
                segments, speaker = await asyncio.gather(segments_future, speaker_future)
                if not segments:
                    continue
                for segment in segments:
                    event = TranscriptSegmentEvent(
                        meeting_id=self.meeting_id,
                        speaker=speaker,
                        text=segment.text,
                        start_time=chunk.timestamp + segment.start,
                        end_time=chunk.timestamp + segment.end,
                        confidence=segment.confidence,
                        segment_id=str(uuid4()),
                    )
                    await self.segments_repo.insert(event)
                    await self.speakers_repo.upsert(self.meeting_id, speaker)
                    await manager.broadcast(
                        self.meeting_id,
                        {
                            "type": "transcript",
                            "data": {"id": event.segment_id, **asdict(event)},
                        },
                    )
            except Exception as exc:
                logger.exception("Failed to drain chunk: %s", exc)

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
        """Main loop: process chunks concurrently but emit results in strict arrival order."""
        # Completed results keyed by sequence number
        results: dict[int, tuple] = {}   # seq -> (chunk, segments, speaker)
        next_seq_to_emit = 0             # the next seq we must emit
        seq_counter = 0                  # monotonically increasing per chunk
        pending: dict[int, asyncio.Task] = {}  # seq -> processing task
        results_ready = asyncio.Event()  # signalled when any result lands

        async def _emit_ready():
            """Emit results in strict sequence order."""
            nonlocal next_seq_to_emit
            while next_seq_to_emit in results:
                chunk, segments, speaker = results.pop(next_seq_to_emit)
                next_seq_to_emit += 1

                if not segments:
                    continue

                for segment in segments:
                    event = TranscriptSegmentEvent(
                        meeting_id=self.meeting_id,
                        speaker=speaker,
                        text=segment.text,
                        start_time=chunk.timestamp + segment.start,
                        end_time=chunk.timestamp + segment.end,
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

        async def _process_and_store(seq: int, chunk) -> None:
            """Run Whisper + speaker embedding in parallel, store result."""
            try:
                loop = asyncio.get_running_loop()
                segments_future = loop.run_in_executor(
                    _cpu_executor, self.transcriber.transcribe, chunk.data
                )
                speaker_future = loop.run_in_executor(
                    _cpu_executor, self.clusterer.assign_speaker, chunk.data
                )
                segments, speaker = await asyncio.gather(segments_future, speaker_future)
                results[seq] = (chunk, segments, speaker)
            except Exception as exc:
                logger.exception("Failed to process audio chunk seq=%d: %s", seq, exc)
                results[seq] = (chunk, [], "Unknown")
            finally:
                pending.pop(seq, None)
                results_ready.set()

        while self.running:
            try:
                chunk = await asyncio.wait_for(self.capture.queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                # Even on timeout, try to emit any ready results
                await _emit_ready()
                continue

            # Limit concurrency: wait if too many in-flight
            while len(pending) >= MAX_CONCURRENT_CHUNKS:
                results_ready.clear()
                await results_ready.wait()
                await _emit_ready()

            seq = seq_counter
            seq_counter += 1
            task = asyncio.create_task(_process_and_store(seq, chunk))
            pending[seq] = task

            # Try to emit any results that are ready
            await _emit_ready()

        # Wait for all in-flight tasks to finish
        if pending:
            await asyncio.gather(*pending.values(), return_exceptions=True)
        # Emit any remaining results
        await _emit_ready()


