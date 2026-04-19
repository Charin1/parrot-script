from __future__ import annotations

import logging
import threading
from collections import deque

import numpy as np

from backend.config import settings
from backend.diarization.embeddings import VoiceEmbedder

logger = logging.getLogger(__name__)


class SpeakerClusterer:
    def __init__(self, embedder: VoiceEmbedder | None = None):
        self.embedder = embedder or VoiceEmbedder()
        # Keep embeddings per-speaker (instead of a single global sliding window).
        # A global window tends to "forget" quiet speakers and makes centroids drift toward
        # whoever talks the most, which eventually collapses attribution.
        self.embedding_history_by_label: dict[str, deque[np.ndarray]] = {}
        self.labels: list[str] = []
        self.speaker_count: int = 0
        self.label_assignment_counts: dict[str, int] = {}
        self.label_total_durations: dict[str, float] = {}
        self._lock = threading.Lock()
        self._last_assignment: tuple[str, float | None] | None = None

    def assign_speaker(
        self,
        audio_bytes: bytes,
        *,
        segment_start: float | None = None,
        segment_end: float | None = None,
    ) -> str:
        # Compute embedding outside the lock (CPU-bound, safe to run concurrently)
        embedding = self.embedder.embed(audio_bytes)
        embedding_norm = float(np.linalg.norm(embedding))

        with self._lock:
            if embedding_norm == 0.0:
                fallback = self._recent_label(segment_start)
                if fallback is None and self.labels:
                    fallback = self.labels[-1]
                if fallback is None:
                    fallback = self._new_label()
                self._remember_assignment(
                    fallback,
                    embedding,
                    segment_start,
                    segment_end,
                    remember_embedding=False,
                )
                logger.info("Zero-vector speaker embedding, falling back to %s", fallback)
                return fallback

            if not self._has_any_embedding_locked():
                label = self._new_label()
                self._remember_assignment(label, embedding, segment_start, segment_end)
                logger.info("First speaker detected: %s", label)
                return label

            unique = self.unique_speakers
            similarities = {
                label: self._cosine_similarity(embedding, self.get_centroid(label))
                for label in unique
            }
            ranked = sorted(similarities.items(), key=lambda item: item[1], reverse=True)
            best_label, best_score = ranked[0]
            runner_up_score = ranked[1][1] if len(ranked) > 1 else -1.0
            best_margin = best_score - runner_up_score

            recent_label = self._recent_label(segment_start)
            recent_score = similarities.get(recent_label, -1.0) if recent_label else -1.0

            logger.debug("Speaker similarities: %s", ranked)
            logger.debug(
                "Best match: %s with score %.3f (Threshold: %.3f, Margin: %.3f)",
                best_label,
                best_score,
                settings.speaker_cluster_threshold,
                best_margin,
            )

            confident_best = best_score >= settings.speaker_cluster_threshold
            clear_best = best_margin >= settings.speaker_similarity_margin or len(ranked) == 1
            recent_is_plausible = (
                recent_label is not None
                and len(ranked) > 1
                and recent_score >= 0.0
                and recent_score >= (best_score - settings.speaker_similarity_margin)
            )

            if confident_best and (clear_best or best_label == recent_label):
                assigned = best_label
                remember_embedding = True
            elif recent_is_plausible:
                assigned = recent_label
                logger.info(
                    "Reusing recent speaker %s due to ambiguous match (recent score %.3f)",
                    recent_label,
                    recent_score,
                )
                # Avoid centroid drift: only update history if we're truly confident.
                remember_embedding = recent_score >= settings.speaker_update_threshold
            elif len(unique) >= settings.max_speakers:
                assigned = best_label
                remember_embedding = best_score >= settings.speaker_update_threshold and clear_best
            else:
                assigned = self._new_label()
                remember_embedding = True

            # Extra guardrail: even when we assign a label, only learn from it when the
            # embedding is strongly consistent with that label's centroid.
            # This is the main protection against "everyone becomes the dominant speaker".
            if assigned in similarities:
                assigned_score = similarities.get(assigned, -1.0)
                if assigned_score < settings.speaker_update_threshold:
                    remember_embedding = False

            self._remember_assignment(
                assigned,
                embedding,
                segment_start,
                segment_end,
                remember_embedding=remember_embedding,
            )
            logger.debug("Assigned chunk to %s", assigned)
            return assigned

    def get_centroid(self, label: str) -> np.ndarray:
        matches = self.embedding_history_by_label.get(label)
        if not matches:
            return np.zeros(256, dtype=np.float32)
        return np.mean(np.stack(list(matches)), axis=0)

    def reset(self, initial_speaker_count: int = 0) -> None:
        with self._lock:
            self.embedding_history_by_label.clear()
            self.labels.clear()
            self.speaker_count = initial_speaker_count
            self.label_assignment_counts.clear()
            self.label_total_durations.clear()
            self._last_assignment = None

    @property
    def unique_speakers(self) -> list[str]:
        return list(dict.fromkeys(self.labels))

    def reported_speaker_count(self) -> int:
        with self._lock:
            if not self.labels:
                return 0

            stable_labels = self._stable_labels_locked()
            if not stable_labels:
                return 1

            merged_groups: list[tuple[np.ndarray, float]] = []
            for label in stable_labels:
                centroid = self.get_centroid(label)
                if float(np.linalg.norm(centroid)) == 0.0:
                    continue

                weight = max(
                    float(self.label_assignment_counts.get(label, 0)),
                    self.label_total_durations.get(label, 0.0),
                )
                merged = False

                for index, (group_centroid, group_weight) in enumerate(merged_groups):
                    similarity = self._cosine_similarity(centroid, group_centroid)
                    if similarity < settings.speaker_reporting_merge_threshold:
                        continue

                    total_weight = group_weight + weight
                    merged_groups[index] = (
                        ((group_centroid * group_weight) + (centroid * weight)) / total_weight,
                        total_weight,
                    )
                    merged = True
                    break

                if not merged:
                    merged_groups.append((centroid, weight))

            return len(merged_groups) or 1

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

    def _recent_label(self, segment_start: float | None) -> str | None:
        if self._last_assignment is None:
            return None

        label, last_end = self._last_assignment
        if segment_start is None or last_end is None:
            return label

        if segment_start - last_end <= settings.speaker_temporal_hold_seconds:
            return label
        return None

    def _remember_assignment(
        self,
        label: str,
        embedding: np.ndarray,
        segment_start: float | None,
        segment_end: float | None,
        *,
        remember_embedding: bool = True,
    ) -> None:
        if remember_embedding and float(np.linalg.norm(embedding)) > 0.0:
            history = self.embedding_history_by_label.get(label)
            if history is None:
                history = deque(maxlen=settings.embedding_window_size)
                self.embedding_history_by_label[label] = history
            history.append(embedding)
        self.labels.append(label)
        self.label_assignment_counts[label] = self.label_assignment_counts.get(label, 0) + 1
        duration = 0.0
        if segment_start is not None and segment_end is not None:
            duration = max(0.0, segment_end - segment_start)
        self.label_total_durations[label] = self.label_total_durations.get(label, 0.0) + duration
        self._last_assignment = (label, segment_end)

    def _has_any_embedding_locked(self) -> bool:
        return any(len(history) > 0 for history in self.embedding_history_by_label.values())

    def _stable_labels_locked(self) -> list[str]:
        return sorted(
            (
                label
                for label in self.unique_speakers
                if (
                    self.label_assignment_counts.get(label, 0) >= settings.speaker_min_stable_segments
                    or self.label_total_durations.get(label, 0.0)
                    >= settings.speaker_min_stable_seconds
                )
            ),
            key=lambda label: (
                self.label_total_durations.get(label, 0.0),
                self.label_assignment_counts.get(label, 0),
            ),
            reverse=True,
        )
