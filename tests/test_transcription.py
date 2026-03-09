from backend.transcription.models import Segment


def test_segment_confidence_bounds() -> None:
    low = Segment(start=0.0, end=1.0, text="test", words=[], avg_logprob=-5.0)
    high = Segment(start=0.0, end=1.0, text="test", words=[], avg_logprob=1.0)

    assert low.confidence == 0.0
    assert high.confidence == 1.0
