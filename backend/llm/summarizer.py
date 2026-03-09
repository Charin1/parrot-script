from __future__ import annotations

import asyncio

import httpx

from backend.config import settings
from backend.core.exceptions import OllamaUnavailableError
from backend.llm.chunker import chunk_transcript, estimate_tokens
from backend.llm.prompts import (
    COMBINE_SUMMARIES_PROMPT,
    MEETING_SUMMARY_PROMPT,
    PARTIAL_SUMMARY_PROMPT,
)
from backend.storage.repositories.summaries import SummariesRepository


class MeetingSummarizer:
    def __init__(self):
        self.repo = SummariesRepository()

    async def summarize(self, transcript: str, meeting_id: str) -> dict:
        transcript = transcript.strip()
        if not transcript:
            raise ValueError("Transcript is empty")

        if estimate_tokens(transcript) > settings.summary_chunk_size:
            chunks = chunk_transcript(transcript, max_tokens=settings.summary_chunk_size)
            partial_summaries = await asyncio.gather(
                *[
                    self._call_ollama(PARTIAL_SUMMARY_PROMPT.format(transcript=chunk))
                    for chunk in chunks
                ]
            )
            combined = "\n\n---\n\n".join(partial_summaries)
            result = await self._call_ollama(
                COMBINE_SUMMARIES_PROMPT.format(summaries=combined)
            )
        else:
            result = await self._call_ollama(
                MEETING_SUMMARY_PROMPT.format(transcript=transcript)
            )

        existing = await self.repo.get_by_meeting(meeting_id)
        if existing:
            saved = await self.repo.update(
                existing["id"],
                content=result,
                model_used=settings.ollama_model,
            )
        else:
            saved = await self.repo.insert(
                meeting_id=meeting_id,
                content=result,
                model=settings.ollama_model,
            )

        return {
            "content": result,
            "meeting_id": meeting_id,
            "summary_id": saved["id"],
        }

    async def _call_ollama(self, prompt: str) -> str:
        payload = {
            "model": settings.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": settings.summary_max_tokens},
        }
        url = f"{settings.ollama_base_url.rstrip('/')}/api/generate"

        try:
            async with httpx.AsyncClient(timeout=settings.ollama_timeout) as client:
                response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OllamaUnavailableError("Could not connect to Ollama") from exc

        content = data.get("response")
        if not isinstance(content, str):
            raise OllamaUnavailableError("Unexpected Ollama response format")

        return content.strip()
