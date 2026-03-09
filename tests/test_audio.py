import numpy as np

from backend.audio.vad import VoiceActivityDetector


def test_vad_silence_filtered() -> None:
    vad = VoiceActivityDetector()
    silence = np.zeros(16000 * 2, dtype=np.int16).tobytes()
    assert vad.filter_silent_chunks(silence) is False
