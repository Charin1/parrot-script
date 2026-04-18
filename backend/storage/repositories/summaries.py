from __future__ import annotations

from uuid import uuid4

from backend.storage.db import get_db


class SummariesRepository:
    async def insert(self, meeting_id: str, content: str, model: str, summary: str = None, action_items: str = None, decisions: str = None) -> dict:
        summary_id = str(uuid4())
        async with get_db() as db:
            await db.execute(
                """
                INSERT INTO summaries(id, meeting_id, content, model_used, summary, action_items, decisions)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (summary_id, meeting_id, content, model, summary, action_items, decisions),
            )
            await db.commit()
        return await self._get(summary_id)

    async def get_by_meeting(self, meeting_id: str) -> dict | None:
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM summaries WHERE meeting_id = ? ORDER BY created_at DESC LIMIT 1",
                (meeting_id,),
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def update(self, summary_id: str, content: str, model_used: str, summary: str = None, action_items: str = None, decisions: str = None) -> dict:
        async with get_db() as db:
            await db.execute(
                "UPDATE summaries SET content = ?, model_used = ?, summary = ?, action_items = ?, decisions = ? WHERE id = ?",
                (content, model_used, summary, action_items, decisions, summary_id),
            )
            await db.commit()
        return await self._get(summary_id)

    async def _get(self, summary_id: str) -> dict:
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM summaries WHERE id = ?",
                (summary_id,),
            ) as cur:
                row = await cur.fetchone()
                if row is None:
                    return {"id": summary_id}
                return dict(row)
