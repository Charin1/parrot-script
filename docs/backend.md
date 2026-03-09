# Backend

## Package Layout

- `backend/config.py`: typed runtime settings loaded from `.env`.
- `backend/main.py`: CLI wrapper for local `uvicorn` startup.
- `backend/api/`: FastAPI app, auth helpers, routes, and WebSocket manager.
- `backend/core/`: pipeline orchestration, event dataclasses, and exceptions.
- `backend/audio/`: FFmpeg capture, device discovery, and voice activity filtering.
- `backend/transcription/`: Faster-Whisper integration and transcript dataclasses.
- `backend/diarization/`: speaker embedding and clustering.
- `backend/storage/`: SQLite initialization, repositories, and vector store.
- `backend/llm/`: transcript chunking, prompts, and Ollama summarization.

## Entry Points

### API server

- ASGI app object: `backend.api.server:app`
- Local CLI wrapper: `python -m backend.main`

### API startup sequence

1. `FastAPI(..., lifespan=lifespan)` is created.
2. `lifespan()` calls `init_db()`.
3. CORS middleware is registered.
4. HTTP auth/security middleware is registered.
5. Route modules are included.
6. WebSocket endpoint is exposed at `/ws/meetings/{meeting_id}`.

## API Surface

### Health

- `GET /health`
- Purpose: unauthenticated health probe for local runtime monitoring.

### Meetings

- `POST /api/meetings/`: create a new meeting.
- `GET /api/meetings/`: list meetings ordered by newest first.
- `GET /api/meetings/{meeting_id}`: fetch one meeting.
- `PATCH /api/meetings/{meeting_id}`: update title, status, or metadata.
- `DELETE /api/meetings/{meeting_id}`: stop any active pipeline and delete meeting data.
- `POST /api/meetings/{meeting_id}/start`: start audio capture and processing.
- `POST /api/meetings/{meeting_id}/stop`: stop capture and mark the meeting complete.

### Transcript

- `GET /api/meetings/{meeting_id}/transcript?page=1&limit=100`
- Returns paginated transcript rows and total count.

### Summary

- `GET /api/meetings/{meeting_id}/summary`: fetch existing summary or generate one from transcript.
- `POST /api/meetings/{meeting_id}/summarize`: force regeneration.

### Search

- `POST /api/search`
- Body: `query`, `limit`
- Returns semantic search results from Chroma.

### WebSocket

- `GET ws://127.0.0.1:8000/ws/meetings/{meeting_id}`
- Message types:
  - `status`
  - `transcript`

## Auth and Request Filtering

File: `backend/api/auth.py`

Key functions:

- `auth_enabled()`: checks whether `API_TOKEN` is configured.
- `extract_bearer_token()`: parses bearer headers.
- `token_valid()`: constant-time token comparison.
- `verify_http_request()`: enforces auth for HTTP requests except `/health` and preflight `OPTIONS`.
- `verify_websocket_request()`: enforces auth for live socket connections.

File: `backend/api/server.py`

Key functions:

- `lifespan()`: initializes the SQLite schema.
- `health()`: returns simple health status.
- `apply_security_headers()`: sets headers like `X-Frame-Options`, `Referrer-Policy`, and `Cache-Control`.
- `security_headers()`: middleware that runs auth and applies headers.
- `websocket_endpoint()`: authenticates, registers, and drains incoming socket traffic.

## Meeting Lifecycle Internals

File: `backend/api/routes/meetings.py`

Key symbols:

- `CreateMeetingRequest`: validates creation input.
- `UpdateMeetingRequest`: validates updates.
- `_start_pipeline()`: wrapper that starts a pipeline and handles failure cleanup.
- `active_pipelines`: in-memory meeting-to-pipeline map.
- `_pipeline_start_tasks`: in-memory startup task map.

Behavior notes:

- Start requests create a `MeetingPipeline` and background startup task.
- Stop requests cancel pending startup tasks before stopping the active pipeline.
- Delete requests also cancel pending startup tasks and stop live pipelines before deleting rows.
- Pipeline start failures mark the meeting as `failed`.

## Pipeline Orchestration

File: `backend/core/pipeline.py`

Primary class: `MeetingPipeline`

Important methods:

- `start()`: loads models, starts FFmpeg capture, launches async processing loop, and emits initial status.
- `stop()`: stops capture, waits for worker shutdown, drains leftover chunks, and emits final status.
- `_process_loop()`: consumes audio chunks until shutdown.
- `_process_chunk()`: transcribes audio, assigns speaker labels, persists transcript segments, and broadcasts updates.

Pipeline dependencies:

- `AudioCapture`
- `WhisperTranscriber`
- `SpeakerClusterer`
- `SegmentsRepository`
- `SpeakersRepository`
- `ConnectionManager`

## Audio Layer

### `backend/audio/capture.py`

Class: `AudioCapture`

Responsibilities:

- build and launch the FFmpeg command
- read PCM data from stdout in a background thread
- filter silent chunks with VAD
- enqueue `AudioChunkEvent` objects for async processing
- terminate FFmpeg and join helper threads on stop

### `backend/audio/vad.py`

Class: `VoiceActivityDetector`

Responsibilities:

- detect speech on 30ms frames
- drop audio chunks with too little speech content

### `backend/audio/devices.py`

Functions:

- `_ffmpeg_device_output()`: raw OS-specific device listing via `dshow`, `avfoundation`, or `pulse`.
- `list_audio_devices()`: parse audio device names/indexes
- `find_blackhole_device()`: convenience lookup for macOS BlackHole Virtual Audio Driver

## Transcription Layer

### `backend/transcription/whisper_stream.py`

Class: `WhisperTranscriber`

Responsibilities:

- lazily load Faster-Whisper
- convert raw PCM to normalized float audio
- run transcription with word timestamps
- convert model output into local dataclasses
- expose `transcribe_async()` for use from the pipeline

### `backend/transcription/models.py`

Dataclasses:

- `Word`
- `Segment`

`Segment.confidence` converts model `avg_logprob` into a bounded `0..1` value.

## Speaker Labeling Layer

### `backend/diarization/embeddings.py`

Class: `VoiceEmbedder`

Responsibilities:

- lazy-load `resemblyzer`
- preprocess audio
- generate a fixed-length embedding vector

### `backend/diarization/speaker_cluster.py`

Class: `SpeakerClusterer`

Responsibilities:

- maintain a rolling history of labeled embeddings
- compute centroids per speaker label
- assign a prior speaker when similarity exceeds threshold
- create new labels up to `MAX_SPEAKERS`
- reset state on new meeting start

## Storage Layer

### Database bootstrap

File: `backend/storage/db.py`

Functions:

- `get_db()`: opens SQLite with WAL mode and foreign keys enabled.
- `init_db()`: applies schema on startup.

Schema summary:

- `meetings`
- `transcript_segments`
- `summaries`
- `speakers`
- index: `idx_segments_meeting`

### Repositories

#### `MeetingsRepository`

Methods:

- `create()`
- `get()`
- `list_all()`
- `update()`
- `delete()`
- `end_meeting()`

#### `SegmentsRepository`

Methods:

- `insert()`
- `get_by_meeting()`
- `get_by_meeting_paginated()`
- `count_by_meeting()`
- `get_full_text()`

#### `SpeakersRepository`

Methods:

- `upsert()`
- `rename()`
- `get_by_id()`
- `get_by_meeting()`
- `_find_by_label()`

#### `SummariesRepository`

Methods:

- `insert()`
- `get_by_id()`
- `get_by_meeting()`
- `update()`

### Vector Store

File: `backend/storage/vector_store.py`

Class: `VectorStore`

Responsibilities:

- open a persistent Chroma collection
- embed text using Chroma's default embedding function
- upsert transcript chunks and summaries
- serve semantic search results

## LLM / Summary Layer

### `backend/llm/chunker.py`

Functions:

- `estimate_tokens()`
- `_split_long_line()`
- `chunk_transcript()`

### `backend/llm/prompts.py`

Prompt constants:

- `MEETING_SUMMARY_PROMPT`
- `PARTIAL_SUMMARY_PROMPT`
- `COMBINE_SUMMARIES_PROMPT`

### `backend/llm/summarizer.py`

Class: `MeetingSummarizer`

Responsibilities:

- choose direct summary vs map-reduce summary based on transcript size
- call Ollama via HTTP
- persist new or updated summaries
- return summary metadata for routes

## Events and Exceptions

### `backend/core/events.py`

Dataclasses:

- `AudioChunkEvent`
- `TranscriptSegmentEvent`
- `MeetingStatusEvent`

### `backend/core/exceptions.py`

Custom exceptions:

- `ParrotScriptError`
- `NotFoundError`
- `OllamaUnavailableError`
- `AudioCaptureError`

## Backend Extension Points

- Add new API routes under `backend/api/routes/` and include them in `backend/api/server.py`.
- Add new persistent entities by extending `SCHEMA_SQL` and adding a repository.
- Replace or enhance diarization by swapping `SpeakerClusterer` internals.
- Add background jobs around summaries/search by extending `MeetingPipeline` or adding new route-level workflows.
