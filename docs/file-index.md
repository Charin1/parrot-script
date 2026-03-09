# File Index

This index maps every source file to its main purpose and the symbols that matter when changing it.

## Backend

- `backend/__init__.py`: package marker.
- `backend/config.py`: typed settings loader. Symbols: `Settings`, `settings`.
- `backend/main.py`: local CLI startup wrapper. Symbols: `parse_args`, `resolve_reload`, `main`.
- `backend/core/__init__.py`: package marker.
- `backend/core/events.py`: pipeline event dataclasses. Symbols: `AudioChunkEvent`, `TranscriptSegmentEvent`, `MeetingStatusEvent`.
- `backend/core/exceptions.py`: custom backend exceptions. Symbols: `ParrotScriptError`, `NotFoundError`, `OllamaUnavailableError`, `AudioCaptureError`.
- `backend/core/pipeline.py`: end-to-end meeting processing pipeline. Symbols: `MeetingPipeline.start`, `MeetingPipeline.stop`, `MeetingPipeline._process_loop`, `MeetingPipeline._process_chunk`.
- `backend/api/__init__.py`: package marker.
- `backend/api/auth.py`: bearer-token auth helpers for HTTP and WebSocket. Symbols: `auth_enabled`, `extract_bearer_token`, `token_valid`, `verify_http_request`, `verify_websocket_request`.
- `backend/api/server.py`: FastAPI app assembly. Symbols: `app`, `lifespan`, `health`, `apply_security_headers`, `security_headers`, `websocket_endpoint`.
- `backend/api/websocket.py`: WebSocket connection registry and broadcasting. Symbols: `ConnectionManager`, `manager`.
- `backend/api/routes/__init__.py`: package marker.
- `backend/api/routes/meetings.py`: meeting CRUD and recording lifecycle routes. Symbols: `CreateMeetingRequest`, `UpdateMeetingRequest`, `_start_pipeline`, `create_meeting`, `list_meetings`, `get_meeting`, `update_meeting`, `delete_meeting`, `start_recording`, `stop_recording`, `active_pipelines`, `_pipeline_start_tasks`.
- `backend/api/routes/transcripts.py`: transcript pagination route. Symbols: `get_transcript`.
- `backend/api/routes/summaries.py`: summary fetch/generate routes. Symbols: `get_vector_store`, `_require_meeting`, `get_or_create_summary`, `force_summarize`.
- `backend/api/routes/search.py`: semantic search route. Symbols: `SearchRequest`, `get_vector_store`, `semantic_search`.
- `backend/audio/__init__.py`: package marker.
- `backend/audio/capture.py`: FFmpeg capture and chunk queueing. Symbols: `AudioCapture`, `AudioCapture.start`, `AudioCapture.stop`, `AudioCapture._build_ffmpeg_cmd`, `AudioCapture._reader_thread`.
- `backend/audio/devices.py`: device enumeration helpers. Symbols: `_ffmpeg_device_output`, `list_audio_devices`, `find_blackhole_device`.
- `backend/audio/vad.py`: speech filtering. Symbols: `VoiceActivityDetector`, `is_speech`, `filter_silent_chunks`.
- `backend/transcription/__init__.py`: package marker.
- `backend/transcription/models.py`: transcript dataclasses. Symbols: `Word`, `Segment`, `Segment.confidence`.
- `backend/transcription/whisper_stream.py`: Faster-Whisper integration. Symbols: `WhisperTranscriber`, `load_model`, `transcribe`, `transcribe_async`.
- `backend/diarization/__init__.py`: package marker.
- `backend/diarization/embeddings.py`: speaker embedding wrapper. Symbols: `VoiceEmbedder`, `load`, `embed`.
- `backend/diarization/speaker_cluster.py`: heuristic speaker clustering. Symbols: `SpeakerClusterer`, `assign_speaker`, `get_centroid`, `reset`, `unique_speakers`, `_new_label`, `_cosine_similarity`.
- `backend/llm/__init__.py`: package marker.
- `backend/llm/chunker.py`: transcript chunk planning. Symbols: `estimate_tokens`, `_split_long_line`, `chunk_transcript`.
- `backend/llm/prompts.py`: Ollama prompt templates. Symbols: `MEETING_SUMMARY_PROMPT`, `PARTIAL_SUMMARY_PROMPT`, `COMBINE_SUMMARIES_PROMPT`.
- `backend/llm/summarizer.py`: Ollama summary orchestration and persistence. Symbols: `MeetingSummarizer`, `summarize`, `_call_ollama`.
- `backend/storage/__init__.py`: package marker.
- `backend/storage/db.py`: SQLite connection and schema bootstrap. Symbols: `SCHEMA_SQL`, `get_db`, `init_db`.
- `backend/storage/vector_store.py`: Chroma wrapper. Symbols: `VectorStore`, `embed_text`, `add_meeting`, `search`.
- `backend/storage/repositories/__init__.py`: package marker.
- `backend/storage/repositories/meetings.py`: meeting persistence. Symbols: `MeetingsRepository`, `create`, `get`, `list_all`, `update`, `delete`, `end_meeting`.
- `backend/storage/repositories/segments.py`: transcript segment persistence. Symbols: `SegmentsRepository`, `insert`, `get_by_meeting`, `get_by_meeting_paginated`, `count_by_meeting`, `get_full_text`.
- `backend/storage/repositories/speakers.py`: speaker persistence. Symbols: `SpeakersRepository`, `upsert`, `rename`, `get_by_id`, `get_by_meeting`, `_find_by_label`.
- `backend/storage/repositories/summaries.py`: summary persistence. Symbols: `SummariesRepository`, `insert`, `get_by_id`, `get_by_meeting`, `update`.

## Frontend

- `frontend/react-app/src/main.tsx`: app bootstrap and initial theme resolution.
- `frontend/react-app/src/App.tsx`: main UI orchestration, data loading, auth panel, workspace switching.
- `frontend/react-app/src/index.css`: global design tokens, layout, and responsive styles.
- `frontend/react-app/src/api/client.ts`: axios client and token helpers. Symbols: `getApiToken`, `setApiToken`, `clearApiToken`, `formatApiError`, `api`.
- `frontend/react-app/src/types/models.ts`: shared API/UI types. Symbols: `MeetingLifecycleStatus`, `Meeting`, `Segment`, `Summary`, `MeetingStatus`, `SearchResult`.
- `frontend/react-app/src/hooks/useTheme.ts`: theme persistence and system-theme tracking. Symbols: `ThemeMode`, `useTheme`, `readStoredMode`, `resolveTheme`.
- `frontend/react-app/src/hooks/useLocalRuntime.ts`: browser/backend health probe. Symbols: `BackendReachability`, `useLocalRuntime`.
- `frontend/react-app/src/hooks/useWebSocket.ts`: live transcript stream management. Symbols: `StreamConnectionState`, `useWebSocket`, `segmentKey`, `appendSegment`.
- `frontend/react-app/src/components/MeetingControls.tsx`: selected-meeting control bar and live timer. Symbols: `MeetingControls`, `formatDuration`.
- `frontend/react-app/src/components/MeetingList.tsx`: meeting selector list. Symbols: `MeetingList`, `formatDate`, `statusClass`.
- `frontend/react-app/src/components/PastMeetingsDashboard.tsx`: historical meeting dashboard. Symbols: `PastMeetingsDashboard`, `formatDate`, `formatDuration`.
- `frontend/react-app/src/components/LiveTranscript.tsx`: transcript rendering panel. Symbols: `LiveTranscript`, `colorForSpeaker`.
- `frontend/react-app/src/components/SummaryPanel.tsx`: summary rendering and regenerate action. Symbols: `SummaryPanel`.
- `frontend/react-app/src/components/SearchBar.tsx`: semantic search UI with request cancellation. Symbols: `SearchBar`.
- `frontend/react-app/src/components/RuntimeStatusPanel.tsx`: browser/backend/socket status UI. Symbols: `RuntimeStatusPanel`, `backendLabel`, `backendBadge`, `streamLabel`, `streamBadge`.
- `frontend/react-app/src/components/ThemeSelector.tsx`: theme segmented control. Symbols: `ThemeSelector`, `OPTIONS`.
- `frontend/react-app/src/components/icons.tsx`: reusable SVG icon primitives. Symbols: `IconBase`, `SunIcon`, `MoonIcon`, `DesktopIcon`, `PlayIcon`, `StopIcon`, `PlusIcon`, `SearchIcon`, `SparklesIcon`.

## Frontend Build and Static Files

- `frontend/react-app/index.html`: HTML shell and favicon reference.
- `frontend/react-app/vite.config.ts`: loopback binding and backend proxy setup.
- `frontend/react-app/package.json`: frontend package metadata and scripts.
- `frontend/react-app/package-lock.json`: npm lockfile.
- `frontend/react-app/tsconfig.json`: main TypeScript config.
- `frontend/react-app/tsconfig.node.json`: TypeScript config for Vite/node-side files.
- `frontend/react-app/public/parrot-script-logo.svg`: project logo asset.

## Scripts

- `scripts/start_meeting.sh`: convenience launcher for Ollama and the backend.
- `scripts/list_audio_devices.py`: helper to list OS-specific audio devices (`avfoundation`/`dshow`/`pulse`). Symbols: `main`.
- `scripts/test_ollama.py`: local Ollama smoke test. Symbols: `main`.
- `scripts/test_whisper.py`: local Whisper WAV smoke test. Symbols: `_resample_if_needed`, `main`.

## Tests

- `tests/__init__.py`: package marker.
- `tests/test_api.py`: API/auth/pagination/deletion regression tests. Symbols: `setup_test_db`, `auth_headers`, `test_create_and_list_meetings`, `test_delete_meeting_with_related_rows`, `test_transcript_pagination`.
- `tests/test_audio.py`: VAD behavior test.
- `tests/test_transcription.py`: transcript confidence bounds test.
- `tests/test_integration.py`: fixture-presence check for the full integration path.

## Non-Code Project Files

- `README.md`: end-user and developer setup/runtime guide.
- `.env.example`: reference environment template.
- `.env`: local environment file.
- `requirements.txt`: Python dependency list.
- `pyproject.toml`: Python project metadata and pytest config.
- `.gitignore`: local artifacts and dependency exclusion rules.
- `task.md`: task log / plan artifact from the build process.
- `meeting_assistant_plan.md`: larger planning artifact from earlier implementation phases.
