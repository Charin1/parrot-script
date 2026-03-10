from __future__ import annotations

from collections import deque

import numpy as np

import logging
from backend.config import settings
from backend.diarization.embeddings import VoiceEmbedder

logger = logging.getLogger(__name__)

class SpeakerClusterer:
    def __init__(self):
        self.embedder = VoiceEmbedder()
        self.embedding_history: deque[tuple[str, np.ndarray]] = deque(
            maxlen=settings.embedding_window_size
        )
        self.labels: list[str] = []
        self.speaker_count: int = 0

    def assign_speaker(self, audio_bytes: bytes) -> str:
        embedding = self.embedder.embed(audio_bytes)

        if not self.embedding_history:
            label = self._new_label()
            self.embedding_history.append((label, embedding))
            self.labels.append(label)
            logger.info("First speaker detected: %s", label)
            return label

        unique = self.unique_speakers
        similarities = [
            (label, self._cosine_similarity(embedding, self.get_centroid(label)))
            for label in unique
        ]
        best_label, best_score = max(similarities, key=lambda item: item[1])
        
        logger.info("Speaker similarities: %s", similarities)
        logger.info("Best match: %s with score %.3f (Threshold: %.3f)", best_label, best_score, settings.speaker_cluster_threshold)

        if best_score >= settings.speaker_cluster_threshold or len(unique) >= settings.max_speakers:
            assigned = best_label
        else:
            assigned = self._new_label()

        self.embedding_history.append((assigned, embedding))
        self.labels.append(assigned)
        logger.info("Assigned chunk to %s", assigned)
        return assigned

    def get_centroid(self, label: str) -> np.ndarray:
        matches = [embedding for current_label, embedding in self.embedding_history if current_label == label]
        if not matches:
            return np.zeros(256, dtype=np.float32)
        return np.mean(np.stack(matches), axis=0)

    def reset(self, initial_speaker_count: int = 0) -> None:
        self.embedding_history.clear()
        self.labels.clear()
        self.speaker_count = initial_speaker_count

    @property
    def unique_speakers(self) -> list[str]:
        return list(dict.fromkeys(self.labels))

    def _new_label(self) -> str:
        self.speaker_count += 1
        return f"Speaker {self.speaker_count}"

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        a_norm = float(np.linalg.norm(a))
        b_norm = float(np.linalg.norm(b))
        if a_norm == 0.0 or b_norm == 0.0:
            return 0.0
        return float(np.dot(a, b) / (a_norm * b_norm))
