# Agent Guide

This document is for future agents or developers who need to make targeted changes quickly.

## Start Here

1. Read `docs/architecture.md`.
2. Read `docs/file-index.md`.
3. If the task is backend-heavy, read `docs/backend.md`.
4. If the task is frontend-heavy, read `docs/frontend.md`.

## High-Impact Files

### Backend runtime and security

- `backend/config.py`: runtime defaults and env parsing
- `backend/api/auth.py`: HTTP and WebSocket auth enforcement
- `backend/api/server.py`: app assembly, middleware, and WebSocket endpoint
- `backend/core/pipeline.py`: end-to-end recording/transcription flow
- `backend/storage/db.py`: schema and DB init

### Frontend runtime and network behavior

- `frontend/react-app/src/App.tsx`: shared app state and orchestration
- `frontend/react-app/src/api/client.ts`: all REST calls and error formatting
- `frontend/react-app/src/hooks/useWebSocket.ts`: live stream reliability and transcript buffering
- `frontend/react-app/src/hooks/useLocalRuntime.ts`: local backend health probing
- `frontend/react-app/vite.config.ts`: loopback binding and proxy setup

## Change Impact Map

### If you change auth

Check these files:

- `backend/api/auth.py`
- `backend/api/server.py`
- `frontend/react-app/src/api/client.ts`
- `frontend/react-app/src/hooks/useWebSocket.ts`
- `frontend/react-app/src/App.tsx`
- `tests/test_api.py`

### If you change meeting lifecycle behavior

Check these files:

- `backend/api/routes/meetings.py`
- `backend/core/pipeline.py`
- `backend/storage/repositories/meetings.py`
- `frontend/react-app/src/App.tsx`
- `frontend/react-app/src/components/MeetingControls.tsx`
- `frontend/react-app/src/components/MeetingList.tsx`

### If you change transcript behavior

Check these files:

- `backend/transcription/whisper_stream.py`
- `backend/storage/repositories/segments.py`
- `backend/api/routes/transcripts.py`
- `frontend/react-app/src/hooks/useWebSocket.ts`
- `frontend/react-app/src/components/LiveTranscript.tsx`

### If you change summarization or search

Check these files:

- `backend/llm/summarizer.py`
- `backend/llm/chunker.py`
- `backend/llm/prompts.py`
- `backend/api/routes/summaries.py`
- `backend/storage/vector_store.py`
- `backend/api/routes/search.py`
- `frontend/react-app/src/components/SummaryPanel.tsx`
- `frontend/react-app/src/components/SearchBar.tsx`

### If you change audio capture or diarization

Check these files:

- `backend/audio/capture.py`
- `backend/audio/vad.py`
- `backend/audio/devices.py`
- `backend/diarization/embeddings.py`
- `backend/diarization/speaker_cluster.py`
- `backend/core/pipeline.py`

## Known Constraints

- Audio capture is dynamically cross-platform (macOS `avfoundation`, Windows `dshow`, Linux `pulse`).
- WebSocket auth shares the same token as REST auth.
- The frontend assumes loopback-bound services.
- `GET /health` is intentionally public for local health checks.
- `SegmentsRepository.get_full_text()` still materializes all transcript rows for summaries.
- Search indexing currently happens during summary generation, not at transcript ingest time.

## Safe Editing Guidelines

- Keep auth failures returning plain HTTP `401` JSON, not uncaught middleware exceptions.
- Preserve loopback defaults unless the user explicitly wants remote exposure.
- When touching the WebSocket hook, avoid reintroducing cross-instance socket close bugs.
- When touching delete behavior, preserve child-row cleanup and FK-safe deletion.
- If you add a new API route, update docs and tests in the same change.
- If you add a new persisted field, update the schema, repository, types, and any affected UI.

## Suggested Validation After Changes

### Backend changes

```bash
PYTHONPYCACHEPREFIX=/tmp/parrot-script-pycache .venv/bin/python -m pytest -q
```

### Frontend changes

```bash
cd frontend/react-app
npm run typecheck
npm run build
```

### Audio or model changes

```bash
.venv/bin/python scripts/list_audio_devices.py
.venv/bin/python scripts/test_whisper.py --file <wav>
.venv/bin/python scripts/test_ollama.py
```
