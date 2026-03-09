from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AudioChunkEvent:
    data: bytes
    timestamp: float
    chunk_index: int


@dataclass
class TranscriptSegmentEvent:
    meeting_id: str
    speaker: str
    text: str
    start_time: float
    end_time: float
    confidence: float
    segment_id: str


@dataclass
class MeetingStatusEvent:
    meeting_id: str
    recording: bool
    speakers_detected: int
    duration_s: float
