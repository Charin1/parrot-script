from __future__ import annotations


import math
import numpy as np


class VoiceActivityDetector:
    """Energy-based Voice Activity Detector.

    Replaces webrtcvad (incompatible with Python 3.13) with a pure-Python
    implementation that uses numpy-vectorized RMS energy thresholding on 16-bit PCM frames.
    """

    def __init__(self, aggressiveness: int = 2, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self.frame_ms = 30
        self.frame_size_bytes = int(self.sample_rate * (self.frame_ms / 1000.0) * 2)

        # Maps aggressiveness 0-3 to RMS thresholds (out of max 32768)
        # Lowered thresholds so laptop microphones aren't filtered out entirely
        thresholds = {0: 10, 1: 50, 2: 100, 3: 200}
        self._rms_threshold = thresholds.get(int(aggressiveness), 100)

    @staticmethod
    def _rms(frame: bytes) -> float:
        """Compute the Root Mean Square energy of a 16-bit PCM frame."""
        if not frame:
            return 0.0
        
        # Vectorized RMS via numpy directly from buffer pointer
        samples = np.frombuffer(frame, dtype=np.int16)
        return float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))

    def is_speech(self, audio_bytes: bytes) -> bool:
        """Return True if a 30ms frame contains speech."""
        if not audio_bytes:
            return False

        frame = audio_bytes[: self.frame_size_bytes]
        if len(frame) < self.frame_size_bytes:
            frame = frame + (b"\x00" * (self.frame_size_bytes - len(frame)))

        return self._rms(frame) > self._rms_threshold

    def filter_silent_chunks(self, audio_bytes: bytes) -> bool:
        """
        Return True if a chunk has enough voiced frames (>30%).
        """
        if not audio_bytes:
            return False

        speech_frames = 0
        total_frames = 0

        for i in range(0, len(audio_bytes) - self.frame_size_bytes + 1, self.frame_size_bytes):
            frame = audio_bytes[i : i + self.frame_size_bytes]
            total_frames += 1
            if self._rms(frame) > self._rms_threshold:
                speech_frames += 1

        if total_frames == 0:
            return False

        return (speech_frames / total_frames) > 0.30
