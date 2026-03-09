#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import soundfile as sf

from backend.config import settings
from backend.transcription.whisper_stream import WhisperTranscriber


def _resample_if_needed(audio: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate:
        return audio

    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)

    src_idx = np.arange(audio.shape[0], dtype=np.float32)
    dst_len = int(audio.shape[0] * (dst_rate / src_rate))
    dst_idx = np.linspace(0, audio.shape[0] - 1, num=dst_len, dtype=np.float32)
    return np.interp(dst_idx, src_idx, audio).astype(np.float32)


def main() -> None:
    parser = argparse.ArgumentParser(description="Test Faster-Whisper on a WAV file")
    parser.add_argument("--file", required=True, help="Path to WAV file")
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    audio, sample_rate = sf.read(file_path.as_posix(), dtype="float32")
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)

    audio = _resample_if_needed(audio, sample_rate, settings.audio_sample_rate)
    pcm16 = np.clip(audio, -1.0, 1.0)
    pcm_bytes = (pcm16 * 32767.0).astype(np.int16).tobytes()

    transcriber = WhisperTranscriber()
    segments = transcriber.transcribe(pcm_bytes)

    if not segments:
        print("No transcript segments generated.")
        return

    for segment in segments:
        print(f"[{segment.start:7.2f}s - {segment.end:7.2f}s] {segment.text}")


if __name__ == "__main__":
    main()
