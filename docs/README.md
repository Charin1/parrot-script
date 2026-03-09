# Documentation

This folder is the working documentation set for `parrot-script`.

Use these documents in this order:

1. [architecture.md](./architecture.md): end-to-end system design, runtime boundaries, and primary data flow.
2. [backend.md](./backend.md): FastAPI, pipeline, storage, transcription, diarization, summarization, and search internals.
3. [frontend.md](./frontend.md): React state model, hooks, components, and UI runtime behavior.
4. [operations.md](./operations.md): setup, run commands, environment, network model, testing, and troubleshooting.
5. [file-index.md](./file-index.md): file-by-file purpose and symbol index.
6. [agent-guide.md](./agent-guide.md): change-impact map and handoff notes for future agents.

## Audience

- Developers new to the repo: start with `architecture.md`.
- Developers changing API or pipeline code: read `backend.md` and `agent-guide.md`.
- Developers changing UI or network behavior: read `frontend.md` and `agent-guide.md`.
- Agents picking up work later: read `agent-guide.md` and `file-index.md` first.

## Current System Shape

- Runtime is local-first and loopback-bound by default.
- Backend API uses FastAPI with bearer-token auth.
- Frontend uses React + Vite with a local proxy to the backend.
- Audio capture uses FFmpeg `avfoundation` (macOS), `dshow` (Windows), or `pulse`/`alsa` (Linux).
- Transcription uses Faster-Whisper.
- Speaker labeling uses Resemblyzer embeddings and cosine-similarity clustering.
- Summaries use Ollama over HTTP.
- Persistence uses SQLite and Chroma.
