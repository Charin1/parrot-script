from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.exceptions import OllamaUnavailableError
from backend.llm.summarizer import MeetingSummarizer
from backend.storage.repositories.meetings import MeetingsRepository
from backend.storage.repositories.segments import SegmentsRepository
from backend.storage.repositories.summaries import SummariesRepository
from backend.storage.vector_store import VectorStore

router = APIRouter(prefix='/api/meetings', tags=['summaries'])
segments_repo = SegmentsRepository()
meetings_repo = MeetingsRepository()
summaries_repo = SummariesRepository()
summarizer = MeetingSummarizer()
_vector_store: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store


async def _require_meeting(meeting_id: str) -> None:
    if await meetings_repo.get(meeting_id) is None:
        raise HTTPException(status_code=404, detail='Meeting not found')


@router.get('/{meeting_id}/summary')
async def get_or_create_summary(meeting_id: UUID) -> dict:
    meeting_id_str = str(meeting_id)
    await _require_meeting(meeting_id_str)

    existing = await summaries_repo.get_by_meeting(meeting_id_str)
    if existing:
        return existing

    transcript = await segments_repo.get_full_text(meeting_id_str)
    if not transcript:
        return {
            "id": "",
            "meeting_id": meeting_id_str,
            "content": "",
            "created_at": "",
            "model_used": None
        }

    try:
        result = await summarizer.summarize(transcript=transcript, meeting_id=meeting_id_str, prompt_template=None)
    except OllamaUnavailableError as exc:
        raise HTTPException(status_code=503, detail='Ollama unavailable') from exc

    await get_vector_store().add_meeting(meeting_id_str, transcript, result['content'])
    created = await summaries_repo.get_by_meeting(meeting_id_str)
    if created is None:
        raise HTTPException(status_code=500, detail='Summary generation failed')
    return created


class SummarizeRequest(BaseModel):
    prompt_template: Optional[str] = None

@router.post('/{meeting_id}/summarize')
async def force_summarize(meeting_id: UUID, body: Optional[SummarizeRequest] = None) -> dict:
    meeting_id_str = str(meeting_id)
    await _require_meeting(meeting_id_str)

    transcript = await segments_repo.get_full_text(meeting_id_str)
    if not transcript:
        raise HTTPException(status_code=400, detail='Transcript is empty')

    prompt_template = body.prompt_template if body else None

    try:
        result = await summarizer.summarize(transcript=transcript, meeting_id=meeting_id_str, prompt_template=prompt_template)
    except OllamaUnavailableError as exc:
        raise HTTPException(status_code=503, detail='Ollama unavailable') from exc

    await get_vector_store().add_meeting(meeting_id_str, transcript, result['content'])
    summary = await summaries_repo.get_by_meeting(meeting_id_str)
    if summary is None:
        raise HTTPException(status_code=500, detail='Summary generation failed')
    return summary


from fastapi.responses import Response, JSONResponse
from fastapi import Query
from backend.core.export import generate_summary_pdf

@router.get('/{meeting_id}/summary/download')
async def download_summary(
    meeting_id: UUID,
    format: str = Query('json', pattern='^(json|pdf)$')
) -> Response:
    meeting_id_str = str(meeting_id)
    meeting = await meetings_repo.get(meeting_id_str)
    if meeting is None:
        raise HTTPException(status_code=404, detail='Meeting not found')
        
    summary = await summaries_repo.get_by_meeting(meeting_id_str)
    if summary is None or not summary.get("content"):
        raise HTTPException(status_code=404, detail='No summary found for this meeting')
        
    if format == 'pdf':
        pdf_bytes = generate_summary_pdf(meeting.get("title", "Untitled"), summary["content"])
        return Response(
            content=bytes(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="summary_{meeting_id_str}.pdf"'}
        )
    else:
        return JSONResponse(
            content=summary,
            headers={"Content-Disposition": f'attachment; filename="summary_{meeting_id_str}.json"'}
        )
