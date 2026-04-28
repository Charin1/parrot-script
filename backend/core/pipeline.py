from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from typing import Optional
from uuid import uuid4

from backend.api.websocket import manager
from backend.audio.sources import CaptureSource, LocalAudioSource
from backend.config import settings
from backend.core.events import MeetingStatusEvent, TranscriptSegmentEvent
from backend.diarization.audio import slice_segment_audio
from backend.diarization.speaker_cluster import SpeakerClusterer
from backend.storage.repositories.segments import SegmentsRepository
from backend.storage.repositories.speakers import SpeakersRepository
from backend.transcription.models import Segment
from backend.transcription.whisper_stream import WhisperTranscriber
from backend.storage.vector_store import VectorStore

logger = logging.getLogger(__name__)

# Shared executor for CPU-bound work (Whisper + speaker embeddings).
# max_workers=4 allows multiple transcriptions while keeping diarization responsive.
_cpu_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="pipeline-cpu")

# Max number of chunks processed concurrently per pipeline.
MAX_CONCURRENT_CHUNKS = 3


class MeetingPipeline:
    def __init__(self, meeting_id: str, capture_source: CaptureSource | None = None):
        self.meeting_id = meeting_id
        self.capture_source = capture_source or LocalAudioSource(meeting_id)
        self.transcriber = WhisperTranscriber()
        self.clusterer = SpeakerClusterer()
        self.segments_repo = SegmentsRepository()
        self.speakers_repo = SpeakersRepository()
        self.vector_store = VectorStore()

        self.running = False
        self.start_epoch: float = 0.0
        self._task: Optional[asyncio.Task] = None
        self._index_buffer: list[TranscriptSegmentEvent] = []
        self._INDEX_BATCH_SIZE = 5

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

        await self.capture_source.start()
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

    async def wait(self) -> None:
        """Wait until the internal processing loop completes."""
        task = self._task
        if task is None:
            return
        await task

    async def stop(self) -> None:
        self.running = False
        await self.capture_source.stop()

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
        while not self.capture_source.queue.empty():
            chunk = self.capture_source.queue.get_nowait()
            try:
                segments = await loop.run_in_executor(
                    _cpu_executor, self.transcriber.transcribe, chunk.data
                )
                if not segments:
                    continue
                speaker_labels = await loop.run_in_executor(
                    _cpu_executor, self._assign_speakers, chunk.data, chunk.timestamp, segments, chunk.track_id
                )
                for segment, speaker in zip(segments, speaker_labels):
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
                    
                    self._index_buffer.append(event)
                    if len(self._index_buffer) >= self._INDEX_BATCH_SIZE:
                        batch = [asdict(e) for e in self._index_buffer]
                        self._index_buffer.clear()
                        asyncio.create_task(self.vector_store.add_segments(self.meeting_id, batch))

                    await manager.broadcast(
                        self.meeting_id,
                        {
                            "type": "transcript",
                            "data": {"id": event.segment_id, **asdict(event)},
                        },
                    )
            except Exception as exc:
                logger.exception("Failed to drain chunk: %s", exc)

        # Final flush of the indexing buffer
        if self._index_buffer:
            batch = [asdict(e) for e in self._index_buffer]
            self._index_buffer.clear()
            await self.vector_store.add_segments(self.meeting_id, batch)

        await manager.broadcast(
            self.meeting_id,
            {
                "type": "status",
                "data": asdict(
                    MeetingStatusEvent(
                        meeting_id=self.meeting_id,
                        recording=False,
                        speakers_detected=self.clusterer.reported_speaker_count(),
                        duration_s=max(0.0, time.time() - self.start_epoch),
                    )
                ),
            },
        )

    async def switch_source(self, new_source: CaptureSource) -> None:
        """Seamlessly swap the capture source (e.g. from Audio Only to Video + Audio)."""
        if not self.running:
            self.capture_source = new_source
            return

        logger.info("Switching capture source for meeting %s to %s", self.meeting_id, new_source.kind)
        await self.capture_source.stop()
        self.capture_source = new_source
        await self.capture_source.start()

    async def _process_loop(self) -> None:
        """Main loop: process chunks concurrently but emit results in strict arrival order."""
        # Completed results keyed by sequence number
        results: dict[int, tuple] = {}   # seq -> (chunk, segments)
        next_seq_to_emit = 0             # the next seq we must emit
        seq_counter = 0                  # monotonically increasing per chunk
        pending: dict[int, asyncio.Task] = {}  # seq -> processing task
        results_ready = asyncio.Event()  # signalled when any result lands
        processed_chunks = 0

        async def _emit_ready():
            """Emit results in strict sequence order."""
            nonlocal next_seq_to_emit, processed_chunks
            while next_seq_to_emit in results:
                seq = next_seq_to_emit
                chunk, segments = results.pop(next_seq_to_emit)
                next_seq_to_emit += 1

                processed_chunks += 1

                if getattr(chunk, "total_chunks", None) is not None:
                    await manager.broadcast(
                        self.meeting_id,
                        {
                            "type": "transcript_progress",
                            "data": {
                                "meeting_id": self.meeting_id,
                                "current": int(getattr(chunk, "chunk_index", processed_chunks)) + 1,
                                "total": int(getattr(chunk, "total_chunks")),
                            },
                        },
                    )

                if not segments:
                    continue

                try:
                    loop = asyncio.get_running_loop()
                    speaker_labels = await loop.run_in_executor(
                        _cpu_executor,
                        self._assign_speakers,
                        chunk.data,
                        chunk.timestamp,
                        segments,
                        chunk.track_id,
                    )
                except Exception as exc:
                    logger.exception("Failed to assign speakers for audio chunk seq=%d: %s", seq, exc)
                    speaker_labels = ["Unknown"] * len(segments)

                for segment, speaker in zip(segments, speaker_labels):
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

                    self._index_buffer.append(event)
                    if len(self._index_buffer) >= self._INDEX_BATCH_SIZE:
                        batch = [asdict(e) for e in self._index_buffer]
                        self._index_buffer.clear()
                        asyncio.create_task(self.vector_store.add_segments(self.meeting_id, batch))

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
                                speakers_detected=self.clusterer.reported_speaker_count(),
                                duration_s=max(0.0, time.time() - self.start_epoch),
                            )
                        ),
                    },
                )

        async def _process_and_store(seq: int, chunk) -> None:
            """Transcribe a chunk and store the result for ordered speaker assignment."""
            try:
                loop = asyncio.get_running_loop()
                segments = await loop.run_in_executor(
                    _cpu_executor, self.transcriber.transcribe, chunk.data
                )
                results[seq] = (chunk, segments)
            except Exception as exc:
                logger.exception("Failed to process audio chunk seq=%d: %s", seq, exc)
                results[seq] = (chunk, [])
            finally:
                pending.pop(seq, None)
                results_ready.set()

        while self.running:
            try:
                chunk = await asyncio.wait_for(self.capture_source.queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                # Even on timeout, try to emit any ready results
                await _emit_ready()
                continue
            if chunk is None:
                # End-of-stream sentinel (used by file imports).
                self.running = False
                break

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

        await manager.broadcast(
            self.meeting_id,
            {
                "type": "status",
                "data": asdict(
                    MeetingStatusEvent(
                        meeting_id=self.meeting_id,
                        recording=False,
                        speakers_detected=self.clusterer.reported_speaker_count(),
                        duration_s=max(0.0, time.time() - self.start_epoch),
                    )
                ),
            },
        )

    def _assign_speakers(
        self,
        chunk_audio: bytes,
        chunk_timestamp: float,
        segments: list[Segment],
        track_id: int = 0,
    ) -> list[str]:
        # Track 0 is the local user (Mic). 
        # We assign it 100% confidence speaker label from settings.
        if track_id == 0 and settings.audio_mic_index is not None:
            return [settings.local_speaker_name] * len(segments)

        labels: list[str] = []
        for segment in segments:
            segment_audio = slice_segment_audio(
                chunk_audio,
                segment.start,
                segment.end,
                sample_rate=settings.audio_sample_rate,
                padding_s=settings.speaker_segment_padding_seconds,
                min_duration_s=settings.speaker_min_segment_seconds,
            )
            labels.append(
                self.clusterer.assign_speaker(
                    segment_audio,
                    segment_start=chunk_timestamp + segment.start,
                    segment_end=chunk_timestamp + segment.end,
                )
            )
        return labels
