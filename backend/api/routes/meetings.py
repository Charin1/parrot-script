from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import Any, Literal, Optional, AsyncGenerator
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse

from pydantic import BaseModel, Field, field_validator
import aiofiles
from pathlib import Path

from backend.assistants import (
    AssistantJoinRequest,
    LocalMeetingAssistantProvider,
    infer_source_platform,
    resolve_capture_mode,
    serialize_provider_metadata,
)
from backend.audio.sources import LocalAudioSource
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
assistant_provider = LocalMeetingAssistantProvider()

MeetingStatus = Literal['active', 'recording', 'completed', 'failed']
CaptureMode = Literal['private', 'assistant']
SourcePlatform = Literal['local', 'google_meet', 'zoom', 'teams', 'other']
AssistantJoinStatus = Literal['not_requested', 'pending', 'joined', 'unsupported', 'failed']
ConsentStatus = Literal['not_needed', 'required', 'pending', 'granted', 'denied', 'unknown']


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
    capture_mode: Optional[CaptureMode] = None
    ghost_mode: Optional[bool] = None
    source_platform: Optional[SourcePlatform] = None
    meeting_url: Optional[str] = Field(default=None, max_length=2000)
    assistant_join_status: Optional[AssistantJoinStatus] = None
    assistant_visible_name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    consent_status: Optional[ConsentStatus] = None
    provider_session_id: Optional[str] = Field(default=None, max_length=200)
    provider_metadata: Optional[str] = Field(default=None, max_length=4000)

    @field_validator('title')
    @classmethod
    def normalize_optional_title(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError('title cannot be empty')
        return cleaned

    @field_validator('meeting_url')
    @classmethod
    def normalize_optional_meeting_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator('assistant_visible_name')
    @classmethod
    def normalize_optional_assistant_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError('assistant_visible_name cannot be empty')
        return cleaned


class StartMeetingRequest(BaseModel):
    capture_mode: Optional[CaptureMode] = None
    ghost_mode: Optional[bool] = None
    meeting_url: Optional[str] = Field(default=None, max_length=2000)
    source_platform: Optional[SourcePlatform] = None
    assistant_visible_name: Optional[str] = Field(default=None, min_length=1, max_length=120)

    @field_validator('meeting_url')
    @classmethod
    def normalize_meeting_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator('assistant_visible_name')
    @classmethod
    def normalize_assistant_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError('assistant_visible_name cannot be empty')
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
async def list_meetings(
    q: Optional[str] = Query(default=None, description='Keyword search on title'),
    status: Optional[str] = Query(default=None, description='Filter by status: active, recording, completed, failed'),
    from_date: Optional[str] = Query(default=None, description='ISO datetime lower bound for created_at'),
    to_date: Optional[str] = Query(default=None, description='ISO datetime upper bound for created_at'),
) -> list[dict[str, Any]]:
    return await meetings_repo.list_all(q=q, status=status, from_date=from_date, to_date=to_date)


@router.get('/{meeting_id}')
async def get_meeting(meeting_id: UUID) -> dict[str, Any]:
    meeting = await meetings_repo.get(str(meeting_id))
    if meeting is None:
        raise HTTPException(status_code=404, detail='Meeting not found')
    return meeting


@router.get('/{meeting_id}/audio')
async def get_meeting_audio(meeting_id: UUID, request: Request) -> Response:
    meeting_id_str = str(meeting_id)
    meeting = await meetings_repo.get(meeting_id_str)
    if meeting is None:
        raise HTTPException(status_code=404, detail='Meeting not found')

    audio_path = Path(settings.db_path).parent / f"{meeting_id_str}.wav"
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail='Audio not found for this meeting')

    file_size = audio_path.stat().st_size
    range_header = request.headers.get('range')

    if range_header:
        # Parse "bytes=start-end"
        try:
            range_val = range_header.strip().replace('bytes=', '')
            range_start_str, range_end_str = range_val.split('-')
            range_start = int(range_start_str) if range_start_str else 0
            range_end = int(range_end_str) if range_end_str else file_size - 1
        except (ValueError, AttributeError):
            range_start = 0
            range_end = file_size - 1

        range_start = max(0, range_start)
        range_end = min(range_end, file_size - 1)
        content_length = range_end - range_start + 1

        async def range_generator() -> AsyncGenerator[bytes, None]:
            async with aiofiles.open(audio_path, 'rb') as f:
                await f.seek(range_start)
                remaining = content_length
                while remaining > 0:
                    chunk = await f.read(min(65536, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return StreamingResponse(
            range_generator(),
            status_code=206,
            media_type='audio/wav',
            headers={
                'Content-Range': f'bytes {range_start}-{range_end}/{file_size}',
                'Content-Length': str(content_length),
                'Accept-Ranges': 'bytes',
                'Cache-Control': 'no-store',
            },
        )

    # No Range header: return full file
    async def full_generator() -> AsyncGenerator[bytes, None]:
        async with aiofiles.open(audio_path, 'rb') as f:
            while True:
                chunk = await f.read(65536)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(
        full_generator(),
        media_type='audio/wav',
        headers={
            'Content-Length': str(file_size),
            'Accept-Ranges': 'bytes',
            'Cache-Control': 'no-store',
        },
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
    logger.info("Received request to delete meeting: %s", meeting_id_str)

    pipeline = active_pipelines.pop(meeting_id_str, None)
    if pipeline is not None:
        logger.info("Stopping active pipeline for meeting: %s", meeting_id_str)
        await pipeline.stop()

    task = _pipeline_start_tasks.pop(meeting_id_str, None)
    if task is not None and not task.done():
        logger.info("Cancelling pipeline start task for meeting: %s", meeting_id_str)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    removed = await meetings_repo.delete(meeting_id_str)
    if not removed:
        logger.warning("Delete failed: Meeting not found: %s", meeting_id_str)
        raise HTTPException(status_code=404, detail='Meeting not found')
    
    logger.info("Meeting deleted successfully: %s", meeting_id_str)
    return {'deleted': True}



@router.post('/{meeting_id}/start')
async def start_recording(meeting_id: UUID, body: Optional[StartMeetingRequest] = None) -> dict[str, Any]:
    meeting_id_str = str(meeting_id)
    meeting = await meetings_repo.get(meeting_id_str)
    if meeting is None:
        raise HTTPException(status_code=404, detail='Meeting not found')

    if meeting_id_str in active_pipelines:
        return {'status': 'recording', 'meeting_id': meeting_id_str, 'message': None}

    body = body or StartMeetingRequest()

    capture_mode, ghost_mode = resolve_capture_mode(body.capture_mode, body.ghost_mode)
    assistant_visible_name = (
        body.assistant_visible_name
        or meeting.get('assistant_visible_name')
        or 'Parrot Script Assistant'
    )
    meeting_url = body.meeting_url if body.meeting_url is not None else meeting.get('meeting_url')
    source_platform = body.source_platform or infer_source_platform(meeting_url)

    if capture_mode == 'assistant':
        if not meeting_url:
            raise HTTPException(
                status_code=422,
                detail='Assistant mode currently requires a meeting URL.',
            )

        session = await assistant_provider.request_join(
            AssistantJoinRequest(
                meeting_id=meeting_id_str,
                title=meeting['title'],
                meeting_url=meeting_url,
                source_platform=source_platform or 'other',
                assistant_visible_name=assistant_visible_name,
            )
        )
        if session.join_status == 'failed':
            await meetings_repo.update(
                meeting_id_str,
                capture_mode='assistant',
                ghost_mode=False,
                source_platform=session.source_platform,
                meeting_url=meeting_url,
                assistant_join_status=session.join_status,
                assistant_visible_name=assistant_visible_name,
                consent_status=session.consent_status,
                provider_session_id=session.provider_session_id,
                provider_metadata=serialize_provider_metadata(session.provider_metadata),
                status='failed',
            )
            raise HTTPException(
                status_code=503,
                detail=session.message or 'Assistant mode could not open the meeting link.',
            )

        pipeline = MeetingPipeline(meeting_id_str, capture_source=LocalAudioSource(meeting_id_str))
        active_pipelines[meeting_id_str] = pipeline
        start_task = asyncio.create_task(_start_pipeline(meeting_id_str, pipeline))
        _pipeline_start_tasks[meeting_id_str] = start_task

        await meetings_repo.update(
            meeting_id_str,
            capture_mode='assistant',
            ghost_mode=False,
            source_platform=session.source_platform,
            meeting_url=meeting_url,
            assistant_join_status=session.join_status,
            assistant_visible_name=assistant_visible_name,
            consent_status=session.consent_status,
            provider_session_id=session.provider_session_id,
            provider_metadata=serialize_provider_metadata(session.provider_metadata),
            status='recording',
        )
        return {
            'status': 'recording',
            'meeting_id': meeting_id_str,
            'message': session.message,
        }

    pipeline = MeetingPipeline(meeting_id_str, capture_source=LocalAudioSource(meeting_id_str))
    active_pipelines[meeting_id_str] = pipeline

    start_task = asyncio.create_task(_start_pipeline(meeting_id_str, pipeline))
    _pipeline_start_tasks[meeting_id_str] = start_task

    await meetings_repo.update(
        meeting_id_str,
        status='recording',
        capture_mode='private',
        ghost_mode=ghost_mode,
        source_platform='local',
        meeting_url=meeting_url,
        assistant_join_status='not_requested',
        assistant_visible_name=assistant_visible_name,
        consent_status='not_needed',
        provider_session_id=None,
        provider_metadata=None,
    )
    return {'status': 'recording', 'meeting_id': meeting_id_str, 'message': None}


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
