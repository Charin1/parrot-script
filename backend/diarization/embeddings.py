from __future__ import annotations

import numpy as np


class VoiceEmbedder:
    def __init__(self):
        self.encoder = None
        self._preprocess_wav = None

    def load(self) -> None:
        if self.encoder is not None:
            return

        from backend.core.pkg_resources_shim import ensure_pkg_resources
        ensure_pkg_resources()

        from resemblyzer import VoiceEncoder, preprocess_wav

        self.encoder = VoiceEncoder()
        self._preprocess_wav = preprocess_wav

    def embed(self, audio_bytes: bytes, sample_rate: int = 16000) -> np.ndarray:
        if self.encoder is None:
            self.load()

        audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        if audio.size == 0:
            return np.zeros(256, dtype=np.float32)

        wav = self._preprocess_wav(audio, source_sr=sample_rate)
        embedding = self.encoder.embed_utterance(wav)
        return np.asarray(embedding, dtype=np.float32)
