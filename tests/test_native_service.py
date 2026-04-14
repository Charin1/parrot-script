from __future__ import annotations

from backend.native.service import NativeAttributionService


def test_compute_overlap_attributions_prefers_clear_winner() -> None:
    service = NativeAttributionService()
    segments = [{"id": "s1", "start_time": 0.0, "end_time": 5.0}]
    events = [
        {"participant_id": "p1", "start_time": 0.0, "end_time": 4.0},
        {"participant_id": "p2", "start_time": 4.5, "end_time": 5.0},
    ]

    mapped = service._compute_overlap_attributions(segments, events)
    assert len(mapped) == 1
    assert mapped[0]["participant_id"] == "p1"


def test_compute_overlap_attributions_skips_ambiguous_tie() -> None:
    service = NativeAttributionService()
    segments = [{"id": "s1", "start_time": 0.0, "end_time": 2.0}]
    events = [
        {"participant_id": "p1", "start_time": 0.0, "end_time": 1.0},
        {"participant_id": "p2", "start_time": 1.0, "end_time": 2.0},
    ]

    mapped = service._compute_overlap_attributions(segments, events)
    assert mapped == []
