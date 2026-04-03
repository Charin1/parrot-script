import logging
from typing import Optional
from uuid import uuid4

from backend.storage.db import get_db

logger = logging.getLogger(__name__)


class MeetingsRepository:
    @staticmethod
    def _normalize_meeting(row) -> Optional[dict]:
        if row is None:
            return None

        meeting = dict(row)
        meeting["capture_mode"] = meeting.get("capture_mode") or "private"
        meeting["ghost_mode"] = bool(meeting.get("ghost_mode", True))
        meeting["assistant_join_status"] = meeting.get("assistant_join_status") or "not_requested"
        meeting["assistant_visible_name"] = (
            meeting.get("assistant_visible_name") or "Parrot Script Assistant"
        )
        meeting["consent_status"] = meeting.get("consent_status") or "not_needed"
        return meeting

    async def create(self, title: str) -> dict:
        meeting_id = str(uuid4())
        db = await get_db()
        try:
            await db.execute(
                "INSERT INTO meetings(id, title, status) VALUES (?, ?, ?)",
                (meeting_id, title, "active"),
            )
            await db.commit()
        finally:
            await db.close()
        return await self.get(meeting_id)

    async def get(self, meeting_id: str) -> Optional[dict]:
        db = await get_db()
        try:
            async with db.execute(
                "SELECT * FROM meetings WHERE id = ?",
                (meeting_id,),
            ) as cur:
                row = await cur.fetchone()
                return self._normalize_meeting(row)
        finally:
            await db.close()

    async def list_all(
        self,
        q: Optional[str] = None,
        status: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> list[dict]:
        conditions: list[str] = []
        params: list[object] = []

        if q:
            conditions.append("title LIKE ?")
            params.append(f"%{q}%")
        if status:
            conditions.append("status = ?")
            params.append(status)
        if from_date:
            conditions.append("created_at >= ?")
            params.append(from_date)
        if to_date:
            conditions.append("created_at <= ?")
            params.append(to_date)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"SELECT * FROM meetings {where_clause} ORDER BY created_at DESC"

        db = await get_db()
        try:
            async with db.execute(sql, params) as cur:
                rows = await cur.fetchall()
                return [self._normalize_meeting(row) for row in rows]
        finally:
            await db.close()

    async def update(self, meeting_id: str, **kwargs) -> dict:
        allowed = {
            "title",
            "ended_at",
            "duration_s",
            "status",
            "metadata",
            "capture_mode",
            "ghost_mode",
            "source_platform",
            "meeting_url",
            "assistant_join_status",
            "assistant_visible_name",
            "consent_status",
            "provider_session_id",
            "provider_metadata",
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            current = await self.get(meeting_id)
            if current is None:
                raise ValueError(f"Meeting {meeting_id} not found")
            return current

        set_clause = ", ".join(f"{key} = ?" for key in updates)
        params = list(updates.values()) + [meeting_id]

        db = await get_db()
        try:
            await db.execute(
                f"UPDATE meetings SET {set_clause} WHERE id = ?",
                params,
            )
            await db.commit()
        finally:
            await db.close()

        updated = await self.get(meeting_id)
        if updated is None:
            raise ValueError(f"Meeting {meeting_id} not found")
        return updated

    async def delete(self, meeting_id: str) -> bool:
        from pathlib import Path
        from backend.config import settings
        import os

        logger.info("Attempting to delete meeting: %s", meeting_id)
        db = await get_db()
        try:
            # Delete related records
            await db.execute("DELETE FROM transcript_segments WHERE meeting_id = ?", (meeting_id,))
            await db.execute("DELETE FROM summaries WHERE meeting_id = ?", (meeting_id,))
            await db.execute("DELETE FROM speakers WHERE meeting_id = ?", (meeting_id,))
            
            # Delete meeting record
            cur = await db.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))
            await db.commit()
            
            removed = cur.rowcount > 0
            if removed:
                logger.info("Deleted database records for meeting: %s", meeting_id)
                audio_path = Path(settings.db_path).parent / f"{meeting_id}.wav"
                if audio_path.exists():
                    try:
                        os.remove(audio_path)
                        logger.info("Deleted audio file for meeting %s: %s", meeting_id, audio_path)
                    except Exception as e:
                        logger.error("Failed to delete audio file for meeting %s at %s: %s", meeting_id, audio_path, e)
                else:
                    logger.debug("No audio file found for meeting %s at %s", meeting_id, audio_path)
            else:
                logger.warning("Meeting not found in database for deletion: %s", meeting_id)
            
            return removed
        except Exception as e:
            logger.exception("Error during meeting deletion for %s: %s", meeting_id, e)
            await db.rollback()
            raise
        finally:
            await db.close()



    async def end_meeting(self, meeting_id: str, duration_s: float) -> dict:
        db = await get_db()
        try:
            await db.execute(
                """
                UPDATE meetings
                SET ended_at = datetime('now'),
                    duration_s = ?,
                    status = 'completed'
                WHERE id = ?
                """,
                (duration_s, meeting_id,),
            )
            await db.commit()
        finally:
            await db.close()

        meeting = await self.get(meeting_id)
        if meeting is None:
            raise ValueError(f"Meeting {meeting_id} not found")
        return meeting
