from __future__ import annotations

from typing import Optional
from uuid import uuid4

from backend.storage.db import get_db


class SummariesRepository:
    async def insert(self, meeting_id: str, content: str, model: str) -> dict:
        summary_id = str(uuid4())
        db = await get_db()
        try:
            await db.execute(
                """
                INSERT INTO summaries(id, meeting_id, content, model_used)
                VALUES (?, ?, ?, ?)
                """,
                (summary_id, meeting_id, content, model),
            )
            await db.commit()
        finally:
            await db.close()
        row = await self.get_by_id(summary_id)
        if row is None:
            raise RuntimeError("Failed to create summary")
        return row

    async def get_by_id(self, summary_id: str) -> Optional[dict]:
        db = await get_db()
        try:
            async with db.execute("SELECT * FROM summaries WHERE id = ?", (summary_id,)) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None
        finally:
            await db.close()

    async def get_by_meeting(self, meeting_id: str) -> Optional[dict]:
        db = await get_db()
        try:
            async with db.execute(
                """
                SELECT * FROM summaries
                WHERE meeting_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (meeting_id,),
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None
        finally:
            await db.close()

    async def update(self, summary_id: str, **kwargs) -> dict:
        allowed = {"content", "summary", "action_items", "decisions", "model_used"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            existing = await self.get_by_id(summary_id)
            if existing is None:
                raise ValueError(f"Summary {summary_id} not found")
            return existing

        set_clause = ", ".join(f"{key} = ?" for key in updates)
        params = list(updates.values()) + [summary_id]

        db = await get_db()
        try:
            await db.execute(
                f"UPDATE summaries SET {set_clause} WHERE id = ?",
                params,
            )
            await db.commit()
        finally:
            await db.close()

        updated = await self.get_by_id(summary_id)
        if updated is None:
            raise ValueError(f"Summary {summary_id} not found")
        return updated
