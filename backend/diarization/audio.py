from __future__ import annotations


def pcm_duration_seconds(audio_bytes: bytes, sample_rate: int = 16000) -> float:
    if not audio_bytes or sample_rate <= 0:
        return 0.0
    return len(audio_bytes) / float(sample_rate * 2)


def slice_segment_audio(
    audio_bytes: bytes,
    start_s: float,
    end_s: float,
    *,
    sample_rate: int = 16000,
    padding_s: float = 0.0,
    min_duration_s: float = 0.0,
) -> bytes:
    """Extract a PCM segment, expanding it with optional padding/context."""
    if not audio_bytes or sample_rate <= 0:
        return b""

    total_duration_s = pcm_duration_seconds(audio_bytes, sample_rate=sample_rate)
    if total_duration_s <= 0.0:
        return b""

    start_s = max(0.0, float(start_s) - max(0.0, padding_s))
    end_s = min(total_duration_s, float(end_s) + max(0.0, padding_s))

    if end_s <= start_s:
        return audio_bytes

    if min_duration_s > 0.0 and (end_s - start_s) < min_duration_s:
        deficit = min_duration_s - (end_s - start_s)
        start_s = max(0.0, start_s - (deficit / 2.0))
        end_s = min(total_duration_s, end_s + (deficit / 2.0))

        # If we hit an edge, bias the remaining expansion to the other side.
        remaining = min_duration_s - (end_s - start_s)
        if remaining > 0.0:
            if start_s <= 0.0:
                end_s = min(total_duration_s, end_s + remaining)
            elif end_s >= total_duration_s:
                start_s = max(0.0, start_s - remaining)

    start_index = int(start_s * sample_rate) * 2
    end_index = int(end_s * sample_rate) * 2

    if end_index <= start_index:
        return audio_bytes

    return audio_bytes[start_index:end_index]
