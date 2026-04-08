from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from backend.core.export import generate_transcript_pdf
from backend.storage.repositories.meetings import MeetingsRepository
from backend.storage.repositories.segments import SegmentsRepository
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/meetings', tags=['transcripts'])
segments_repo = SegmentsRepository()
meetings_repo = MeetingsRepository()


@router.get('/{meeting_id}/transcript')
async def get_transcript(
    meeting_id: UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    meeting_id_str = str(meeting_id)
    meeting = await meetings_repo.get(meeting_id_str)
    if meeting is None:
        raise HTTPException(status_code=404, detail='Meeting not found')

    start = (page - 1) * limit
    total = await segments_repo.count_by_meeting(meeting_id_str)
    segments = await segments_repo.get_by_meeting_paginated(
        meeting_id=meeting_id_str,
        limit=limit,
        offset=start,
    )
    
    return {
        'items': segments,
        'page': page,
        'limit': limit,
        'total': total,
    }



@router.get('/{meeting_id}/transcript/download')
async def download_transcript(
    meeting_id: UUID,
    format: str = Query('json', pattern='^(json|pdf)$')
) -> Response:
    meeting_id_str = str(meeting_id)
    meeting = await meetings_repo.get(meeting_id_str)
    if meeting is None:
        raise HTTPException(status_code=404, detail='Meeting not found')
        
    segments = await segments_repo.get_by_meeting(meeting_id_str)
    
    if format == 'pdf':
        pdf_bytes = generate_transcript_pdf(meeting.get("title", "Untitled"), segments)
        return Response(
            content=bytes(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="transcript_{meeting_id_str}.pdf"'}
        )
    else:
        return JSONResponse(
            content=segments,
            headers={"Content-Disposition": f'attachment; filename="transcript_{meeting_id_str}.json"'}
        )


class BookmarkToggleRequest(BaseModel):
    is_bookmarked: bool

class UpdateSegmentTextRequest(BaseModel):
    text: str


@router.patch('/{meeting_id}/segments/{segment_id}/bookmark')
async def toggle_segment_bookmark(
    meeting_id: UUID, 
    segment_id: str, 
    body: BookmarkToggleRequest
) -> dict[str, Any]:
    meeting_id_str = str(meeting_id)
    # Fast verify meeting
    meeting = await meetings_repo.get(meeting_id_str)
    if meeting is None:
        raise HTTPException(status_code=404, detail='Meeting not found')
        
    updated = await segments_repo.toggle_bookmark(segment_id, body.is_bookmarked)
    if not updated:
        raise HTTPException(status_code=404, detail='Transcript segment not found')
        
    return {"id": segment_id, "is_bookmarked": body.is_bookmarked}

@router.patch('/{meeting_id}/segments/{segment_id}/text')
async def update_segment_text(
    meeting_id: UUID, 
    segment_id: str, 
    body: UpdateSegmentTextRequest
) -> dict[str, Any]:
    meeting_id_str = str(meeting_id)
    # Fast verify meeting
    meeting = await meetings_repo.get(meeting_id_str)
    if meeting is None:
        raise HTTPException(status_code=404, detail='Meeting not found')
        
    updated = await segments_repo.update_text(segment_id, body.text)
    if not updated:
        raise HTTPException(status_code=404, detail='Transcript segment not found')
        
    return {"id": segment_id, "text": body.text}
