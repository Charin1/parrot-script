from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from backend.native.service import NativeAttributionService
from backend.storage.repositories.meetings import MeetingsRepository
from backend.storage.repositories.participants import ParticipantsRepository

router = APIRouter(prefix="/api/meetings", tags=["native-attribution"])
meetings_repo = MeetingsRepository()
participants_repo = ParticipantsRepository()
native_service = NativeAttributionService(
    participants_repo=participants_repo,
    meetings_repo=meetings_repo,
)


class NativeParticipant(BaseModel):
    external_id: str = Field(min_length=1, max_length=200)
    display_name: str = Field(min_length=1, max_length=200)
    is_host: bool = False
    is_bot: bool = False
    joined_at: float | None = None
    left_at: float | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("external_id", "display_name")
    @classmethod
    def _normalize_required_string(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value cannot be empty")
        return cleaned


class SyncParticipantsRequest(BaseModel):
    participants: list[NativeParticipant] = Field(default_factory=list)


class NativeSpeakingEvent(BaseModel):
    participant_external_id: str = Field(min_length=1, max_length=200)
    start_time: float = Field(ge=0.0)
    end_time: float = Field(gt=0.0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("participant_external_id")
    @classmethod
    def _normalize_participant_external_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("participant_external_id cannot be empty")
        return cleaned

    @field_validator("end_time")
    @classmethod
    def _validate_end_time(cls, value: float, info) -> float:
        start_time = info.data.get("start_time")
        if start_time is not None and value <= start_time:
            raise ValueError("end_time must be greater than start_time")
        return value


class SyncSpeakingEventsRequest(BaseModel):
    events: list[NativeSpeakingEvent] = Field(default_factory=list)
    source: str = Field(default="native_provider_event", min_length=1, max_length=120)

    @field_validator("source")
    @classmethod
    def _normalize_source(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("source cannot be empty")
        return cleaned


@router.get("/{meeting_id}/native/participants")
async def list_native_participants(meeting_id: UUID) -> dict[str, Any]:
    meeting_id_str = str(meeting_id)
    meeting = await meetings_repo.get(meeting_id_str)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found")

    participants = await participants_repo.list_by_meeting(meeting_id_str)
    return {"items": participants, "total": len(participants)}


@router.put("/{meeting_id}/native/participants")
async def sync_native_participants(meeting_id: UUID, body: SyncParticipantsRequest) -> dict[str, Any]:
    meeting_id_str = str(meeting_id)
    meeting = await meetings_repo.get(meeting_id_str)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found")

    try:
        result = await native_service.sync_participants(
            meeting_id_str,
            [item.model_dump(exclude_none=True) for item in body.participants],
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return result


@router.put("/{meeting_id}/native/speaking-events")
async def sync_native_speaking_events(
    meeting_id: UUID,
    body: SyncSpeakingEventsRequest,
) -> dict[str, Any]:
    meeting_id_str = str(meeting_id)
    meeting = await meetings_repo.get(meeting_id_str)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found")

    try:
        result = await native_service.sync_speaking_events(
            meeting_id_str,
            [item.model_dump(exclude_none=True) for item in body.events],
            body.source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return result


@router.post("/{meeting_id}/native/attribution/recompute")
async def recompute_native_attribution(meeting_id: UUID) -> dict[str, Any]:
    meeting_id_str = str(meeting_id)
    meeting = await meetings_repo.get(meeting_id_str)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found")

    return await native_service.recompute_attribution(meeting_id_str)
