from __future__ import annotations

import json

from backend.storage.repositories.meetings import MeetingsRepository
from backend.storage.repositories.participants import ParticipantsRepository
from backend.storage.repositories.segments import SegmentsRepository

MAX_PARTICIPANTS_PER_SYNC = 500
MAX_SPEAKING_EVENTS_PER_SYNC = 100_000
MIN_ATTRIBUTION_CONFIDENCE = 0.2


class NativeAttributionService:
    """Service layer for first-party participant-aware attribution.

    Keeps API routes thin and isolates attribution logic from storage details.
    """

    def __init__(
        self,
        participants_repo: ParticipantsRepository | None = None,
        segments_repo: SegmentsRepository | None = None,
        meetings_repo: MeetingsRepository | None = None,
    ):
        self.participants_repo = participants_repo or ParticipantsRepository()
        self.segments_repo = segments_repo or SegmentsRepository()
        self.meetings_repo = meetings_repo or MeetingsRepository()

    async def sync_participants(self, meeting_id: str, participants: list[dict]) -> dict[str, int]:
        if len(participants) > MAX_PARTICIPANTS_PER_SYNC:
            raise ValueError(
                f"Too many participants in one sync ({len(participants)}). "
                f"Max allowed is {MAX_PARTICIPANTS_PER_SYNC}."
            )

        synced = 0
        for participant in participants:
            external_id = str(participant["external_id"]).strip()
            display_name = str(participant["display_name"]).strip()
            if not external_id or not display_name:
                continue

            metadata_dict = participant.get("metadata")
            metadata_json = None
            if metadata_dict is not None:
                metadata_json = json.dumps(metadata_dict, separators=(",", ":"), sort_keys=True)
                if len(metadata_json) > 4000:
                    metadata_json = metadata_json[:4000]

            await self.participants_repo.upsert(
                meeting_id,
                external_id=external_id,
                display_name=display_name,
                is_host=bool(participant.get("is_host", False)),
                is_bot=bool(participant.get("is_bot", False)),
                joined_at=participant.get("joined_at"),
                left_at=participant.get("left_at"),
                metadata=metadata_json,
            )
            synced += 1

        return {"participants_synced": synced}

    async def sync_speaking_events(self, meeting_id: str, events: list[dict], source: str) -> dict[str, int]:
        if len(events) > MAX_SPEAKING_EVENTS_PER_SYNC:
            raise ValueError(
                f"Too many speaking events in one sync ({len(events)}). "
                f"Max allowed is {MAX_SPEAKING_EVENTS_PER_SYNC}."
            )

        sanitized: list[dict] = []
        for event in events:
            start = float(event["start_time"])
            end = float(event["end_time"])
            if start < 0 or end <= start:
                continue
            confidence = event.get("confidence")
            if confidence is not None:
                confidence = max(0.0, min(1.0, float(confidence)))
            sanitized.append(
                {
                    "participant_external_id": str(event["participant_external_id"]).strip(),
                    "start_time": start,
                    "end_time": end,
                    "confidence": confidence,
                }
            )

        inserted = await self.participants_repo.replace_speaking_events(
            meeting_id,
            events=sanitized,
            source=source,
        )
        return {
            "events_received": len(events),
            "events_inserted": inserted,
            "events_dropped": max(0, len(events) - inserted),
        }

    async def recompute_attribution(self, meeting_id: str) -> dict[str, int]:
        segments = await self.segments_repo.get_segment_windows(meeting_id)
        speaking_events = await self.participants_repo.get_speaking_events(meeting_id)

        # Both lists are already sorted by start_time in repository queries.
        attributions = self._compute_overlap_attributions(segments, speaking_events)
        await self.participants_repo.replace_segment_attributions(meeting_id, attributions)

        mapped = len(attributions)
        total = len(segments)
        
        if mapped > 0:
            from backend.api.websocket import manager
            
            # Build batch of updated segments and broadcast once
            seg_map = {str(s["id"]): s for s in segments}
            batch = []
            for attr in attributions:
                seg = seg_map.get(attr["segment_id"])
                if seg:
                    batch.append({
                        "id": attr["segment_id"],
                        "segment_id": attr["segment_id"],
                        "meeting_id": meeting_id,
                        "speaker": attr["participant_id"],
                        "participant_name": attr.get("participant_name"),
                        "text": seg["text"],
                        "start_time": seg["start_time"],
                        "end_time": seg["end_time"],
                        "confidence": seg["confidence"],
                        "speaker_identity_level": "participant-aware"
                    })

            # Send all updates in one batch, then individual for frontend compatibility
            for item in batch:
                await manager.broadcast(meeting_id, {"type": "transcript", "data": item})
            
            await self._mark_meeting_participant_aware(meeting_id)

        return {
            "segments_total": total,
            "segments_mapped": mapped,
            "segments_unmapped": max(0, total - mapped),
        }

    def _compute_overlap_attributions(self, segments: list[dict], speaking_events: list[dict]) -> list[dict]:
        """Map segments to participants using a carry-forward strategy.

        Each detected speaker owns all segments from their detection point
        until a different speaker is detected.  Segments before the first
        detection are assigned to the first detected speaker.
        """
        if not segments or not speaking_events:
            return []

        # Build a timeline of speaker changes: [(time, participant_id, participant_name)]
        speaker_timeline: list[tuple[float, str, str]] = []
        for event in speaking_events:
            p_id = str(event["participant_id"])
            p_name = event.get("participant_name") or event.get("participant_external_id") or p_id
            start = float(event["start_time"])
            speaker_timeline.append((start, p_id, p_name))

        # Sort by time; deduplicate consecutive same-speaker entries
        speaker_timeline.sort(key=lambda x: x[0])

        attributions: list[dict] = []
        for segment in segments:
            seg_start = float(segment["start_time"])
            seg_end = float(segment["end_time"])
            if seg_end <= seg_start:
                continue

            seg_mid = (seg_start + seg_end) / 2.0

            # Find the most recent speaker detection at or before this segment's midpoint
            best_id = None
            best_name = None
            for t, p_id, p_name in speaker_timeline:
                if t <= seg_mid:
                    best_id = p_id
                    best_name = p_name
                else:
                    break

            # If no speaker detected before this segment, use the first detected speaker
            if best_id is None:
                best_id = speaker_timeline[0][1]
                best_name = speaker_timeline[0][2]

            attributions.append(
                {
                    "segment_id": str(segment["id"]),
                    "participant_id": best_id,
                    "participant_name": best_name,
                    "confidence": 1.0,
                    "attribution_source": "native_carry_forward",
                }
            )

        return attributions

    async def _mark_meeting_participant_aware(self, meeting_id: str) -> None:
        meeting = await self.meetings_repo.get(meeting_id)
        if meeting is None:
            return

        metadata_raw = meeting.get("provider_metadata")
        metadata: dict[str, object] = {}
        if isinstance(metadata_raw, str) and metadata_raw.strip():
            try:
                parsed = json.loads(metadata_raw)
                if isinstance(parsed, dict):
                    metadata = parsed
            except json.JSONDecodeError:
                metadata = {}

        metadata["speaker_identity_level"] = "participant-aware"
        metadata["speaker_identity_reason"] = (
            "Segment attribution is mapped from native provider participant speaking events."
        )
        metadata["capture_topology"] = "native_participant_events"

        await self.meetings_repo.update(
            meeting_id,
            provider_metadata=json.dumps(metadata, separators=(",", ":"), sort_keys=True),
        )
