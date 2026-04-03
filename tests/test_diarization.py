from __future__ import annotations

from collections import deque

import numpy as np

from backend.config import settings
from backend.diarization.audio import pcm_duration_seconds, slice_segment_audio
from backend.diarization.speaker_cluster import SpeakerClusterer


class FakeEmbedder:
    def __init__(self, embeddings: list[np.ndarray]):
        self._embeddings = deque(embeddings)

    def embed(self, audio_bytes: bytes, sample_rate: int = 16000) -> np.ndarray:
        if not self._embeddings:
            raise AssertionError("No fake embeddings left for test")
        return self._embeddings.popleft()


def _pcm_bytes(duration_s: float, sample_rate: int = 16000) -> bytes:
    sample_count = int(duration_s * sample_rate)
    return (np.zeros(sample_count, dtype=np.int16)).tobytes()


def test_slice_segment_audio_adds_context() -> None:
    audio_bytes = _pcm_bytes(5.0)

    segment = slice_segment_audio(
        audio_bytes,
        start_s=1.0,
        end_s=1.2,
        sample_rate=16000,
        padding_s=0.2,
        min_duration_s=1.0,
    )

    assert pcm_duration_seconds(segment) == 1.0


def test_slice_segment_audio_respects_chunk_edges() -> None:
    audio_bytes = _pcm_bytes(1.0)

    segment = slice_segment_audio(
        audio_bytes,
        start_s=0.0,
        end_s=0.1,
        sample_rate=16000,
        padding_s=0.4,
        min_duration_s=1.2,
    )

    assert pcm_duration_seconds(segment) == 1.0


def test_speaker_clusterer_reuses_matching_speaker() -> None:
    speaker_a = np.ones(256, dtype=np.float32)
    embedder = FakeEmbedder([speaker_a, speaker_a * 0.99])
    clusterer = SpeakerClusterer(embedder=embedder)

    first = clusterer.assign_speaker(_pcm_bytes(1.2), segment_start=0.0, segment_end=1.2)
    second = clusterer.assign_speaker(_pcm_bytes(1.2), segment_start=1.3, segment_end=2.5)

    assert first == "Speaker 1"
    assert second == "Speaker 1"


def test_speaker_clusterer_creates_new_label_for_distinct_voice() -> None:
    speaker_a = np.ones(256, dtype=np.float32)
    speaker_b = -np.ones(256, dtype=np.float32)
    embedder = FakeEmbedder([speaker_a, speaker_b])
    clusterer = SpeakerClusterer(embedder=embedder)

    first = clusterer.assign_speaker(_pcm_bytes(1.2), segment_start=0.0, segment_end=1.2)
    second = clusterer.assign_speaker(_pcm_bytes(1.2), segment_start=1.3, segment_end=2.5)

    assert first == "Speaker 1"
    assert second == "Speaker 2"


def test_speaker_clusterer_prefers_recent_speaker_when_match_is_ambiguous() -> None:
    original_margin = settings.speaker_similarity_margin
    original_hold = settings.speaker_temporal_hold_seconds
    settings.speaker_similarity_margin = 0.08
    settings.speaker_temporal_hold_seconds = 1.5
    try:
        speaker_a = np.ones(256, dtype=np.float32)
        speaker_b = np.concatenate(
            [np.ones(128, dtype=np.float32), -np.ones(128, dtype=np.float32)]
        )
        ambiguous = np.concatenate(
            [
                np.full(128, 0.99, dtype=np.float32),
                np.full(128, 0.01, dtype=np.float32),
            ]
        )

        embedder = FakeEmbedder([speaker_a, speaker_b, ambiguous])
        clusterer = SpeakerClusterer(embedder=embedder)

        assert clusterer.assign_speaker(_pcm_bytes(1.2), segment_start=0.0, segment_end=1.2) == "Speaker 1"
        assert clusterer.assign_speaker(_pcm_bytes(1.2), segment_start=1.4, segment_end=2.6) == "Speaker 2"
        assert clusterer.assign_speaker(_pcm_bytes(0.8), segment_start=2.7, segment_end=3.5) == "Speaker 2"
    finally:
        settings.speaker_similarity_margin = original_margin
        settings.speaker_temporal_hold_seconds = original_hold


def test_reported_speaker_count_ignores_ephemeral_labels() -> None:
    original_segments = settings.speaker_min_stable_segments
    original_seconds = settings.speaker_min_stable_seconds
    original_hold = settings.speaker_temporal_hold_seconds
    settings.speaker_min_stable_segments = 2
    settings.speaker_min_stable_seconds = 2.0
    settings.speaker_temporal_hold_seconds = 0.0
    try:
        speaker_a = np.ones(256, dtype=np.float32)
        speaker_b = -np.ones(256, dtype=np.float32)
        speaker_c = np.concatenate(
            [np.ones(128, dtype=np.float32), -np.ones(128, dtype=np.float32)]
        )
        embedder = FakeEmbedder([speaker_a, speaker_b, speaker_c, speaker_b])
        clusterer = SpeakerClusterer(embedder=embedder)

        assert clusterer.assign_speaker(_pcm_bytes(3.0), segment_start=0.0, segment_end=3.0) == "Speaker 1"
        assert clusterer.reported_speaker_count() == 1

        assert clusterer.assign_speaker(_pcm_bytes(0.5), segment_start=3.1, segment_end=3.6) == "Speaker 2"
        assert clusterer.assign_speaker(_pcm_bytes(0.4), segment_start=3.7, segment_end=4.1) == "Speaker 3"
        assert clusterer.reported_speaker_count() == 1

        assert clusterer.assign_speaker(_pcm_bytes(0.6), segment_start=4.2, segment_end=4.8) == "Speaker 2"
        assert clusterer.reported_speaker_count() == 2
    finally:
        settings.speaker_min_stable_segments = original_segments
        settings.speaker_min_stable_seconds = original_seconds
        settings.speaker_temporal_hold_seconds = original_hold


def test_reported_speaker_count_merges_near_duplicate_stable_labels() -> None:
    original_segments = settings.speaker_min_stable_segments
    original_seconds = settings.speaker_min_stable_seconds
    original_merge_threshold = settings.speaker_reporting_merge_threshold
    original_cluster_threshold = settings.speaker_cluster_threshold
    settings.speaker_min_stable_segments = 1
    settings.speaker_min_stable_seconds = 0.1
    settings.speaker_cluster_threshold = 0.85
    settings.speaker_reporting_merge_threshold = 0.84
    try:
        speaker_a = np.ones(256, dtype=np.float32)
        speaker_a_split = speaker_a.copy()
        speaker_a_split[:20] = -1.0
        speaker_b = -np.ones(256, dtype=np.float32)
        embedder = FakeEmbedder([speaker_a, speaker_a_split, speaker_b])
        clusterer = SpeakerClusterer(embedder=embedder)

        assert clusterer.assign_speaker(_pcm_bytes(1.5), segment_start=0.0, segment_end=1.5) == "Speaker 1"
        assert clusterer.assign_speaker(_pcm_bytes(1.2), segment_start=1.7, segment_end=2.9) == "Speaker 2"
        assert clusterer.assign_speaker(_pcm_bytes(1.3), segment_start=3.1, segment_end=4.4) == "Speaker 3"

        assert clusterer.reported_speaker_count() == 2
    finally:
        settings.speaker_min_stable_segments = original_segments
        settings.speaker_min_stable_seconds = original_seconds
        settings.speaker_reporting_merge_threshold = original_merge_threshold
        settings.speaker_cluster_threshold = original_cluster_threshold
