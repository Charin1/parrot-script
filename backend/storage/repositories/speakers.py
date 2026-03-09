from __future__ import annotations

from typing import Optional
from uuid import uuid4

from backend.storage.db import get_db


PALETTE = [
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
]


class SpeakersRepository:
    async def upsert(self, meeting_id: str, label: str) -> dict:
        existing = await self._find_by_label(meeting_id, label)
        if existing:
            return existing

        speaker_id = str(uuid4())
        color = PALETTE[abs(hash(label)) % len(PALETTE)]

        db = await get_db()
        try:
            await db.execute(
                "INSERT INTO speakers(id, meeting_id, label, color) VALUES (?, ?, ?, ?)",
                (speaker_id, meeting_id, label, color),
            )
            await db.commit()
        finally:
            await db.close()

        created = await self.get_by_id(speaker_id)
        if created is None:
            raise RuntimeError("Failed to create speaker")
        return created

    async def rename(self, speaker_id: str, name: str) -> dict:
        db = await get_db()
        try:
            await db.execute(
                "UPDATE speakers SET name = ? WHERE id = ?",
                (name, speaker_id),
            )
            await db.commit()
        finally:
            await db.close()

        updated = await self.get_by_id(speaker_id)
        if updated is None:
            raise ValueError(f"Speaker {speaker_id} not found")
        return updated

    async def rename_by_label(self, meeting_id: str, label: str, name: str) -> dict:
        speaker = await self._find_by_label(meeting_id, label)
        if not speaker:
            raise ValueError(f"Speaker '{label}' not found in meeting {meeting_id}")
            
        return await self.rename(speaker["id"], name)

    async def get_by_id(self, speaker_id: str) -> Optional[dict]:
        db = await get_db()
        try:
            async with db.execute("SELECT * FROM speakers WHERE id = ?", (speaker_id,)) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None
        finally:
            await db.close()

    async def get_by_meeting(self, meeting_id: str) -> list[dict]:
        db = await get_db()
        try:
            async with db.execute(
                "SELECT * FROM speakers WHERE meeting_id = ? ORDER BY label ASC",
                (meeting_id,),
            ) as cur:
                rows = await cur.fetchall()
                return [dict(row) for row in rows]
        finally:
            await db.close()

    async def _find_by_label(self, meeting_id: str, label: str) -> Optional[dict]:
        db = await get_db()
        try:
            async with db.execute(
                "SELECT * FROM speakers WHERE meeting_id = ? AND label = ? LIMIT 1",
                (meeting_id, label),
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None
        finally:
            await db.close()
