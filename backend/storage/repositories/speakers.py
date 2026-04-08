from __future__ import annotations

from uuid import uuid4

from backend.storage.db import get_db


class SpeakersRepository:
    async def upsert(self, meeting_id: str, label: str, name: str | None = None) -> dict:
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM speakers WHERE meeting_id = ? AND label = ?",
                (meeting_id, label),
            ) as cur:
                existing = await cur.fetchone()

            if existing:
                if name:
                    await db.execute(
                        "UPDATE speakers SET name = ? WHERE id = ?",
                        (name, dict(existing)["id"]),
                    )
                    await db.commit()
                return dict(existing)

            speaker_id = str(uuid4())
            await db.execute(
                "INSERT INTO speakers(id, meeting_id, label, name) VALUES (?, ?, ?, ?)",
                (speaker_id, meeting_id, label, name or label),
            )
            await db.commit()

        return await self._get(speaker_id)

    async def get_by_meeting(self, meeting_id: str) -> list[dict]:
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM speakers WHERE meeting_id = ?",
                (meeting_id,),
            ) as cur:
                rows = await cur.fetchall()
                return [dict(row) for row in rows]

    async def update_name(self, meeting_id: str, label: str, name: str) -> dict | None:
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM speakers WHERE meeting_id = ? AND label = ?",
                (meeting_id, label),
            ) as cur:
                existing = await cur.fetchone()

            if not existing:
                return None

            await db.execute(
                "UPDATE speakers SET name = ? WHERE id = ?",
                (name, dict(existing)["id"]),
            )
            await db.commit()

        return await self._get(dict(existing)["id"])

    async def rename_by_label(self, meeting_id: str, label: str, name: str) -> dict:
        """Alias for update_name, used by the meetings route."""
        result = await self.update_name(meeting_id, label, name)
        if result is None:
            raise ValueError(f"Speaker '{label}' not found in meeting {meeting_id}")
        return result

    async def get_display_name(self, meeting_id: str, label: str) -> str:
        async with get_db() as db:
            async with db.execute(
                "SELECT name FROM speakers WHERE meeting_id = ? AND label = ?",
                (meeting_id, label),
            ) as cur:
                row = await cur.fetchone()
                if row and dict(row).get("name"):
                    return dict(row)["name"]
                return label

    async def _get(self, speaker_id: str) -> dict:
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM speakers WHERE id = ?",
                (speaker_id,),
            ) as cur:
                row = await cur.fetchone()
                if row is None:
                    return {"id": speaker_id}
                return dict(row)
