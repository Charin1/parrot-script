from __future__ import annotations

import logging
from uuid import uuid4

from backend.core.events import TranscriptSegmentEvent
from backend.storage.db import get_db

logger = logging.getLogger(__name__)


class SegmentsRepository:
    async def insert(self, event: TranscriptSegmentEvent) -> dict:
        segment_id = event.segment_id or str(uuid4())
        async with get_db() as db:
            await db.execute(
                """
                INSERT INTO transcript_segments(id, meeting_id, speaker, text, start_time, end_time, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (segment_id, event.meeting_id, event.speaker, event.text, event.start_time, event.end_time, event.confidence),
            )
            await db.commit()
        return await self._get(segment_id)

    async def get_by_meeting(self, meeting_id: str, limit: int = 500, offset: int = 0) -> list[dict]:
        async with get_db() as db:
            async with db.execute(
                """
                SELECT
                    ts.*,
                    spa.confidence AS participant_confidence,
                    spa.attribution_source AS attribution_source,
                    mp.external_id AS participant_external_id,
                    mp.display_name AS participant_name
                FROM transcript_segments ts
                LEFT JOIN segment_participant_attribution spa
                    ON spa.segment_id = ts.id
                LEFT JOIN meeting_participants mp
                    ON mp.id = spa.participant_id
                WHERE ts.meeting_id = ?
                ORDER BY ts.start_time ASC
                LIMIT ? OFFSET ?
                """,
                (meeting_id, limit, offset),
            ) as cur:
                rows = await cur.fetchall()
                return [self._normalize(row) for row in rows]

    async def get_by_time_range(self, meeting_id: str, start_time: float, end_time: float) -> list[dict]:
        async with get_db() as db:
            async with db.execute(
                """
                SELECT
                    ts.*,
                    mp.display_name AS participant_name
                FROM transcript_segments ts
                LEFT JOIN segment_participant_attribution spa
                    ON spa.segment_id = ts.id
                LEFT JOIN meeting_participants mp
                    ON mp.id = spa.participant_id
                WHERE ts.meeting_id = ? AND ts.start_time >= ? AND ts.start_time <= ?
                ORDER BY ts.start_time ASC
                """,
                (meeting_id, start_time, end_time),
            ) as cur:
                rows = await cur.fetchall()
                return [self._normalize(row) for row in rows]

    async def get_by_speaker(self, meeting_id: str, speaker_name: str) -> list[dict]:
        async with get_db() as db:
            async with db.execute(
                """
                SELECT
                    ts.*,
                    mp.display_name AS participant_name
                FROM transcript_segments ts
                LEFT JOIN segment_participant_attribution spa
                    ON spa.segment_id = ts.id
                LEFT JOIN meeting_participants mp
                    ON mp.id = spa.participant_id
                WHERE ts.meeting_id = ? AND (ts.speaker LIKE ? OR mp.display_name LIKE ?)
                ORDER BY ts.start_time ASC
                """,
                (meeting_id, f"%{speaker_name}%", f"%{speaker_name}%"),
            ) as cur:
                rows = await cur.fetchall()
                return [self._normalize(row) for row in rows]


    async def get_by_meeting_paginated(self, meeting_id: str, limit: int = 500, offset: int = 0) -> list[dict]:
        """Alias for get_by_meeting with explicit pagination parameters."""
        return await self.get_by_meeting(meeting_id, limit=limit, offset=offset)

    async def count_by_meeting(self, meeting_id: str) -> int:
        async with get_db() as db:
            async with db.execute(
                "SELECT COUNT(*) as cnt FROM transcript_segments WHERE meeting_id = ?",
                (meeting_id,),
            ) as cur:
                row = await cur.fetchone()
                return dict(row)["cnt"] if row else 0

    async def get_segment_windows(self, meeting_id: str) -> list[dict]:
        async with get_db() as db:
            async with db.execute(
                """
                SELECT id, start_time, end_time, text, confidence
                FROM transcript_segments
                WHERE meeting_id = ?
                ORDER BY start_time ASC
                """,
                (meeting_id,),
            ) as cur:
                rows = await cur.fetchall()
                return [dict(row) for row in rows]

    async def update_speaker(self, meeting_id: str, original_label: str, new_name: str) -> int:
        async with get_db() as db:
            cur = await db.execute(
                """
                UPDATE transcript_segments
                SET speaker = ?
                WHERE meeting_id = ? AND speaker = ?
                """,
                (new_name, meeting_id, original_label),
            )
            await db.commit()
            return cur.rowcount

    async def update_text(self, segment_id: str, text: str) -> dict | None:
        async with get_db() as db:
            await db.execute(
                "UPDATE transcript_segments SET text = ? WHERE id = ?",
                (text, segment_id),
            )
            await db.commit()
        return await self._get(segment_id)

    async def update_bookmark(self, segment_id: str, is_bookmarked: bool) -> dict | None:
        async with get_db() as db:
            await db.execute(
                "UPDATE transcript_segments SET is_bookmarked = ? WHERE id = ?",
                (1 if is_bookmarked else 0, segment_id),
            )
            await db.commit()
        return await self._get(segment_id)

    async def toggle_bookmark(self, segment_id: str, is_bookmarked: bool) -> dict | None:
        # Backwards-compatible alias used by the API route.
        return await self.update_bookmark(segment_id, is_bookmarked)

    async def get_full_text(self, meeting_id: str) -> str:
        segments = await self.get_by_meeting(meeting_id, limit=100000)
        lines = []
        for seg in segments:
            speaker = seg.get("display_name", seg.get("speaker", "Unknown"))
            lines.append(f"{speaker}: {seg['text']}")
        return "\n".join(lines)

    async def _get(self, segment_id: str) -> dict:
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM transcript_segments WHERE id = ?",
                (segment_id,),
            ) as cur:
                row = await cur.fetchone()
                if row is None:
                    return {"id": segment_id}
                return self._normalize(row)

    @staticmethod
    def _normalize(row) -> dict:
        d = dict(row)
        d["is_bookmarked"] = bool(d.get("is_bookmarked", False))
        participant_name = d.get("participant_name")
        d["speaker_identity_level"] = "participant-aware" if participant_name else "heuristic"
        return d
