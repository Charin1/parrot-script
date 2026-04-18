from __future__ import annotations

import asyncio
import json
from typing import Optional, Callable, Awaitable

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

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
import logging

logger = logging.getLogger(__name__)


class MeetingSummarizer:
    def __init__(self):
        self.repo = SummariesRepository()
        self.segments_repo = SegmentsRepository()

    async def summarize(
        self, 
        transcript: str, 
        meeting_id: str, 
        prompt_template: Optional[str] = None,
        on_progress: Optional[Callable[[int, int], Awaitable[None]]] = None
    ) -> dict:
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
            logger.info(f"Summarizing meeting {meeting_id} in {len(chunks)} chunks (SEQUENTIAL MODE)")
            
            if on_progress:
                await on_progress(0, len(chunks))

            partial_summaries = []
            for i, chunk in enumerate(chunks):
                logger.info(f"Processing chunk {i+1}/{len(chunks)} for meeting {meeting_id}...")
                chunk_result = await self._call_ollama(PARTIAL_SUMMARY_PROMPT.format(transcript=prompt_prefix + chunk))
                partial_summaries.append(chunk_result)
                if on_progress:
                    await on_progress(i + 1, len(chunks))
            
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
            logger.info(f"Successfully generated combined summary for meeting {meeting_id}")
        else:
            final_prompt = prompt_template if prompt_template else MEETING_SUMMARY_PROMPT
            
            try:
                formatted = final_prompt.format(transcript=prompt_prefix + transcript)
            except KeyError:
                formatted = final_prompt + "\n\nTRANSCRIPT:\n" + prompt_prefix + transcript

            if on_progress:
                # Ensure the UI has a progress signal even for single-chunk meetings.
                await on_progress(0, 1)

            result = await self._call_ollama(formatted)
            logger.info(f"Successfully generated summary for meeting {meeting_id} (single chunk)")

            if on_progress:
                await on_progress(1, 1)


        # Clean result of markdown blocks if they exists
        clean_result = result.strip()
        if clean_result.startswith("```"):
            # Strip lines starting with ``` (and potential json tag)
            lines = clean_result.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].startswith("```"):
                lines = lines[:-1]
            clean_result = "\n".join(lines).strip()

        # Try to parse the result as JSON
        try:
            parsed = json.loads(clean_result)
            summary_text = parsed.get("summary")
            # Store arrays as JSON strings
            action_items_str = json.dumps(parsed.get("action_items", []))
            decisions_str = json.dumps(parsed.get("decisions", []))
            
            # If everything is empty, fallback to raw text
            if not summary_text and not parsed.get("action_items") and not parsed.get("decisions"):
                logger.warning("LLM returned valid JSON but all fields were empty. Falling back to raw text.")
                summary_text = result
                action_items_str = "[]"
                decisions_str = "[]"
        except (json.JSONDecodeError, AttributeError, ValueError) as exc:
            logger.warning("JSON parsing failed (falling back to raw text): %r", exc)
            summary_text = result
            action_items_str = "[]"
            decisions_str = "[]"

        existing = await self.repo.get_by_meeting(meeting_id)
        if existing:
            saved = await self.repo.update(
                existing["id"],
                content=result,
                model_used=settings.ollama_model,
                summary=summary_text,
                action_items=action_items_str,
                decisions=decisions_str
            )
        else:
            saved = await self.repo.insert(
                meeting_id=meeting_id,
                content=result,
                model=settings.ollama_model,
                summary=summary_text,
                action_items=action_items_str,
                decisions=decisions_str
            )

        return {
            "content": result,
            "meeting_id": meeting_id,
            "summary_id": saved["id"],
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(OllamaUnavailableError),
        reraise=True
    )
    async def _call_ollama(self, prompt: str) -> str:
        payload = {
            "model": settings.ollama_model,
            "prompt": prompt,
            "stream": False,
            # Removing strict 'format: json' as it can cause Ollama to hang or disconnect 
            # on some models/versions when under high system load. 
            # Our prompt and clean_result logic handles the extraction.
            "options": {"num_predict": settings.summary_max_tokens},
        }
        url = f"{settings.ollama_base_url.rstrip('/')}/api/generate"

        try:
            # Using a fresh client per request without connection pooling for these long AI calls
            async with httpx.AsyncClient(timeout=settings.ollama_timeout, limits=httpx.Limits(max_keepalive_connections=0)) as client:
                response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # Using %r to get the full class name and details
            logger.warning("LLM request failed (will retry): %r", exc)
            raise OllamaUnavailableError(f"Could not connect to Ollama: {exc}") from exc

        content = data.get("response")
        if not content or not isinstance(content, str):
            logger.warning("Unexpected or empty LLM response (will retry)")
            raise OllamaUnavailableError("Unexpected or empty Ollama response")

        return content.strip()
