from __future__ import annotations

import asyncio
import logging
import time

import numpy as np

from backend.config import settings
from backend.transcription.models import Segment, Word

logger = logging.getLogger(__name__)


class WhisperTranscriber:
    def __init__(self):
        self.model = None

    def load_model(self) -> None:
        if self.model is not None:
            return

        from faster_whisper import WhisperModel

        started = time.perf_counter()
        self.model = WhisperModel(
            model_size_or_path=settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
        elapsed = time.perf_counter() - started
        logger.info("Whisper model %s loaded in %.2fs", settings.whisper_model, elapsed)

    def transcribe(self, audio_bytes: bytes) -> list[Segment]:
        if not audio_bytes:
            return []

        if self.model is None:
            self.load_model()

        audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        if audio.size == 0:
            return []

        segments_iter, _ = self.model.transcribe(
            audio,
            beam_size=settings.whisper_beam_size,
            word_timestamps=True,
            vad_filter=True,
            language="en",
        )

        converted: list[Segment] = []
        for seg in segments_iter:
            words: list[Word] = []
            for word in getattr(seg, "words", []) or []:
                words.append(
                    Word(
                        start=float(getattr(word, "start", 0.0) or 0.0),
                        end=float(getattr(word, "end", 0.0) or 0.0),
                        word=str(getattr(word, "word", "") or "").strip(),
                        probability=float(getattr(word, "probability", 0.0) or 0.0),
                    )
                )

            converted.append(
                Segment(
                    start=float(getattr(seg, "start", 0.0) or 0.0),
                    end=float(getattr(seg, "end", 0.0) or 0.0),
                    text=str(getattr(seg, "text", "") or "").strip(),
                    words=words,
                    avg_logprob=float(getattr(seg, "avg_logprob", -1.0) or -1.0),
                )
            )

        return converted

    async def transcribe_async(self, audio_bytes: bytes) -> list[Segment]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.transcribe, audio_bytes)
