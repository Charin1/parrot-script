from __future__ import annotations

from typing import Optional
from uuid import uuid4

from backend.storage.db import get_db


class MeetingsRepository:
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
                return dict(row) if row else None
        finally:
            await db.close()

    async def list_all(self) -> list[dict]:
        db = await get_db()
        try:
            async with db.execute(
                "SELECT * FROM meetings ORDER BY created_at DESC"
            ) as cur:
                rows = await cur.fetchall()
                return [dict(row) for row in rows]
        finally:
            await db.close()

    async def update(self, meeting_id: str, **kwargs) -> dict:
        allowed = {"title", "ended_at", "duration_s", "status", "metadata"}
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
        db = await get_db()
        try:
            await db.execute("DELETE FROM transcript_segments WHERE meeting_id = ?", (meeting_id,))
            await db.execute("DELETE FROM summaries WHERE meeting_id = ?", (meeting_id,))
            await db.execute("DELETE FROM speakers WHERE meeting_id = ?", (meeting_id,))
            cur = await db.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))
            await db.commit()
            return cur.rowcount > 0
        except Exception:
            await db.rollback()
            raise
        finally:
            await db.close()

    async def end_meeting(self, meeting_id: str) -> dict:
        db = await get_db()
        try:
            await db.execute(
                """
                UPDATE meetings
                SET ended_at = datetime('now'),
                    duration_s = (julianday(datetime('now')) - julianday(created_at)) * 86400.0,
                    status = 'completed'
                WHERE id = ?
                """,
                (meeting_id,),
            )
            await db.commit()
        finally:
            await db.close()

        meeting = await self.get(meeting_id)
        if meeting is None:
            raise ValueError(f"Meeting {meeting_id} not found")
        return meeting
