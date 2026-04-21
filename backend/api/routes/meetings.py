from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import subprocess
import time
from typing import Any, Literal, Optional, AsyncGenerator
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response, UploadFile, File, Form
from fastapi.responses import StreamingResponse

from backend.api.limiter import limiter

from pydantic import BaseModel, Field, field_validator
import aiofiles
from pathlib import Path

from backend.assistants import (
    AssistantJoinRequest,
    CaptureMode,
    ConsentStatus,
    AssistantJoinStatus,
    LocalMeetingAssistantProvider,
    SourcePlatform,
    infer_source_platform,
    resolve_capture_mode,
    serialize_provider_metadata,
)
from backend.audio.sources import LocalAudioSource, LocalVideoAudioSource, ImportedFileAudioSource
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
_pipeline_lock = asyncio.Lock()
assistant_provider = LocalMeetingAssistantProvider()

MeetingStatus = Literal['active', 'recording', 'completed', 'failed']
RecordingType = Literal['audio', 'video_audio']


def normalize_meeting_url_input(value: str | None) -> str | None:
    if value is None:
        return None

    cleaned = value.strip()
    if not cleaned:
        return None

    # Allow explicit schemes, including provider-specific deep links.
    if "://" in cleaned:
        return cleaned

    # Common Google Meet share format: just the meeting code.
    if re.fullmatch(r"[a-z]{3}-[a-z]{4}-[a-z]{3}", cleaned.lower()):
        return f"https://meet.google.com/{cleaned.lower()}"

    # If it already looks like a hostname/path, default to https.
    hostish = cleaned.split("/")[0]
    if "." in hostish:
        return f"https://{cleaned}"

    return cleaned


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
        return normalize_meeting_url_input(value)

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
    recording_type: Optional[RecordingType] = None
    video_resolution: Optional[str] = Field(default=None, max_length=20)

    @field_validator('meeting_url')
    @classmethod
    def normalize_meeting_url(cls, value: Optional[str]) -> Optional[str]:
        return normalize_meeting_url_input(value)

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
        async with _pipeline_lock:
            active_pipelines.pop(meeting_id, None)
        raise
    except Exception as exc:
        logger.exception('Pipeline start failed for %s: %s', meeting_id, exc)
        async with _pipeline_lock:
            active_pipelines.pop(meeting_id, None)
        await meetings_repo.update(
            meeting_id,
            status='failed',
            metadata=f"Pipeline start failed: {exc}",
        )
    finally:
        async with _pipeline_lock:
            _pipeline_start_tasks.pop(meeting_id, None)


async def _run_import_job(meeting_id: str, source_path: Path) -> None:
    """Convert uploaded media to WAV, then run transcription in the background."""
    data_dir = Path(settings.db_path).parent
    wav_path = data_dir / f"{meeting_id}.wav"
    mp4_path = data_dir / f"{meeting_id}.mp4"

    def _is_video(path: Path) -> bool:
        return path.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}

    async def _run_cmd(cmd: list[str]) -> tuple[int, str]:
        def _run() -> tuple[int, str]:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            out = (result.stderr or "")[-4000:]
            return result.returncode, out
        return await asyncio.to_thread(_run)

    try:
        meeting = await meetings_repo.get(meeting_id)
        if meeting is None:
            return

        # Best-effort: store a playable MP4 if the upload was a video container.
        has_video = False
        if _is_video(source_path):
            cmd = ["ffmpeg", "-y", "-i", str(source_path), "-movflags", "faststart", "-c", "copy", str(mp4_path)]
            code, err = await _run_cmd(cmd)
            if code != 0:
                logger.warning("Video remux failed for %s (will continue without video): %s", meeting_id, err)
            else:
                has_video = mp4_path.exists() and mp4_path.stat().st_size > 0

        # Extract WAV for transcription (16kHz mono PCM).
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(source_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(settings.audio_sample_rate),
            "-c:a",
            "pcm_s16le",
            str(wav_path),
        ]
        code, err = await _run_cmd(cmd)
        if code != 0 or not wav_path.exists():
            raise RuntimeError(f"ffmpeg audio extract failed: {err}")

        # Read WAV duration for final meeting duration.
        import wave

        def _duration() -> float:
            with wave.open(str(wav_path), "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate() or settings.audio_sample_rate
                return frames / float(rate) if rate > 0 else 0.0

        duration_s = await asyncio.to_thread(_duration)

        await meetings_repo.update(
            meeting_id,
            status="recording",
            capture_mode="private",
            ghost_mode=True,
            source_platform="local",
            meeting_url=None,
            assistant_join_status="not_requested",
            consent_status="not_needed",
            recording_type="video_audio" if has_video else "audio",
            has_video=has_video,
            metadata="Imported file transcription in progress.",
            duration_s=duration_s,
        )

        capture_src = ImportedFileAudioSource(wav_path)
        pipeline = MeetingPipeline(meeting_id, capture_source=capture_src)
        async with _pipeline_lock:
            active_pipelines[meeting_id] = pipeline

        start_task = asyncio.create_task(_start_import_pipeline(meeting_id, pipeline, duration_s))
        async with _pipeline_lock:
            _pipeline_start_tasks[meeting_id] = start_task
    except Exception as exc:
        logger.exception("Import job failed for %s: %s", meeting_id, exc)
        with contextlib.suppress(Exception):
            await meetings_repo.update(meeting_id, status="failed", metadata=f"Import failed: {exc}")


async def _start_import_pipeline(meeting_id: str, pipeline: MeetingPipeline, duration_s: float) -> None:
    """Start the pipeline and automatically mark the meeting completed when done."""
    try:
        await pipeline.start()
        await pipeline.wait()
        current = await meetings_repo.get(meeting_id)
        if current is None:
            return
        if current.get("status") != "completed":
            await meetings_repo.end_meeting(meeting_id, duration_s)
    except asyncio.CancelledError:
        if pipeline.running:
            await pipeline.stop()
        raise
    except Exception as exc:
        logger.exception("Import pipeline failed for %s: %s", meeting_id, exc)
        with contextlib.suppress(Exception):
            await meetings_repo.update(meeting_id, status="failed", metadata=f"Import pipeline failed: {exc}")
    finally:
        async with _pipeline_lock:
            active_pipelines.pop(meeting_id, None)
            _pipeline_start_tasks.pop(meeting_id, None)


async def _stream_media_file(
    file_path: Path,
    media_type: str,
    request: Request,
) -> Response:
    """Shared file-streaming helper with HTTP Range support."""
    if not file_path.exists():
        kind = 'Audio' if 'audio' in media_type else 'Video'
        raise HTTPException(status_code=404, detail=f'{kind} not found for this meeting')

    file_size = file_path.stat().st_size
    range_header = request.headers.get('range')

    if range_header:
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
            async with aiofiles.open(file_path, 'rb') as f:
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
            media_type=media_type,
            headers={
                'Content-Range': f'bytes {range_start}-{range_end}/{file_size}',
                'Content-Length': str(content_length),
                'Accept-Ranges': 'bytes',
                'Cache-Control': 'no-store',
            },
        )

    async def full_generator() -> AsyncGenerator[bytes, None]:
        async with aiofiles.open(file_path, 'rb') as f:
            while True:
                chunk = await f.read(65536)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(
        full_generator(),
        media_type=media_type,
        headers={
            'Content-Length': str(file_size),
            'Accept-Ranges': 'bytes',
            'Cache-Control': 'no-store',
        },
    )


def _mux_audio_into_video(video_path: Path, audio_path: Path) -> bool:
    """Mux WAV audio into MP4 so video playback has an audio track."""
    if not video_path.exists() or video_path.stat().st_size == 0:
        return False
    if not audio_path.exists() or audio_path.stat().st_size == 0:
        return False

    temp_output = video_path.with_name(f"{video_path.stem}.mux.tmp{video_path.suffix}")
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(audio_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        "-movflags",
        "+faststart",
        str(temp_output),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        logger.warning("FFmpeg not found while muxing audio into video for %s", video_path)
        return False
    except Exception as exc:
        logger.warning("Muxing audio into video failed for %s: %s", video_path, exc)
        return False

    if result.returncode != 0:
        stderr_lines = [line.strip() for line in result.stderr.splitlines() if line.strip()]
        logger.warning(
            "FFmpeg mux failed for %s (exit=%s): %s",
            video_path,
            result.returncode,
            " | ".join(stderr_lines[-6:]) if stderr_lines else "no stderr",
        )
        with contextlib.suppress(Exception):
            if temp_output.exists():
                temp_output.unlink()
        return False

    temp_output.replace(video_path)
    logger.info("Muxed WAV audio into MP4 for %s", video_path)
    return True


def _video_has_audio_track(video_path: Path) -> bool:
    if not video_path.exists() or video_path.stat().st_size == 0:
        return False

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except Exception:
        return False

    if result.returncode != 0:
        return False
    return any(line.strip() == "audio" for line in result.stdout.splitlines())


def _ensure_video_has_audio(video_path: Path, audio_path: Path) -> bool:
    if _video_has_audio_track(video_path):
        return True
    return _mux_audio_into_video(video_path, audio_path)


@router.post('/')
async def create_meeting(body: CreateMeetingRequest) -> dict[str, Any]:
    return await meetings_repo.create(body.title)


@router.post('/import')
@limiter.limit("3/minute")
async def import_meeting(
    request: Request,
    title: str = Form(...),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    clean_title = (title or "").strip()[:200]
    if not clean_title:
        raise HTTPException(status_code=422, detail="Meeting title cannot be empty")

    meeting = await meetings_repo.create(clean_title)
    meeting_id = meeting["id"]

    data_dir = Path(settings.db_path).parent
    suffix = Path(file.filename or "").suffix or ".bin"
    source_path = data_dir / f"{meeting_id}_upload{suffix}"

    try:
        async with aiofiles.open(source_path, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                await out.write(chunk)
    except Exception as exc:
        logger.exception("Failed to save uploaded file for %s: %s", meeting_id, exc)
        with contextlib.suppress(Exception):
            await meetings_repo.update(meeting_id, status="failed", metadata=f"Upload save failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to save uploaded file")
    finally:
        with contextlib.suppress(Exception):
            await file.close()

    await meetings_repo.update(
        meeting_id,
        status="recording",
        metadata="Upload received. Import processing queued.",
    )

    # Run conversion + transcription in the background so the user can keep using the UI.
    asyncio.create_task(_run_import_job(meeting_id, source_path))
    updated = await meetings_repo.get(meeting_id)
    return updated or meeting


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
    return await _stream_media_file(audio_path, 'audio/wav', request)



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

    async with _pipeline_lock:
        pipeline = active_pipelines.pop(meeting_id_str, None)
        task = _pipeline_start_tasks.pop(meeting_id_str, None)

    if pipeline is not None:
        logger.info("Stopping active pipeline for meeting: %s", meeting_id_str)
        await pipeline.stop()

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
@limiter.limit("10/minute")
async def start_recording(request: Request, meeting_id: UUID, body: Optional[StartMeetingRequest] = None) -> dict[str, Any]:
    meeting_id_str = str(meeting_id)
    meeting = await meetings_repo.get(meeting_id_str)
    if meeting is None:
        raise HTTPException(status_code=404, detail='Meeting not found')

    async with _pipeline_lock:
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
    
    # Determine recording type and resolution
    recording_type = body.recording_type or 'audio'
    video_resolution = body.video_resolution or settings.video_default_resolution

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

        if recording_type == 'video_audio':
            capture_src = LocalVideoAudioSource(
                meeting_id_str,
                resolution=video_resolution,
                ghost_mode=False,
            )
        else:
            capture_src = LocalAudioSource(meeting_id_str)

        pipeline = MeetingPipeline(meeting_id_str, capture_source=capture_src)
        async with _pipeline_lock:
            active_pipelines[meeting_id_str] = pipeline
        start_task = asyncio.create_task(_start_pipeline(meeting_id_str, pipeline))
        async with _pipeline_lock:
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
            recording_type=recording_type,
            video_resolution=video_resolution if recording_type == 'video_audio' else None,
        )
        return {
            'status': 'recording',
            'meeting_id': meeting_id_str,
            'message': session.message,
        }

    # Determine recording type and resolution
    recording_type = body.recording_type or 'audio'
    video_resolution = body.video_resolution or settings.video_default_resolution

    if recording_type == 'video_audio':
        capture_src = LocalVideoAudioSource(
            meeting_id_str,
            resolution=video_resolution,
            ghost_mode=ghost_mode,
        )
    else:
        capture_src = LocalAudioSource(meeting_id_str)

    pipeline = MeetingPipeline(meeting_id_str, capture_source=capture_src)
    async with _pipeline_lock:
        active_pipelines[meeting_id_str] = pipeline

    start_task = asyncio.create_task(_start_pipeline(meeting_id_str, pipeline))
    async with _pipeline_lock:
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
        recording_type=recording_type,
        video_resolution=video_resolution if recording_type == 'video_audio' else None,
    )
    return {'status': 'recording', 'meeting_id': meeting_id_str, 'message': None}


@router.post('/{meeting_id}/stop')
async def stop_recording(meeting_id: UUID) -> dict[str, str]:
    meeting_id_str = str(meeting_id)
    meeting = await meetings_repo.get(meeting_id_str)
    if meeting is None:
        raise HTTPException(status_code=404, detail='Meeting not found')

    async with _pipeline_lock:
        task = _pipeline_start_tasks.pop(meeting_id_str, None)
    if task is not None and not task.done():
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async with _pipeline_lock:
        pipeline = active_pipelines.pop(meeting_id_str, None)
    if pipeline is not None:
        await pipeline.stop()
        
    final_duration = (meeting.get('duration_s') or 0.0)
    if pipeline is not None:
        final_duration += max(0.0, time.time() - pipeline.start_epoch)

    await meetings_repo.end_meeting(meeting_id_str, final_duration)

    # Ensure completed MP4 includes the captured WAV audio track.
    video_path = Path(settings.db_path).parent / f"{meeting_id_str}.mp4"
    audio_path = Path(settings.db_path).parent / f"{meeting_id_str}.wav"
    if meeting.get("recording_type") == "video_audio":
        await asyncio.to_thread(_ensure_video_has_audio, video_path, audio_path)

    # Mark video availability if a video file was produced
    if video_path.exists() and video_path.stat().st_size > 0:
        await meetings_repo.update(meeting_id_str, has_video=True)

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


@router.get('/{meeting_id}/video')
async def get_meeting_video(meeting_id: UUID, request: Request) -> Response:
    meeting_id_str = str(meeting_id)
    meeting = await meetings_repo.get(meeting_id_str)
    if meeting is None:
        raise HTTPException(status_code=404, detail='Meeting not found')

    video_path = Path(settings.db_path).parent / f"{meeting_id_str}.mp4"
    audio_path = Path(settings.db_path).parent / f"{meeting_id_str}.wav"
    if meeting.get("recording_type") == "video_audio":
        # Best-effort: if this is an older recording or mux was missed, repair on access.
        await asyncio.to_thread(_ensure_video_has_audio, video_path, audio_path)
    return await _stream_media_file(video_path, 'video/mp4', request)
