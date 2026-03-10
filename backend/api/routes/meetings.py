from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any, Literal, Optional, AsyncGenerator
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator
import aiofiles
from pathlib import Path

from backend.config import settings

from backend.core.pipeline import MeetingPipeline
from backend.storage.repositories.meetings import MeetingsRepository
from backend.storage.repositories.speakers import SpeakersRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/meetings", tags=["meetings"])
meetings_repo = MeetingsRepository()
speakers_repo = SpeakersRepository()
active_pipelines: dict[str, MeetingPipeline] = {}
_pipeline_start_tasks: dict[str, asyncio.Task] = {}

MeetingStatus = Literal['active', 'recording', 'completed', 'failed']


class RenameSpeakerRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator('name')
    @classmethod
    def normalize_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError('name cannot be empty')
        return cleaned


class CreateMeetingRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)

    @field_validator('title')
    @classmethod
    def normalize_title(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError('title cannot be empty')
        return cleaned


class UpdateMeetingRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    status: Optional[MeetingStatus] = None
    metadata: Optional[str] = Field(default=None, max_length=4000)

    @field_validator('title')
    @classmethod
    def normalize_optional_title(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError('title cannot be empty')
        return cleaned


async def _start_pipeline(meeting_id: str, pipeline: MeetingPipeline) -> None:
    try:
        await pipeline.start()
    except asyncio.CancelledError:
        if pipeline.running:
            await pipeline.stop()
        active_pipelines.pop(meeting_id, None)
        raise
    except Exception as exc:
        logger.exception('Pipeline start failed for %s: %s', meeting_id, exc)
        active_pipelines.pop(meeting_id, None)
        await meetings_repo.update(meeting_id, status='failed')
    finally:
        _pipeline_start_tasks.pop(meeting_id, None)


@router.post('/')
async def create_meeting(body: CreateMeetingRequest) -> dict[str, Any]:
    return await meetings_repo.create(body.title)


@router.get('/')
async def list_meetings() -> list[dict[str, Any]]:
    return await meetings_repo.list_all()


@router.get('/{meeting_id}')
async def get_meeting(meeting_id: UUID) -> dict[str, Any]:
    meeting = await meetings_repo.get(str(meeting_id))
    if meeting is None:
        raise HTTPException(status_code=404, detail='Meeting not found')
    return meeting


@router.get('/{meeting_id}/audio')
async def get_meeting_audio(meeting_id: UUID) -> FileResponse:
    meeting_id_str = str(meeting_id)
    meeting = await meetings_repo.get(meeting_id_str)
    if meeting is None:
        raise HTTPException(status_code=404, detail='Meeting not found')
        
    audio_path = Path(settings.db_path).parent / f"{meeting_id_str}.wav"
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail='Audio not found for this meeting')
        
    async def audio_generator() -> AsyncGenerator[bytes, None]:
        async with aiofiles.open(audio_path, 'rb') as f:
            while True:
                chunk = await f.read(65536)
                if not chunk:
                    # If the meeting is still recording, we shouldn't necessarily close the stream,
                    # but for HTTP GET, standard behavior is to end when EOF is hit. 
                    # The client audio player will just request range again if needed.
                    break
                yield chunk

    return StreamingResponse(
        audio_generator(),
        media_type="audio/wav",
        headers={"Accept-Ranges": "bytes"}
    )


@router.patch('/{meeting_id}')
async def update_meeting(meeting_id: UUID, body: UpdateMeetingRequest) -> dict[str, Any]:
    meeting_id_str = str(meeting_id)
    meeting = await meetings_repo.get(meeting_id_str)
    if meeting is None:
        raise HTTPException(status_code=404, detail='Meeting not found')

    updates = body.model_dump(exclude_none=True)
    return await meetings_repo.update(meeting_id_str, **updates)


@router.delete('/{meeting_id}')
async def delete_meeting(meeting_id: UUID) -> dict[str, bool]:
    meeting_id_str = str(meeting_id)

    pipeline = active_pipelines.pop(meeting_id_str, None)
    if pipeline is not None:
        await pipeline.stop()

    task = _pipeline_start_tasks.pop(meeting_id_str, None)
    if task is not None and not task.done():
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    removed = await meetings_repo.delete(meeting_id_str)
    if not removed:
        raise HTTPException(status_code=404, detail='Meeting not found')
    return {'deleted': True}


@router.post('/{meeting_id}/start')
async def start_recording(meeting_id: UUID) -> dict[str, str]:
    meeting_id_str = str(meeting_id)
    meeting = await meetings_repo.get(meeting_id_str)
    if meeting is None:
        raise HTTPException(status_code=404, detail='Meeting not found')

    if meeting_id_str in active_pipelines:
        return {'status': 'recording', 'meeting_id': meeting_id_str}

    pipeline = MeetingPipeline(meeting_id_str)
    active_pipelines[meeting_id_str] = pipeline

    start_task = asyncio.create_task(_start_pipeline(meeting_id_str, pipeline))
    _pipeline_start_tasks[meeting_id_str] = start_task

    await meetings_repo.update(meeting_id_str, status='recording')
    return {'status': 'recording', 'meeting_id': meeting_id_str}


@router.post('/{meeting_id}/stop')
async def stop_recording(meeting_id: UUID) -> dict[str, str]:
    meeting_id_str = str(meeting_id)
    meeting = await meetings_repo.get(meeting_id_str)
    if meeting is None:
        raise HTTPException(status_code=404, detail='Meeting not found')

    task = _pipeline_start_tasks.pop(meeting_id_str, None)
    if task is not None and not task.done():
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    pipeline = active_pipelines.pop(meeting_id_str, None)
    if pipeline is not None:
        await pipeline.stop()
        
    final_duration = (meeting.get('duration_s') or 0.0)
    if pipeline is not None:
        final_duration += max(0.0, time.time() - pipeline.start_epoch)

    await meetings_repo.end_meeting(meeting_id_str, final_duration)
    return {'status': 'completed', 'meeting_id': meeting_id_str}


@router.patch('/{meeting_id}/speakers/{label:path}')
async def rename_speaker(meeting_id: UUID, label: str, body: RenameSpeakerRequest) -> dict[str, Any]:
    meeting_id_str = str(meeting_id)
    
    # Verify the meeting exists
    meeting = await meetings_repo.get(meeting_id_str)
    if meeting is None:
        raise HTTPException(status_code=404, detail='Meeting not found')
        
    try:
        updated = await speakers_repo.rename_by_label(meeting_id_str, label, body.name)
        return updated
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
