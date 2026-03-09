from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Word:
    start: float
    end: float
    word: str
    probability: float


@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: list[Word]
    avg_logprob: float

    @property
    def confidence(self) -> float:
        return min(1.0, max(0.0, (self.avg_logprob + 1.0)))
