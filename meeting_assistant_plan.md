# Local AI Meeting Assistant — Full Implementation Plan
> Privacy-first · Fully local · Apple Silicon optimized · Mac M-series 16 GB RAM

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [System Requirements](#2-system-requirements)
3. [Detailed Architecture](#3-detailed-architecture)
4. [Data Flow Diagrams](#4-data-flow-diagrams)
5. [Technology Stack](#5-technology-stack)
6. [Model Selection & Benchmarks](#6-model-selection--benchmarks)
7. [Component Specifications](#7-component-specifications)
8. [Database Schema](#8-database-schema)
9. [API Contracts](#9-api-contracts)
10. [Project File Structure](#10-project-file-structure)
11. [Memory & Performance Budget](#11-memory--performance-budget)
12. [Implementation Phases](#12-implementation-phases)
13. [Configuration Reference](#13-configuration-reference)
14. [Error Handling & Resilience](#14-error-handling--resilience)
15. [Testing Strategy](#15-testing-strategy)
16. [Key Design Principles](#16-key-design-principles)

---

## 1. Project Overview

Build a **fully local AI meeting assistant** that captures, transcribes, diarizes, and summarizes meetings from Google Meet, Zoom, or Teams — with zero data leaving the machine.

### Core Capabilities

| Capability              | Description                                        |
|-------------------------|----------------------------------------------------|
| Audio capture           | System-level audio capture via virtual audio device |
| Real-time transcription | Sub-5s latency using Faster-Whisper                |
| Speaker diarization     | Voice-embedding clustering (no cloud)              |
| AI summarization        | Mistral 7B via Ollama                              |
| Local storage           | SQLite + optional vector search                    |
| Live UI                 | Streaming dashboard with React or Streamlit        |

---

## 2. System Requirements

### Hardware Target

```
Machine : MacBook Pro / Air — Apple Silicon (M1 / M2 / M3 / M4)
RAM     : 16 GB unified memory
Storage : 10 GB free (models + transcripts)
OS      : macOS 13+ (Ventura or later)
```

### Software Prerequisites

```
Python      3.11+
FFmpeg      6.0+       (brew install ffmpeg)
Ollama      0.3+       (brew install ollama)
Node.js     20+        (optional — only for React frontend)
BlackHole   2ch        (virtual audio — brew install blackhole-2ch)
```

### Performance Targets

| Metric                       | Target             |
|------------------------------|--------------------|
| Transcription latency        | ≤ 3–5 seconds      |
| Peak RAM (all components)    | ≤ 8 GB             |
| CPU during transcription     | ≤ 60% (4 cores)    |
| LLM summary generation time  | ≤ 30 seconds       |
| Storage per 1-hour meeting   | ≤ 2 MB (transcript)|

---

## 3. Detailed Architecture

### 3.1 High-Level System Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        MEETING SOURCES                           │
│           Google Meet │ Zoom │ Teams │ Local recording           │
└────────────────────────────┬─────────────────────────────────────┘
                             │ system audio
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                    AUDIO CAPTURE LAYER                           │
│                                                                  │
│   BlackHole 2ch (virtual device)                                 │
│   ↓                                                              │
│   FFmpeg avfoundation driver → PCM 16kHz mono stream            │
│   ↓                                                              │
│   Audio Chunker (30-second sliding window + VAD overlap)         │
└────────────────────────────┬─────────────────────────────────────┘
                             │ raw audio chunks (WAV bytes)
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                TRANSCRIPTION + DIARIZATION LAYER                 │
│                                                                  │
│   ┌────────────────────┐    ┌──────────────────────────────────┐ │
│   │  Faster-Whisper    │    │  Speaker Diarization             │ │
│   │  (small.en model)  │    │  - Resemblyzer embeddings        │ │
│   │                    │    │  - Agglomerative clustering      │ │
│   │  VAD → segments    │    │  - Speaker label assignment      │ │
│   │  → word timestamps │    │                                  │ │
│   └────────┬───────────┘    └───────────┬──────────────────────┘ │
│            │                            │                        │
│            └────────────┬───────────────┘                        │
│                         │ merged segments (text + speaker)       │
└─────────────────────────┼────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATION LAYER (FastAPI)                 │
│                                                                  │
│   WebSocket Server  ──────────────────────────►  Live UI        │
│   REST API          ──────────────────────────►  History UI     │
│   Event Bus         (in-process asyncio queue)                  │
└─────────────────────────┬────────────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          │               │               │
          ▼               ▼               ▼
┌─────────────┐  ┌──────────────┐  ┌──────────────────────┐
│   SQLite DB  │  │  Ollama LLM  │  │  Vector Store        │
│             │  │  (Mistral 7B) │  │  (ChromaDB / FAISS)  │
│  meetings   │  │              │  │                      │
│  transcripts│  │  summarizer  │  │  semantic search     │
│  summaries  │  │  action items│  │  RAG queries         │
│  speakers   │  │  follow-ups  │  │                      │
└─────────────┘  └──────────────┘  └──────────────────────┘
```

---

### 3.2 Component Interaction Diagram

```
capture.py ──(audio bytes queue)──► whisper_stream.py
                                          │
                                          ├──(raw segments)──► speaker_cluster.py
                                          │                          │
                                          └──(merged segments)◄──────┘
                                                    │
                                                    ▼
                                             db.py (SQLite write)
                                                    │
                                          ┌─────────┴──────────┐
                                          │                    │
                                    server.py             summarizer.py
                                   (WebSocket             (Ollama call)
                                    broadcast)                 │
                                          │                    │
                                          ▼                    ▼
                                      dashboard             summaries
                                      (live feed)          (stored in DB)
```

---

### 3.3 Audio Capture Detail

```
macOS System Audio
       │
       ▼
BlackHole 2ch (virtual loopback device)
       │
       ▼  (avfoundation source)
FFmpeg → PCM s16le, 16000 Hz, mono, pipe:1
       │
       ▼
Python subprocess.Popen reading stdout
       │
       ▼
AudioChunker
  - buffer audio bytes
  - every N seconds OR silence detected → emit chunk
       │
       ▼
asyncio.Queue  ──► transcription worker
```

---

### 3.4 Transcription Pipeline Detail

```
audio chunk (bytes)
       │
       ▼
numpy float32 normalization  (-1.0 to +1.0)
       │
       ▼
Faster-Whisper .transcribe()
  - beam_size = 5
  - word_timestamps = True
  - vad_filter = True           ← removes silence chunks
  - language = "en"             ← or auto-detect
       │
       ▼
List[Segment]  (start, end, text, words[])
       │
       ▼
Segment buffer  ← merge short adjacent segments
       │
       ▼
Emit TranscriptEvent → queue
```

---

### 3.5 Speaker Diarization Detail

```
audio chunk (full segment audio slice)
       │
       ▼
Resemblyzer.preprocess_wav()
       │
       ▼
VoiceEncoder.embed_utterance()  → 256-dim embedding
       │
       ▼
Embedding buffer (rolling window of last N embeddings)
       │
       ▼
AgglomerativeClustering (cosine distance, threshold=0.75)
       │
       ▼
Speaker label map  {embedding_id → "Speaker 1" / "Speaker 2" ...}
       │
       ▼
Merge label with Whisper segment → annotated transcript line
```

---

### 3.6 LLM Summarization Detail

```
POST /api/meetings/{id}/summarize
       │
       ▼
Load full transcript from SQLite
       │
       ▼
Chunk transcript if > 4000 tokens  ← map-reduce strategy
       │
  ┌────┴─────┐
  │  chunk 1  │ → Ollama partial summary
  │  chunk 2  │ → Ollama partial summary
  │  ...      │
  └────┬─────┘
       │
       ▼
Combine partial summaries → final Ollama pass
       │
       ▼
Structured markdown output:
  ## Summary
  ## Key Decisions
  ## Action Items
  ## Risks
  ## Next Steps
       │
       ▼
Store in summaries table (SQLite)
Optionally embed in ChromaDB for search
```

---

## 4. Data Flow Diagrams

### 4.1 Real-Time Transcription Flow

```
t=0s  Audio capture starts
       │
t=5s  First 5-second chunk emitted
       ├──► Whisper transcribes → "Hello everyone, let's get started"
       ├──► Speaker assigned → Speaker 1
       ├──► Written to DB
       └──► WebSocket pushes to UI
       │
t=10s Next chunk emitted
       ├──► Transcript continues appending
       └──► UI updates live
       │
t=60m Meeting ends
       ├──► Final transcript flushed
       └──► Summarization triggered
```

### 4.2 Post-Meeting Summary Flow

```
User clicks "Generate Summary"
       │
       ▼
GET /api/meetings/{id}/transcript  → full text
       │
       ▼
Token count > 3500?
  YES → split into chunks → parallel Ollama calls → merge
  NO  → single Ollama call
       │
       ▼
Structured JSON parsed from LLM output
       │
       ▼
Store in summaries table
       │
       ▼
Embed summary vector in ChromaDB
       │
       ▼
Return to frontend
```

---

## 5. Technology Stack

| Layer              | Technology              | Version  | Justification                                    |
|--------------------|-------------------------|----------|--------------------------------------------------|
| Runtime            | Python                  | 3.11+    | async support, ML ecosystem                      |
| API Server         | FastAPI + uvicorn       | 0.110+   | async WebSocket + REST, minimal overhead         |
| Audio Capture      | FFmpeg + avfoundation   | 6.0+     | only reliable system audio tap on macOS          |
| Virtual Audio      | BlackHole 2ch           | 0.6+     | zero-latency system audio loopback               |
| Transcription      | faster-whisper          | 1.0+     | 4× faster than openai-whisper, Metal support     |
| Speaker Embedding  | resemblyzer             | 0.1.3    | lightweight 256-dim voice embeddings             |
| Clustering         | scikit-learn            | 1.4+     | AgglomerativeClustering, no extra deps           |
| LLM                | Ollama                  | 0.3+     | local inference, model management                |
| LLM Model          | mistral:7b-instruct     | Q4_K_M   | best quality/RAM tradeoff at 5 GB                |
| Database           | SQLite + aiosqlite      | 3.45+    | zero-server, async, reliable                     |
| Vector Store       | ChromaDB                | 0.5+     | embedded mode, no server needed                  |
| Frontend           | React + Vite            | React 18 | real-time WebSocket UI                           |
| Alt Frontend       | Streamlit               | 1.35+    | rapid prototyping option                         |
| Config             | python-dotenv + pydantic| —        | typed settings                                   |
| Audio processing   | numpy + soundfile       | —        | PCM manipulation                                 |

---

## 6. Model Selection & Benchmarks

### 6.1 Whisper Models (Speech-to-Text)

| Model        | RAM    | Speed (relative) | WER (en) | Recommendation         |
|--------------|--------|------------------|----------|------------------------|
| tiny.en      | 0.5 GB | 10×              | 8%       | Too inaccurate         |
| base.en      | 0.7 GB | 7×               | 6%       | Acceptable fallback    |
| **small.en** | **1.5 GB** | **4×**       | **4%**   | **Default — best fit** |
| medium.en    | 3.0 GB | 2×               | 3%       | If RAM allows          |
| large-v3     | 6.0 GB | 1×               | 2%       | Overkill for meetings  |

> **Default:** `small.en` with `compute_type=int8` on CPU (Metal via ctranslate2 on Apple Silicon)

### 6.2 Ollama LLM Models

| Model              | Quant   | RAM    | Quality | Recommendation            |
|--------------------|---------|--------|---------|---------------------------|
| phi3:mini          | Q4      | 2.5 GB | Good    | Lightweight option        |
| **mistral:7b**     | **Q4_K_M** | **5 GB** | **Best** | **Default**          |
| llama3:8b          | Q4_K_M  | 6 GB   | Excellent| If RAM available         |
| llama3.1:8b        | Q4_K_M  | 6 GB   | Excellent| Best for summaries       |
| gemma2:9b          | Q4_K_M  | 7 GB   | Good    | Too close to RAM limit    |

> **Default:** `mistral:7b-instruct-q4_K_M` — 5 GB, excellent instruction following

---

## 7. Component Specifications

### 7.1 Audio Capture Service (`backend/audio/capture.py`)

**Responsibilities:**
- Launch FFmpeg subprocess pointing to BlackHole 2ch
- Read stdout as raw PCM bytes
- Buffer into time-based chunks (default: 30 seconds)
- Apply Voice Activity Detection (webrtcvad) to skip silent chunks
- Push chunks to `asyncio.Queue`

**Key classes:**

```python
class AudioCapture:
    device_index: int           # BlackHole device index
    sample_rate: int = 16000
    chunk_seconds: int = 30
    queue: asyncio.Queue

    async def start() -> None
    async def stop() -> None
    def _read_ffmpeg_stdout() -> None  # threaded
```

**FFmpeg command:**
```bash
ffmpeg -f avfoundation -i ":{DEVICE_INDEX}" \
       -ac 1 -ar 16000 -acodec pcm_s16le \
       -f s16le -bufsize 65536 pipe:1
```

---

### 7.2 Transcription Service (`backend/transcription/whisper_stream.py`)

**Responsibilities:**
- Consume audio chunks from queue
- Run Faster-Whisper inference
- Return segments with timestamps and word-level timing
- Handle model loading + warm-up

**Key classes:**

```python
class WhisperTranscriber:
    model_size: str = "small.en"
    compute_type: str = "int8"    # int8 for CPU, float16 for Metal
    device: str = "cpu"           # cpu recommended for stability

    async def transcribe(chunk: bytes) -> List[Segment]
    def load_model() -> None
```

**Segment data model:**
```python
@dataclass
class Segment:
    start: float          # seconds from chunk start
    end: float
    text: str
    words: List[Word]     # word-level timestamps
    confidence: float
```

---

### 7.3 Speaker Diarization (`backend/diarization/speaker_cluster.py`)

**Responsibilities:**
- Accept audio slice + segment timestamps
- Embed each utterance using Resemblyzer
- Cluster embeddings over rolling window
- Return `speaker_id` string per segment

**Key classes:**

```python
class SpeakerClusterer:
    threshold: float = 0.75       # cosine distance threshold
    min_speakers: int = 1
    max_speakers: int = 8
    embedding_history: deque      # rolling window of (embedding, label)

    def assign_speaker(audio: np.ndarray, segment: Segment) -> str
    def reset() -> None           # call at meeting start
```

**Speaker label format:** `Speaker 1`, `Speaker 2`, ... (user can rename in UI)

---

### 7.4 Orchestration Server (`backend/api/server.py`)

**Responsibilities:**
- FastAPI app with REST + WebSocket endpoints
- Spawn audio capture + transcription workers
- Broadcast transcript events via WebSocket
- Expose meeting CRUD endpoints

**WebSocket protocol:**

```json
// Server → Client (transcript update)
{
  "type": "transcript",
  "data": {
    "meeting_id": "uuid",
    "speaker": "Speaker 1",
    "text": "Let's finalize the roadmap",
    "timestamp": 125.4,
    "segment_id": "uuid"
  }
}

// Server → Client (status)
{
  "type": "status",
  "data": { "recording": true, "speakers_detected": 2 }
}
```

---

### 7.5 LLM Summarization (`backend/llm/summarizer.py`)

**Responsibilities:**
- Accept full transcript text
- Chunk if over token limit
- Call Ollama REST API
- Parse structured markdown response
- Store result

**Ollama endpoint:** `http://localhost:11434/api/generate`

**Prompt template:**

```
You are an expert meeting analyst. Analyze the following transcript.

TRANSCRIPT:
{transcript}

Return ONLY valid markdown with these exact sections:

## Summary
(2-3 sentence overview)

## Key Discussion Points
- point 1
- point 2

## Decisions Made
- decision 1

## Action Items
| Assignee | Task | Deadline |
|----------|------|----------|
| Name | Task | Date |

## Risks & Blockers
- risk 1

## Next Steps
- step 1
```

---

### 7.6 Storage Layer (`backend/storage/db.py`)

**Responsibilities:**
- SQLite via `aiosqlite` for async access
- CRUD for meetings, transcript segments, summaries, speakers
- Migration support

---

## 8. Database Schema

```sql
-- meetings table
CREATE TABLE meetings (
    id          TEXT PRIMARY KEY,       -- UUID
    title       TEXT NOT NULL,
    created_at  DATETIME DEFAULT (datetime('now')),
    ended_at    DATETIME,
    duration_s  REAL,
    status      TEXT DEFAULT 'active',  -- active | completed | archived
    metadata    TEXT                    -- JSON blob (participants, tags)
);

-- transcript_segments table
CREATE TABLE transcript_segments (
    id          TEXT PRIMARY KEY,       -- UUID
    meeting_id  TEXT NOT NULL REFERENCES meetings(id),
    speaker     TEXT,                   -- "Speaker 1", or renamed label
    text        TEXT NOT NULL,
    start_time  REAL NOT NULL,          -- seconds from meeting start
    end_time    REAL NOT NULL,
    confidence  REAL,
    created_at  DATETIME DEFAULT (datetime('now'))
);

-- summaries table
CREATE TABLE summaries (
    id          TEXT PRIMARY KEY,       -- UUID
    meeting_id  TEXT NOT NULL REFERENCES meetings(id),
    content     TEXT NOT NULL,          -- full markdown
    summary     TEXT,                   -- extracted ## Summary section
    action_items TEXT,                  -- JSON array
    decisions   TEXT,                   -- JSON array
    created_at  DATETIME DEFAULT (datetime('now')),
    model_used  TEXT                    -- e.g. "mistral:7b"
);

-- speakers table
CREATE TABLE speakers (
    id          TEXT PRIMARY KEY,       -- UUID
    meeting_id  TEXT NOT NULL REFERENCES meetings(id),
    label       TEXT NOT NULL,          -- "Speaker 1"
    name        TEXT,                   -- user-assigned "John"
    color       TEXT                    -- hex color for UI
);

-- CREATE INDEXES
CREATE INDEX idx_segments_meeting ON transcript_segments(meeting_id, start_time);
CREATE INDEX idx_summaries_meeting ON summaries(meeting_id);
```

---

## 9. API Contracts

### REST Endpoints

```
POST   /api/meetings                    → Create new meeting, return {id}
GET    /api/meetings                    → List all meetings
GET    /api/meetings/{id}               → Get meeting detail
PATCH  /api/meetings/{id}               → Update title / status
DELETE /api/meetings/{id}               → Delete meeting + segments

POST   /api/meetings/{id}/start         → Start recording
POST   /api/meetings/{id}/stop          → Stop recording

GET    /api/meetings/{id}/transcript    → Full transcript (paginated)
GET    /api/meetings/{id}/summary       → Get summary (generate if missing)
POST   /api/meetings/{id}/summarize     → Force regenerate summary

GET    /api/speakers/{meeting_id}       → List speakers
PATCH  /api/speakers/{id}              → Rename speaker

POST   /api/search                      → Semantic search across meetings
  body: { "query": "what was decided about auth?" }
```

### WebSocket

```
WS /ws/meetings/{id}                    → Real-time transcript stream
```

---

## 10. Project File Structure

```
parrot-script/
│
├── README.md
├── PLAN.md                            ← this file
├── TASKS.md                           ← step-by-step coding tasks
├── .env.example
├── .env                               ← local config (gitignored)
├── requirements.txt
├── pyproject.toml
│
├── backend/
│   │
│   ├── main.py                        ← entrypoint: uvicorn startup
│   │
│   ├── config.py                      ← pydantic Settings model
│   │   # reads .env: WHISPER_MODEL, OLLAMA_URL, DB_PATH, etc.
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── server.py                  ← FastAPI app + router registration
│   │   ├── routes/
│   │   │   ├── meetings.py            ← meeting CRUD routes
│   │   │   ├── transcripts.py         ← transcript routes
│   │   │   ├── summaries.py           ← summary routes
│   │   │   └── search.py              ← semantic search
│   │   └── websocket.py               ← WebSocket manager + broadcaster
│   │
│   ├── audio/
│   │   ├── __init__.py
│   │   ├── capture.py                 ← FFmpeg process + chunker
│   │   ├── devices.py                 ← list avfoundation devices
│   │   └── vad.py                     ← voice activity detection wrapper
│   │
│   ├── transcription/
│   │   ├── __init__.py
│   │   ├── whisper_stream.py          ← Faster-Whisper inference
│   │   └── models.py                  ← Segment, Word dataclasses
│   │
│   ├── diarization/
│   │   ├── __init__.py
│   │   ├── speaker_cluster.py         ← Resemblyzer + clustering
│   │   └── embeddings.py              ← embedding cache + helpers
│   │
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── summarizer.py              ← Ollama call + prompt builder
│   │   ├── prompts.py                 ← all prompt templates
│   │   └── chunker.py                 ← transcript token chunking
│   │
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── db.py                      ← aiosqlite connection + migrations
│   │   ├── repositories/
│   │   │   ├── meetings.py
│   │   │   ├── segments.py
│   │   │   ├── summaries.py
│   │   │   └── speakers.py
│   │   └── vector_store.py            ← ChromaDB client wrapper
│   │
│   └── core/
│       ├── __init__.py
│       ├── events.py                  ← event dataclasses (TranscriptEvent, etc.)
│       ├── pipeline.py                ← wires audio→transcription→diarization
│       └── exceptions.py
│
├── frontend/
│   │
│   ├── react-app/                     ← Primary frontend (React + Vite)
│   │   ├── package.json
│   │   ├── vite.config.ts
│   │   ├── src/
│   │   │   ├── main.tsx
│   │   │   ├── App.tsx
│   │   │   ├── components/
│   │   │   │   ├── MeetingControls.tsx   ← Start/Stop buttons
│   │   │   │   ├── LiveTranscript.tsx    ← WebSocket feed
│   │   │   │   ├── SpeakerTimeline.tsx   ← Speaker turn visualization
│   │   │   │   ├── SummaryPanel.tsx      ← AI summary display
│   │   │   │   ├── MeetingList.tsx       ← Past meetings
│   │   │   │   └── SearchBar.tsx         ← Semantic search
│   │   │   ├── hooks/
│   │   │   │   ├── useWebSocket.ts
│   │   │   │   └── useMeeting.ts
│   │   │   └── api/
│   │   │       └── client.ts            ← API calls
│   │   └── public/
│   │
│   └── streamlit_app/                 ← Fallback / simple frontend
│       └── dashboard.py
│
├── scripts/
│   ├── start_meeting.sh               ← CLI launcher (sets up audio + starts backend)
│   ├── list_audio_devices.py          ← helper to find BlackHole device index
│   ├── test_whisper.py                ← smoke test transcription
│   └── test_ollama.py                 ← smoke test summarization
│
├── tests/
│   ├── test_audio.py
│   ├── test_transcription.py
│   ├── test_diarization.py
│   ├── test_llm.py
│   ├── test_api.py
│   └── fixtures/
│       └── sample_meeting.wav
│
└── data/                              ← gitignored
    ├── meetings.db                    ← SQLite database
    └── chroma/                        ← ChromaDB persistence
```

---

## 11. Memory & Performance Budget

### RAM Allocation (Mac M4, 16 GB)

| Component                        | RAM Usage  | Notes                            |
|----------------------------------|------------|----------------------------------|
| macOS + background apps          | ~3.0 GB    | baseline                         |
| Python runtime + FastAPI         | ~0.3 GB    |                                  |
| Faster-Whisper `small.en` (int8) | ~1.5 GB    | loaded once, stays in memory     |
| Resemblyzer voice encoder        | ~0.3 GB    |                                  |
| scikit-learn clustering          | ~0.1 GB    |                                  |
| Ollama (mistral:7b Q4_K_M)       | ~5.0 GB    | loaded on first summary call     |
| ChromaDB (embedded)              | ~0.2 GB    |                                  |
| Audio buffer (30s PCM)           | ~1.0 MB    | negligible                       |
| **Total (peak)**                 | **~10.5 GB** | within 16 GB budget            |
| **Total (idle, no Ollama)**      | **~5.5 GB** |                                  |

> Ollama only loads when summarization is triggered — freeing ~5 GB during recording.

### CPU Usage Expectations

| Task                         | CPU Load  | Duration        |
|------------------------------|-----------|-----------------|
| Audio capture (FFmpeg)       | < 5%      | continuous      |
| Whisper transcription        | 40–60%    | 2–4s per chunk  |
| Speaker embedding            | 10–20%    | 0.5s per chunk  |
| Ollama summarization         | 40–80%    | 20–40s once     |
| FastAPI / WebSocket          | < 5%      | continuous      |

---

## 12. Implementation Phases

### Phase 1 — Core MVP (Days 1–2)

**Goal:** Working transcription pipeline with basic UI.

**Deliverables:**
- [ ] BlackHole + FFmpeg audio capture working
- [ ] Faster-Whisper transcribing chunks accurately
- [ ] SQLite schema created + segments stored
- [ ] FastAPI REST endpoints: create meeting, get transcript
- [ ] Streamlit dashboard showing live transcript
- [ ] Ollama summarization on demand

**Acceptance criteria:**
- Can record a 5-minute test meeting
- Transcript accuracy > 90% for clear speech
- Summary generated within 60 seconds

---

### Phase 2 — Real-Time System (Days 3–5)

**Goal:** True streaming pipeline with speaker labels.

**Deliverables:**
- [ ] Resemblyzer speaker diarization integrated
- [ ] WebSocket broadcasting to frontend
- [ ] React frontend with live transcript feed
- [ ] Speaker renaming in UI
- [ ] Meeting start/stop controls
- [ ] VAD filtering (skip silence chunks)

**Acceptance criteria:**
- Transcript appears in UI within 5 seconds of speech
- 2 speakers correctly separated in test recording
- UI shows speaker colors + timeline

---

### Phase 3 — Meeting Intelligence (Days 6–14)

**Goal:** Searchable knowledge base from all meetings.

**Deliverables:**
- [ ] ChromaDB integration for transcript embedding
- [ ] Semantic search endpoint (`/api/search`)
- [ ] Search UI in frontend
- [ ] Action item extraction + tracking view
- [ ] Meeting history list with summaries
- [ ] Export meeting as Markdown / PDF

**Example search queries:**
```
"What was decided about the authentication system?"
"What tasks were assigned to Sarah last week?"
"When did we discuss the Q3 budget?"
```

---

### Phase 4 — Polish & Extensions (Week 3+)

- [ ] Multiple meeting source support (file upload + live)
- [ ] Speaker profile management (persistent across meetings)
- [ ] Slack / Notion export integration
- [ ] Custom prompt templates for different meeting types
- [ ] Meeting templates (standup, planning, retrospective)

---

## 13. Configuration Reference

### `.env.example`

```env
# Whisper
WHISPER_MODEL=small.en
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
WHISPER_BEAM_SIZE=5

# Audio
AUDIO_DEVICE_INDEX=2           # run scripts/list_audio_devices.py to find
AUDIO_SAMPLE_RATE=16000
AUDIO_CHUNK_SECONDS=30
AUDIO_VAD_AGGRESSIVENESS=2     # 0-3, higher = more aggressive silence removal

# Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=mistral:7b-instruct
OLLAMA_TIMEOUT=120

# Database
DB_PATH=./data/meetings.db
CHROMA_PATH=./data/chroma

# API
API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=http://localhost:5173,http://localhost:8501

# Speaker Diarization
MAX_SPEAKERS=8
SPEAKER_CLUSTER_THRESHOLD=0.75
EMBEDDING_WINDOW_SIZE=50       # number of embeddings to keep in rolling window

# Summarization
SUMMARY_CHUNK_SIZE=3000        # tokens per chunk for map-reduce
SUMMARY_MAX_TOKENS=1000        # max output tokens from LLM
```

---

## 14. Error Handling & Resilience

### Audio Capture Failures

```python
# If FFmpeg dies mid-meeting:
# - Log error + timestamp
# - Attempt restart (max 3 retries)
# - Mark gap in transcript
# - Continue storing what was captured
```

### Whisper Inference Failures

```python
# If chunk fails to transcribe:
# - Log + skip chunk (don't block pipeline)
# - Store placeholder segment: [inaudible]
# - Continue with next chunk
```

### Ollama Unavailable

```python
# If Ollama not running:
# - Return 503 from /summarize endpoint
# - Frontend shows "Start Ollama to generate summary"
# - Recording and transcription unaffected
```

### Database Write Failures

```python
# Use WAL mode for SQLite (concurrent reads + writes)
# Wrap writes in transactions
# On failure: queue writes in memory, retry
```

---

## 15. Testing Strategy

### Unit Tests

```
tests/test_audio.py           → mock FFmpeg, test chunking logic
tests/test_transcription.py   → test with sample .wav fixture
tests/test_diarization.py     → test speaker clustering with synthetic embeddings
tests/test_llm.py             → mock Ollama, test prompt building + parsing
tests/test_api.py             → FastAPI TestClient, all endpoints
```

### Integration Tests

```
Run full pipeline with a 2-minute sample meeting WAV
Assert:
  - Transcript has > 10 segments
  - At least 1 speaker detected
  - Summary contains ## Action Items section
  - SQLite has correct row counts
```

### Smoke Test Commands

```bash
# Test audio device detection
python scripts/list_audio_devices.py

# Test Whisper on sample file
python scripts/test_whisper.py --file tests/fixtures/sample_meeting.wav

# Test Ollama connection
python scripts/test_ollama.py

# Run all unit tests
pytest tests/ -v
```

---

## 16. Key Design Principles

1. **Local-first** — Zero data leaves the machine. No API keys. No cloud.
2. **Async everywhere** — Audio capture, transcription, and DB writes are all non-blocking.
3. **Fail gracefully** — Any component failure must not crash the recording pipeline.
4. **Modular and swappable** — Swap Whisper model, LLM, or frontend independently.
5. **Streaming over batch** — Prefer 30-second incremental processing over end-of-meeting batching.
6. **Memory discipline** — Respect 8 GB budget. Ollama unloads between summaries if needed.
7. **Structured outputs** — LLM output is always parsed into structured data, not free text.

---

## Quick Start (After Implementation)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Install BlackHole audio loopback
brew install blackhole-2ch

# 3. Pull Ollama model
ollama pull mistral:7b-instruct

# 4. Find your BlackHole device index
python scripts/list_audio_devices.py
# → Set AUDIO_DEVICE_INDEX in .env

# 5. Start the backend
uvicorn backend.main:app --reload --port 8000

# 6. Start the frontend (React)
cd frontend && npm install && npm run dev

# 7. Open http://localhost:5173 → click Start Meeting
```

---

*Plan version: 1.0 | Optimized for Apple Silicon M-series, 16 GB RAM | Privacy-first local architecture*