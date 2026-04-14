from __future__ import annotations

import json
from collections import defaultdict, deque

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
            await self._mark_meeting_participant_aware(meeting_id)

        return {
            "segments_total": total,
            "segments_mapped": mapped,
            "segments_unmapped": max(0, total - mapped),
        }

    def _compute_overlap_attributions(self, segments: list[dict], speaking_events: list[dict]) -> list[dict]:
        """Map segments to participants using a sliding active-window overlap.

        Complexity is near-linear in practice: O(S + E + overlap_checks), where
        overlap_checks depends on concurrent active speakers rather than all events.
        """
        attributions: list[dict] = []
        active_events: deque[dict] = deque()
        event_index = 0
        event_total = len(speaking_events)

        for segment in segments:
            seg_start = float(segment["start_time"])
            seg_end = float(segment["end_time"])
            if seg_end <= seg_start:
                continue

            while event_index < event_total and float(speaking_events[event_index]["start_time"]) < seg_end:
                active_events.append(speaking_events[event_index])
                event_index += 1

            while active_events and float(active_events[0]["end_time"]) <= seg_start:
                active_events.popleft()

            if not active_events:
                continue

            overlap_by_participant: dict[str, float] = defaultdict(float)
            for event in active_events:
                overlap_start = max(seg_start, float(event["start_time"]))
                overlap_end = min(seg_end, float(event["end_time"]))
                overlap = overlap_end - overlap_start
                if overlap <= 0:
                    continue
                overlap_by_participant[str(event["participant_id"])] += overlap

            if not overlap_by_participant:
                continue

            ranked = sorted(overlap_by_participant.items(), key=lambda item: item[1], reverse=True)
            winner_id, winner_overlap = ranked[0]
            runner_up_overlap = ranked[1][1] if len(ranked) > 1 else 0.0

            # Avoid unstable assignments when two speakers overlap almost equally.
            if runner_up_overlap > 0 and (winner_overlap - runner_up_overlap) <= 0.05:
                continue

            seg_duration = max(0.001, seg_end - seg_start)
            confidence = max(0.0, min(1.0, winner_overlap / seg_duration))
            if confidence < MIN_ATTRIBUTION_CONFIDENCE:
                continue

            attributions.append(
                {
                    "segment_id": str(segment["id"]),
                    "participant_id": winner_id,
                    "confidence": confidence,
                    "attribution_source": "native_speaking_event_overlap",
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
