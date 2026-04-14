from __future__ import annotations

from uuid import uuid4

from backend.storage.db import get_db


class ParticipantsRepository:
    async def upsert(
        self,
        meeting_id: str,
        *,
        external_id: str,
        display_name: str,
        is_host: bool = False,
        is_bot: bool = False,
        joined_at: float | None = None,
        left_at: float | None = None,
        metadata: str | None = None,
    ) -> dict:
        async with get_db() as db:
            async with db.execute(
                """
                SELECT * FROM meeting_participants
                WHERE meeting_id = ? AND external_id = ?
                """,
                (meeting_id, external_id),
            ) as cur:
                existing = await cur.fetchone()

            if existing:
                participant_id = dict(existing)["id"]
                await db.execute(
                    """
                    UPDATE meeting_participants
                    SET display_name = ?,
                        is_host = ?,
                        is_bot = ?,
                        joined_at = ?,
                        left_at = ?,
                        metadata = ?
                    WHERE id = ?
                    """,
                    (
                        display_name,
                        1 if is_host else 0,
                        1 if is_bot else 0,
                        joined_at,
                        left_at,
                        metadata,
                        participant_id,
                    ),
                )
                await db.commit()
                return await self._get(participant_id)

            participant_id = str(uuid4())
            await db.execute(
                """
                INSERT INTO meeting_participants(
                    id, meeting_id, external_id, display_name, is_host, is_bot, joined_at, left_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    participant_id,
                    meeting_id,
                    external_id,
                    display_name,
                    1 if is_host else 0,
                    1 if is_bot else 0,
                    joined_at,
                    left_at,
                    metadata,
                ),
            )
            await db.commit()

        return await self._get(participant_id)

    async def list_by_meeting(self, meeting_id: str) -> list[dict]:
        async with get_db() as db:
            async with db.execute(
                """
                SELECT * FROM meeting_participants
                WHERE meeting_id = ?
                ORDER BY display_name COLLATE NOCASE ASC
                """,
                (meeting_id,),
            ) as cur:
                rows = await cur.fetchall()
                return [self._normalize(row) for row in rows]

    async def get_by_external_id(self, meeting_id: str, external_id: str) -> dict | None:
        async with get_db() as db:
            async with db.execute(
                """
                SELECT * FROM meeting_participants
                WHERE meeting_id = ? AND external_id = ?
                """,
                (meeting_id, external_id),
            ) as cur:
                row = await cur.fetchone()
                return self._normalize(row) if row else None

    async def replace_speaking_events(
        self,
        meeting_id: str,
        *,
        events: list[dict],
        source: str = "native_provider_event",
    ) -> int:
        """Replace speaking events for a meeting and return inserted count."""
        async with get_db() as db:
            async with db.execute(
                """
                SELECT id, external_id
                FROM meeting_participants
                WHERE meeting_id = ?
                """,
                (meeting_id,),
            ) as cur:
                participant_rows = await cur.fetchall()
                participant_id_by_external: dict[str, str] = {
                    str(dict(row)["external_id"]): str(dict(row)["id"]) for row in participant_rows
                }

            await db.execute(
                "DELETE FROM participant_speaking_events WHERE meeting_id = ?",
                (meeting_id,),
            )

            inserted = 0
            for event in events:
                participant_external_id = str(event["participant_external_id"])
                participant_id = participant_id_by_external.get(participant_external_id)
                if participant_id is None:
                    continue
                await db.execute(
                    """
                    INSERT INTO participant_speaking_events(
                        id, meeting_id, participant_id, start_time, end_time, confidence, source
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid4()),
                        meeting_id,
                        participant_id,
                        float(event["start_time"]),
                        float(event["end_time"]),
                        event.get("confidence"),
                        source,
                    ),
                )
                inserted += 1

            await db.commit()
            return inserted

    async def get_speaking_events(self, meeting_id: str) -> list[dict]:
        async with get_db() as db:
            async with db.execute(
                """
                SELECT
                    pse.*,
                    mp.external_id AS participant_external_id,
                    mp.display_name AS participant_name
                FROM participant_speaking_events pse
                JOIN meeting_participants mp ON mp.id = pse.participant_id
                WHERE pse.meeting_id = ?
                ORDER BY pse.start_time ASC
                """,
                (meeting_id,),
            ) as cur:
                rows = await cur.fetchall()
                return [dict(row) for row in rows]

    async def clear_segment_attributions(self, meeting_id: str) -> None:
        async with get_db() as db:
            await db.execute(
                "DELETE FROM segment_participant_attribution WHERE meeting_id = ?",
                (meeting_id,),
            )
            await db.commit()

    async def insert_segment_attribution(
        self,
        meeting_id: str,
        *,
        segment_id: str,
        participant_id: str,
        confidence: float,
        attribution_source: str,
    ) -> None:
        async with get_db() as db:
            await db.execute(
                """
                INSERT INTO segment_participant_attribution(
                    segment_id, meeting_id, participant_id, confidence, attribution_source
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(segment_id) DO UPDATE SET
                    participant_id = excluded.participant_id,
                    confidence = excluded.confidence,
                    attribution_source = excluded.attribution_source,
                    created_at = datetime('now')
                """,
                (segment_id, meeting_id, participant_id, confidence, attribution_source),
            )
            await db.commit()

    async def replace_segment_attributions(self, meeting_id: str, attributions: list[dict]) -> None:
        async with get_db() as db:
            await db.execute(
                "DELETE FROM segment_participant_attribution WHERE meeting_id = ?",
                (meeting_id,),
            )
            for item in attributions:
                await db.execute(
                    """
                    INSERT INTO segment_participant_attribution(
                        segment_id, meeting_id, participant_id, confidence, attribution_source
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(segment_id) DO UPDATE SET
                        participant_id = excluded.participant_id,
                        confidence = excluded.confidence,
                        attribution_source = excluded.attribution_source,
                        created_at = datetime('now')
                    """,
                    (
                        item["segment_id"],
                        meeting_id,
                        item["participant_id"],
                        item["confidence"],
                        item["attribution_source"],
                    ),
                )
            await db.commit()

    async def _get(self, participant_id: str) -> dict:
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM meeting_participants WHERE id = ?",
                (participant_id,),
            ) as cur:
                row = await cur.fetchone()
                return self._normalize(row) if row else {"id": participant_id}

    @staticmethod
    def _normalize(row) -> dict:
        value = dict(row)
        value["is_host"] = bool(value.get("is_host", False))
        value["is_bot"] = bool(value.get("is_bot", False))
        return value
