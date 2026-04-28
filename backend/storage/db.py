from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import aiosqlite

from backend.config import settings

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meetings (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at DATETIME DEFAULT (datetime('now')),
    ended_at DATETIME,
    duration_s REAL,
    status TEXT DEFAULT 'active',
    metadata TEXT,
    capture_mode TEXT DEFAULT 'private',
    ghost_mode BOOLEAN DEFAULT 1,
    source_platform TEXT,
    meeting_url TEXT,
    assistant_join_status TEXT DEFAULT 'not_requested',
    assistant_visible_name TEXT DEFAULT 'Parrot Script Assistant',
    consent_status TEXT DEFAULT 'not_needed',
    provider_session_id TEXT,
    provider_metadata TEXT,
    video_start_offset REAL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS transcript_segments (
    id TEXT PRIMARY KEY,
    meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    speaker TEXT,
    text TEXT NOT NULL,
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    confidence REAL,
    created_at DATETIME DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS summaries (
    id TEXT PRIMARY KEY,
    meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    summary TEXT,
    action_items TEXT,
    decisions TEXT,
    created_at DATETIME DEFAULT (datetime('now')),
    model_used TEXT
);

CREATE TABLE IF NOT EXISTS speakers (
    id TEXT PRIMARY KEY,
    meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    name TEXT,
    color TEXT
);

CREATE TABLE IF NOT EXISTS meeting_participants (
    id TEXT PRIMARY KEY,
    meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    external_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    is_host BOOLEAN DEFAULT 0,
    is_bot BOOLEAN DEFAULT 0,
    joined_at REAL,
    left_at REAL,
    metadata TEXT,
    created_at DATETIME DEFAULT (datetime('now')),
    UNIQUE(meeting_id, external_id)
);

CREATE TABLE IF NOT EXISTS participant_speaking_events (
    id TEXT PRIMARY KEY,
    meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    participant_id TEXT NOT NULL REFERENCES meeting_participants(id) ON DELETE CASCADE,
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    confidence REAL,
    source TEXT,
    created_at DATETIME DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS segment_participant_attribution (
    segment_id TEXT PRIMARY KEY REFERENCES transcript_segments(id) ON DELETE CASCADE,
    meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    participant_id TEXT NOT NULL REFERENCES meeting_participants(id) ON DELETE CASCADE,
    confidence REAL,
    attribution_source TEXT,
    created_at DATETIME DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_segments_meeting
    ON transcript_segments(meeting_id, start_time);
CREATE INDEX IF NOT EXISTS idx_meeting_participants_meeting
    ON meeting_participants(meeting_id);
CREATE INDEX IF NOT EXISTS idx_speaking_events_meeting
    ON participant_speaking_events(meeting_id, start_time, end_time);
CREATE INDEX IF NOT EXISTS idx_attribution_meeting
    ON segment_participant_attribution(meeting_id);
"""


@asynccontextmanager
async def get_db() -> AsyncIterator[aiosqlite.Connection]:
    """Async context manager that yields a configured SQLite connection.

    Usage::

        async with get_db() as db:
            await db.execute(...)
    """
    db_path = Path(settings.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    db = await aiosqlite.connect(db_path.as_posix(), timeout=10.0)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
    finally:
        await db.close()


async def init_db() -> None:
    async with get_db() as db:
        await db.executescript(SCHEMA_SQL)

        async with db.execute("PRAGMA table_info(meetings)") as cur:
            meeting_columns = [dict(row)["name"] for row in await cur.fetchall()]

        meeting_migrations = {
            "capture_mode": "ALTER TABLE meetings ADD COLUMN capture_mode TEXT DEFAULT 'private'",
            "ghost_mode": "ALTER TABLE meetings ADD COLUMN ghost_mode BOOLEAN DEFAULT 1",
            "source_platform": "ALTER TABLE meetings ADD COLUMN source_platform TEXT",
            "meeting_url": "ALTER TABLE meetings ADD COLUMN meeting_url TEXT",
            "assistant_join_status": "ALTER TABLE meetings ADD COLUMN assistant_join_status TEXT DEFAULT 'not_requested'",
            "assistant_visible_name": "ALTER TABLE meetings ADD COLUMN assistant_visible_name TEXT DEFAULT 'Parrot Script Assistant'",
            "consent_status": "ALTER TABLE meetings ADD COLUMN consent_status TEXT DEFAULT 'not_needed'",
            "provider_session_id": "ALTER TABLE meetings ADD COLUMN provider_session_id TEXT",
            "provider_metadata": "ALTER TABLE meetings ADD COLUMN provider_metadata TEXT",
        }
        for column, sql in meeting_migrations.items():
            if column not in meeting_columns:
                await db.execute(sql)

        # Safe migration for video recording columns
        video_migrations = {
            "recording_type": "ALTER TABLE meetings ADD COLUMN recording_type TEXT DEFAULT 'audio'",
            "video_resolution": "ALTER TABLE meetings ADD COLUMN video_resolution TEXT",
            "has_video": "ALTER TABLE meetings ADD COLUMN has_video BOOLEAN DEFAULT 0",
            "video_start_offset": "ALTER TABLE meetings ADD COLUMN video_start_offset REAL DEFAULT 0.0",
        }
        for column, sql in video_migrations.items():
            if column not in meeting_columns:
                await db.execute(sql)

        # Safe migration for new is_bookmarked column
        async with db.execute("PRAGMA table_info(transcript_segments)") as cur:
            columns = [dict(row)["name"] for row in await cur.fetchall()]
            if "is_bookmarked" not in columns:
                await db.execute("ALTER TABLE transcript_segments ADD COLUMN is_bookmarked BOOLEAN DEFAULT 0")

        # Safe migration for new summary intelligence columns
        async with db.execute("PRAGMA table_info(summaries)") as cur:
            sum_columns = [dict(row)["name"] for row in await cur.fetchall()]
            summary_fields = {
                "summary": "ALTER TABLE summaries ADD COLUMN summary TEXT",
                "action_items": "ALTER TABLE summaries ADD COLUMN action_items TEXT",
                "decisions": "ALTER TABLE summaries ADD COLUMN decisions TEXT",
            }
            for column, sql in summary_fields.items():
                if column not in sum_columns:
                    await db.execute(sql)

        await db.commit()
