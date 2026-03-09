from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from backend.storage.repositories.meetings import MeetingsRepository
from backend.storage.repositories.segments import SegmentsRepository

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

from fastapi.responses import Response, JSONResponse
import json
from backend.core.export import generate_transcript_pdf

@router.get('/{meeting_id}/transcript/download')
async def download_transcript(
    meeting_id: UUID,
    format: str = Query('json', regex='^(json|pdf)$')
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
