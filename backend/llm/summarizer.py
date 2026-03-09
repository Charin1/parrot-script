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
from backend.storage.repositories.segments import SegmentsRepository
from backend.storage.repositories.summaries import SummariesRepository


class MeetingSummarizer:
    def __init__(self):
        self.repo = SummariesRepository()
        self.segments_repo = SegmentsRepository()

    async def summarize(self, transcript: str, meeting_id: str, prompt_template: Optional[str] = None) -> dict:
        transcript = transcript.strip()
        if not transcript:
            raise ValueError("Transcript is empty")

        # Fetch bookmarked lines to emphasize in summary
        segments = await self.segments_repo.get_by_meeting(meeting_id)
        bookmarked = [s for s in segments if s.get("is_bookmarked")]
        
        prompt_prefix = ""
        if bookmarked:
            prompt_prefix = "CRITICAL INSTRUCTION: The user has specifically bookmarked the following key moments. You MUST explicitly highlight these points or action items in your summary:\n"
            for b in bookmarked:
                speaker = b.get("display_name", b.get("speaker", "Unknown"))
                prompt_prefix += f"- {speaker}: \"{b['text']}\"\n"
            prompt_prefix += "\n\n"

        if estimate_tokens(transcript) > settings.summary_chunk_size:
            chunks = chunk_transcript(transcript, max_tokens=settings.summary_chunk_size)
            partial_summaries = await asyncio.gather(
                *[
                    self._call_ollama(PARTIAL_SUMMARY_PROMPT.format(transcript=prompt_prefix + chunk))
                    for chunk in chunks
                ]
            )
            combined = "\n\n---\n\n".join(partial_summaries)
            final_prompt = prompt_template if prompt_template else COMBINE_SUMMARIES_PROMPT
            
            # If they provided a custom prompt, we need to ensure we format it correctly.
            # We will try both '{transcript}' and '{summaries}' based on what they wrote.
            try:
                formatted = final_prompt.format(summaries=prompt_prefix + combined, transcript=prompt_prefix + combined)
            except KeyError:
                # If they didn't include the exact variables, just append it
                formatted = final_prompt + "\n\nTRANSCRIPT/SUMMARIES:\n" + prompt_prefix + combined

            result = await self._call_ollama(formatted)
        else:
            final_prompt = prompt_template if prompt_template else MEETING_SUMMARY_PROMPT
            
            try:
                formatted = final_prompt.format(transcript=prompt_prefix + transcript)
            except KeyError:
                formatted = final_prompt + "\n\nTRANSCRIPT:\n" + prompt_prefix + transcript

            result = await self._call_ollama(formatted)

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
