from __future__ import annotations

from typing import Optional, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, BackgroundTasks
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from backend.api.limiter import limiter

from backend.core.exceptions import OllamaUnavailableError
from backend.core.export import generate_summary_pdf
from backend.llm.summarizer import MeetingSummarizer
from backend.storage.repositories.meetings import MeetingsRepository
from backend.storage.repositories.segments import SegmentsRepository
from backend.storage.repositories.summaries import SummariesRepository
from backend.storage.vector_store import VectorStore
from backend.api.websocket import manager
import logging

logger = logging.getLogger(__name__)

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


async def background_summarize(meeting_id: str, transcript: str, prompt_template: Optional[str] = None) -> None:
    """Internal task to run summarization in the background and notify clients via WS."""
    async def progress_callback(current: int, total: int):
        await manager.broadcast(meeting_id, {
            "type": "summary_progress",
            "data": {
                "meeting_id": meeting_id,
                "current": current,
                "total": total
            }
        })

    try:
        logger.info("Background summarization started for %s (chars=%s)", meeting_id, len(transcript))
        result = await summarizer.summarize(
            transcript=transcript, 
            meeting_id=meeting_id, 
            prompt_template=prompt_template,
            on_progress=progress_callback
        )
        
        # Add to vector store
        await get_vector_store().add_meeting(meeting_id, transcript, result['content'])
        
        # Notify completion
        summary = await summaries_repo.get_by_meeting(meeting_id)
        if summary:
            logger.info("Background summarization completed for %s", meeting_id)
            await manager.broadcast(meeting_id, {
                "type": "summary_completed",
                "data": summary
            })
    except Exception as exc:
        logger.exception(f"Background summarization failed for {meeting_id}: {exc}")
        await manager.broadcast(meeting_id, {
            "type": "summary_failed",
            "data": {
                "meeting_id": meeting_id,
                "error": str(exc)
            }
        })


@router.get('/{meeting_id}/summary')
@limiter.limit("20/minute")
async def get_or_create_summary(request: Request, meeting_id: UUID, background_tasks: BackgroundTasks) -> Any:
    meeting_id_str = str(meeting_id)
    logger.info(f"Summary request for meeting {meeting_id_str}")
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

    background_tasks.add_task(background_summarize, meeting_id_str, transcript)
    return JSONResponse(
        status_code=202,
        content={"status": "processing", "message": "Summary generation started"}
    )


class SummarizeRequest(BaseModel):
    prompt_template: Optional[str] = None

@router.post('/{meeting_id}/summarize')
@limiter.limit("10/minute")
async def force_summarize(request: Request, meeting_id: UUID, background_tasks: BackgroundTasks, body: Optional[SummarizeRequest] = None) -> Any:
    meeting_id_str = str(meeting_id)
    logger.info(f"Force summarize request for meeting {meeting_id_str}")
    await _require_meeting(meeting_id_str)

    transcript = await segments_repo.get_full_text(meeting_id_str)
    if not transcript:
        raise HTTPException(status_code=400, detail='Transcript is empty')

    prompt_template = body.prompt_template if body else None

    background_tasks.add_task(background_summarize, meeting_id_str, transcript, prompt_template)
    return JSONResponse(
        status_code=202,
        content={"status": "processing", "message": "Summarization started"}
    )




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
