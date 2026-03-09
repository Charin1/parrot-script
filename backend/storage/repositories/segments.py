from __future__ import annotations

from backend.core.events import TranscriptSegmentEvent
from backend.storage.db import get_db


class SegmentsRepository:
    async def insert(self, segment: TranscriptSegmentEvent) -> dict:
        db = await get_db()
        try:
            await db.execute(
                """
                INSERT INTO transcript_segments(
                    id, meeting_id, speaker, text, start_time, end_time, confidence, is_bookmarked
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    segment.segment_id,
                    segment.meeting_id,
                    segment.speaker,
                    segment.text,
                    segment.start_time,
                    segment.end_time,
                    segment.confidence,
                ),
            )
            await db.commit()
        finally:
            await db.close()

        return {
            "id": segment.segment_id,
            "meeting_id": segment.meeting_id,
            "speaker": segment.speaker,
            "text": segment.text,
            "start_time": segment.start_time,
            "end_time": segment.end_time,
            "confidence": segment.confidence,
            "is_bookmarked": False,
        }

    async def get_by_meeting(self, meeting_id: str) -> list[dict]:
        db = await get_db()
        try:
            async with db.execute(
                """
                SELECT ts.*, CAST(IFNULL(ts.is_bookmarked, 0) AS BOOLEAN) as is_bookmarked, s.name as display_name
                FROM transcript_segments ts
                LEFT JOIN speakers s ON ts.meeting_id = s.meeting_id AND ts.speaker = s.label
                WHERE ts.meeting_id = ?
                ORDER BY ts.start_time ASC
                """,
                (meeting_id,),
            ) as cur:
                rows = await cur.fetchall()
                return [dict(row) for row in rows]
        finally:
            await db.close()

    async def toggle_bookmark(self, segment_id: str, is_bookmarked: bool) -> bool:
        db = await get_db()
        try:
            val = 1 if is_bookmarked else 0
            cur = await db.execute(
                "UPDATE transcript_segments SET is_bookmarked = ? WHERE id = ?",
                (val, segment_id)
            )
            await db.commit()
            return cur.rowcount > 0
        finally:
            await db.close()

    async def get_by_meeting_paginated(self, meeting_id: str, limit: int, offset: int) -> list[dict]:
        db = await get_db()
        try:
            async with db.execute(
                """
                SELECT ts.*, CAST(IFNULL(ts.is_bookmarked, 0) AS BOOLEAN) as is_bookmarked, s.name as display_name
                FROM transcript_segments ts
                LEFT JOIN speakers s ON ts.meeting_id = s.meeting_id AND ts.speaker = s.label
                WHERE ts.meeting_id = ?
                ORDER BY ts.start_time ASC
                LIMIT ? OFFSET ?
                """,
                (meeting_id, limit, offset),
            ) as cur:
                rows = await cur.fetchall()
                return [dict(row) for row in rows]
        finally:
            await db.close()

    async def count_by_meeting(self, meeting_id: str) -> int:
        db = await get_db()
        try:
            async with db.execute(
                "SELECT COUNT(*) AS count FROM transcript_segments WHERE meeting_id = ?",
                (meeting_id,),
            ) as cur:
                row = await cur.fetchone()
                if row is None:
                    return 0
                return int(row["count"])
        finally:
            await db.close()

    async def get_full_text(self, meeting_id: str) -> str:
        segments = await self.get_by_meeting(meeting_id)
        return "\n".join(seg["text"].strip() for seg in segments if seg.get("text"))
