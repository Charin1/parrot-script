# TASKS.md — Step-by-Step Build Roadmap for Claude Code
> Feed this file to Claude Code after PLAN.md. Complete tasks in order.

---

## Instructions for Claude Code

- Complete tasks **in the exact order listed**
- Each task has a clear **goal**, **files to create/modify**, and **acceptance test**
- Run the acceptance test before marking a task done
- Never skip a task — later tasks depend on earlier ones
- Refer to `PLAN.md` for architecture decisions and data models

---

## PHASE 1 — Project Scaffold & Config

---

### TASK 1.1 — Initialize project structure

**Goal:** Create the full directory tree and placeholder files.

**Create these files (empty or with minimal content):**

```
parrot-script/
├── .env.example
├── .env                          ← copy from .env.example, fill in defaults
├── requirements.txt
├── pyproject.toml
├── backend/__init__.py
├── backend/main.py
├── backend/config.py
├── backend/api/__init__.py
├── backend/api/server.py
├── backend/api/websocket.py
├── backend/api/routes/__init__.py
├── backend/api/routes/meetings.py
├── backend/api/routes/transcripts.py
├── backend/api/routes/summaries.py
├── backend/api/routes/search.py
├── backend/audio/__init__.py
├── backend/audio/capture.py
├── backend/audio/devices.py
├── backend/audio/vad.py
├── backend/transcription/__init__.py
├── backend/transcription/whisper_stream.py
├── backend/transcription/models.py
├── backend/diarization/__init__.py
├── backend/diarization/speaker_cluster.py
├── backend/diarization/embeddings.py
├── backend/llm/__init__.py
├── backend/llm/summarizer.py
├── backend/llm/prompts.py
├── backend/llm/chunker.py
├── backend/storage/__init__.py
├── backend/storage/db.py
├── backend/storage/vector_store.py
├── backend/storage/repositories/__init__.py
├── backend/storage/repositories/meetings.py
├── backend/storage/repositories/segments.py
├── backend/storage/repositories/summaries.py
├── backend/storage/repositories/speakers.py
├── backend/core/__init__.py
├── backend/core/events.py
├── backend/core/pipeline.py
├── backend/core/exceptions.py
├── scripts/list_audio_devices.py
├── scripts/test_whisper.py
├── scripts/test_ollama.py
├── tests/__init__.py
├── tests/test_audio.py
├── tests/test_transcription.py
├── tests/test_api.py
└── data/.gitkeep
```

**`requirements.txt` must include:**

```
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
websockets>=12.0
aiosqlite>=0.20.0
faster-whisper>=1.0.0
resemblyzer>=0.1.3
scikit-learn>=1.4.0
numpy>=1.26.0
soundfile>=0.12.1
httpx>=0.27.0
chromadb>=0.5.0
python-dotenv>=1.0.0
pydantic>=2.6.0
pydantic-settings>=2.2.0
webrtcvad>=2.0.10
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

**`pyproject.toml`:**
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

**Acceptance test:**
```bash
find parrot-script -type f -name "*.py" | wc -l
# should output >= 25
pip install -r requirements.txt
# should install without errors
```

---

### TASK 1.2 — Implement `backend/config.py`

**Goal:** Typed configuration using pydantic-settings that reads from `.env`.

**Implement `Settings` class with these fields:**

```python
# Whisper
whisper_model: str = "small.en"
whisper_device: str = "cpu"
whisper_compute_type: str = "int8"
whisper_beam_size: int = 5

# Audio
audio_device_index: int = 0
audio_sample_rate: int = 16000
audio_chunk_seconds: int = 30
audio_vad_aggressiveness: int = 2

# Ollama
ollama_base_url: str = "http://localhost:11434"
ollama_model: str = "mistral:7b-instruct"
ollama_timeout: int = 120

# Database
db_path: str = "./data/meetings.db"
chroma_path: str = "./data/chroma"

# API
api_host: str = "0.0.0.0"
api_port: int = 8000
cors_origins: list[str] = ["http://localhost:5173", "http://localhost:8501"]

# Speaker
max_speakers: int = 8
speaker_cluster_threshold: float = 0.75
embedding_window_size: int = 50

# Summarization
summary_chunk_size: int = 3000
summary_max_tokens: int = 1000
```

**Export a singleton:** `settings = Settings()`

**Acceptance test:**
```python
from backend.config import settings
assert settings.whisper_model == "small.en"
assert settings.ollama_base_url.startswith("http")
print("Config OK")
```

---

### TASK 1.3 — Implement `backend/core/events.py`

**Goal:** Define all event dataclasses used across the pipeline.

**Implement these dataclasses:**

```python
@dataclass
class AudioChunkEvent:
    data: bytes           # raw PCM bytes
    timestamp: float      # epoch seconds when chunk was captured
    chunk_index: int

@dataclass
class TranscriptSegmentEvent:
    meeting_id: str
    speaker: str           # "Speaker 1"
    text: str
    start_time: float      # seconds from meeting start
    end_time: float
    confidence: float
    segment_id: str        # UUID

@dataclass
class MeetingStatusEvent:
    meeting_id: str
    recording: bool
    speakers_detected: int
    duration_s: float
```

**Acceptance test:**
```python
from backend.core.events import AudioChunkEvent, TranscriptSegmentEvent
e = TranscriptSegmentEvent("m1", "Speaker 1", "hello", 0.0, 1.5, 0.95, "s1")
assert e.text == "hello"
```

---

## PHASE 2 — Database Layer

---

### TASK 2.1 — Implement `backend/storage/db.py`

**Goal:** SQLite connection manager with schema creation.

**Implement:**
- `async def get_db() -> aiosqlite.Connection` — returns an open connection
- `async def init_db()` — creates all tables if they don't exist
- Use WAL mode: `PRAGMA journal_mode=WAL`

**SQL schema to execute in `init_db()`:**

```sql
CREATE TABLE IF NOT EXISTS meetings (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at DATETIME DEFAULT (datetime('now')),
    ended_at DATETIME,
    duration_s REAL,
    status TEXT DEFAULT 'active',
    metadata TEXT
);

CREATE TABLE IF NOT EXISTS transcript_segments (
    id TEXT PRIMARY KEY,
    meeting_id TEXT NOT NULL REFERENCES meetings(id),
    speaker TEXT,
    text TEXT NOT NULL,
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    confidence REAL,
    created_at DATETIME DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS summaries (
    id TEXT PRIMARY KEY,
    meeting_id TEXT NOT NULL REFERENCES meetings(id),
    content TEXT NOT NULL,
    summary TEXT,
    action_items TEXT,
    decisions TEXT,
    created_at DATETIME DEFAULT (datetime('now')),
    model_used TEXT
);

CREATE TABLE IF NOT EXISTS speakers (
    id TEXT PRIMARY KEY,
    meeting_id TEXT NOT NULL REFERENCES meetings(id),
    label TEXT NOT NULL,
    name TEXT,
    color TEXT
);

CREATE INDEX IF NOT EXISTS idx_segments_meeting
    ON transcript_segments(meeting_id, start_time);
```

**Acceptance test:**
```python
import asyncio
from backend.storage.db import init_db, get_db

async def test():
    await init_db()
    db = await get_db()
    async with db.execute("SELECT name FROM sqlite_master WHERE type='table'") as cur:
        tables = [row[0] async for row in cur]
    assert "meetings" in tables
    assert "transcript_segments" in tables
    print("DB OK:", tables)

asyncio.run(test())
```

---

### TASK 2.2 — Implement repository classes

**Goal:** CRUD operations for each table.

**`backend/storage/repositories/meetings.py`:**

```python
class MeetingsRepository:
    async def create(title: str) -> dict           # returns meeting row as dict
    async def get(meeting_id: str) -> dict | None
    async def list_all() -> list[dict]
    async def update(meeting_id: str, **kwargs) -> dict
    async def delete(meeting_id: str) -> bool
    async def end_meeting(meeting_id: str) -> dict
```

**`backend/storage/repositories/segments.py`:**

```python
class SegmentsRepository:
    async def insert(segment: TranscriptSegmentEvent) -> dict
    async def get_by_meeting(meeting_id: str) -> list[dict]
    async def get_full_text(meeting_id: str) -> str   # concat all text
```

**`backend/storage/repositories/summaries.py`:**

```python
class SummariesRepository:
    async def insert(meeting_id: str, content: str, model: str) -> dict
    async def get_by_meeting(meeting_id: str) -> dict | None
    async def update(summary_id: str, **kwargs) -> dict
```

**`backend/storage/repositories/speakers.py`:**

```python
class SpeakersRepository:
    async def upsert(meeting_id: str, label: str) -> dict
    async def rename(speaker_id: str, name: str) -> dict
    async def get_by_meeting(meeting_id: str) -> list[dict]
```

**Acceptance test:**
```python
import asyncio
from backend.storage.db import init_db
from backend.storage.repositories.meetings import MeetingsRepository

async def test():
    await init_db()
    repo = MeetingsRepository()
    meeting = await repo.create("Test Meeting")
    assert meeting["title"] == "Test Meeting"
    fetched = await repo.get(meeting["id"])
    assert fetched["id"] == meeting["id"]
    print("Repo OK")

asyncio.run(test())
```

---

## PHASE 3 — Audio Capture

---

### TASK 3.1 — Implement `backend/audio/devices.py`

**Goal:** List available audio input devices on macOS using FFmpeg.

**Implement:**

```python
def list_audio_devices() -> list[dict]:
    """
    Run: ffmpeg -f avfoundation -list_devices true -i ""
    Parse output to extract device names and indices.
    Return list of {"index": int, "name": str}
    """

def find_blackhole_device() -> int | None:
    """
    Return the device index for BlackHole 2ch, or None if not found.
    """
```

**`scripts/list_audio_devices.py`** should call this and pretty-print results.

**Acceptance test:**
```bash
python scripts/list_audio_devices.py
# Should list audio devices, including BlackHole if installed
```

---

### TASK 3.2 — Implement `backend/audio/vad.py`

**Goal:** Wrap webrtcvad to detect voice activity in audio chunks.

**Implement:**

```python
class VoiceActivityDetector:
    def __init__(self, aggressiveness: int = 2, sample_rate: int = 16000):
        ...

    def is_speech(self, audio_bytes: bytes) -> bool:
        """
        Return True if chunk contains speech.
        Frame must be 10, 20, or 30ms — use 30ms frames.
        """

    def filter_silent_chunks(self, audio_bytes: bytes) -> bool:
        """
        Returns True if overall chunk has enough speech frames (>30%).
        """
```

**Acceptance test:**
```python
from backend.audio.vad import VoiceActivityDetector
import numpy as np

vad = VoiceActivityDetector()
# Test with silence (zeros)
silence = np.zeros(16000 * 2, dtype=np.int16).tobytes()
assert vad.filter_silent_chunks(silence) == False
print("VAD OK")
```

---

### TASK 3.3 — Implement `backend/audio/capture.py`

**Goal:** Capture system audio via FFmpeg and emit chunks to an async queue.

**Implement:**

```python
class AudioCapture:
    def __init__(self, device_index: int, sample_rate: int = 16000,
                 chunk_seconds: int = 30):
        self.queue: asyncio.Queue[AudioChunkEvent] = asyncio.Queue()
        self._process: subprocess.Popen | None = None
        self._chunk_index: int = 0

    async def start(self) -> None:
        """Launch FFmpeg subprocess, start reader thread."""

    async def stop(self) -> None:
        """Terminate FFmpeg process, signal done."""

    def _build_ffmpeg_cmd(self) -> list[str]:
        """
        Returns:
        ffmpeg -f avfoundation -i ":{device_index}"
               -ac 1 -ar {sample_rate} -acodec pcm_s16le
               -f s16le -bufsize 65536 pipe:1
        """

    def _reader_thread(self) -> None:
        """
        Read stdout bytes from FFmpeg.
        Buffer until chunk_seconds * sample_rate * 2 bytes accumulated.
        If VAD says chunk is silent: discard.
        Else: create AudioChunkEvent and put in queue.
        Run in a daemon thread.
        """
```

**Acceptance test:**
```python
# Manually test by running capture for 5 seconds
import asyncio
from backend.audio.capture import AudioCapture

async def test():
    cap = AudioCapture(device_index=0, chunk_seconds=5)
    await cap.start()
    await asyncio.sleep(6)
    chunk = await asyncio.wait_for(cap.queue.get(), timeout=5.0)
    print(f"Got chunk: {len(chunk.data)} bytes, index={chunk.chunk_index}")
    await cap.stop()

asyncio.run(test())
```

---

## PHASE 4 — Transcription

---

### TASK 4.1 — Implement `backend/transcription/models.py`

**Goal:** Data models for transcription output.

**Implement:**

```python
@dataclass
class Word:
    start: float
    end: float
    word: str
    probability: float

@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: list[Word]
    avg_logprob: float

    @property
    def confidence(self) -> float:
        return min(1.0, max(0.0, (self.avg_logprob + 1.0)))
```

---

### TASK 4.2 — Implement `backend/transcription/whisper_stream.py`

**Goal:** Load Faster-Whisper and transcribe audio chunks.

**Implement:**

```python
class WhisperTranscriber:
    def __init__(self):
        self.model = None  # loaded lazily

    def load_model(self) -> None:
        """
        Load WhisperModel(
            model_size_or_path=settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type
        )
        Log model load time.
        """

    def transcribe(self, audio_bytes: bytes) -> list[Segment]:
        """
        1. Convert bytes to numpy float32 (divide by 32768.0)
        2. Call self.model.transcribe(
               audio,
               beam_size=settings.whisper_beam_size,
               word_timestamps=True,
               vad_filter=True,
               language="en"
           )
        3. Convert to list[Segment] dataclass
        4. Return segments
        """

    async def transcribe_async(self, audio_bytes: bytes) -> list[Segment]:
        """
        Run transcribe() in executor to avoid blocking event loop.
        Use asyncio.get_event_loop().run_in_executor(None, self.transcribe, audio_bytes)
        """
```

**`scripts/test_whisper.py`** should:
1. Load a WAV file from CLI arg
2. Run `WhisperTranscriber().transcribe()`
3. Print all segments with timestamps

**Acceptance test:**
```bash
python scripts/test_whisper.py --file tests/fixtures/sample_meeting.wav
# Should print timestamped transcript segments
```

---

## PHASE 5 — Speaker Diarization

---

### TASK 5.1 — Implement `backend/diarization/embeddings.py`

**Goal:** Voice embedding helper using Resemblyzer.

**Implement:**

```python
class VoiceEmbedder:
    def __init__(self):
        self.encoder = None  # VoiceEncoder, loaded lazily

    def load(self) -> None:
        """from resemblyzer import VoiceEncoder; self.encoder = VoiceEncoder()"""

    def embed(self, audio_bytes: bytes, sample_rate: int = 16000) -> np.ndarray:
        """
        1. Convert bytes to float32 numpy array
        2. Call encoder.preprocess_wav(audio, sample_rate)
        3. Call encoder.embed_utterance(wav)
        4. Return 256-dim embedding
        """
```

---

### TASK 5.2 — Implement `backend/diarization/speaker_cluster.py`

**Goal:** Assign speaker labels using cosine clustering.

**Implement:**

```python
class SpeakerClusterer:
    def __init__(self):
        self.embedder = VoiceEmbedder()
        self.embedding_history: deque = deque(maxlen=settings.embedding_window_size)
        self.labels: list[str] = []
        self.speaker_count: int = 0

    def assign_speaker(self, audio_bytes: bytes) -> str:
        """
        1. Get embedding from VoiceEmbedder
        2. If no history: assign "Speaker 1", store, return
        3. Compute cosine similarity with all existing cluster centroids
        4. If max similarity > (1 - threshold): assign that speaker label
        5. Else: create new speaker label ("Speaker N+1")
        6. Add to embedding history
        7. Return speaker label
        """

    def get_centroid(self, label: str) -> np.ndarray:
        """Average all embeddings in history for the given label."""

    def reset(self) -> None:
        """Clear history and labels. Call at meeting start."""

    @property
    def unique_speakers(self) -> list[str]:
        return list(set(self.labels))
```

**Acceptance test:**
```python
# Two clearly different speakers should get different labels
# Same speaker repeated should get same label
from backend.diarization.speaker_cluster import SpeakerClusterer
sc = SpeakerClusterer()
sc.embedder.load()
print("Diarizer loaded OK")
```

---

## PHASE 6 — LLM Summarization

---

### TASK 6.1 — Implement `backend/llm/prompts.py`

**Goal:** All prompt templates as constants.

**Implement:**

```python
MEETING_SUMMARY_PROMPT = """
You are an expert meeting analyst.

Analyze the following transcript and return ONLY valid markdown with these exact sections:

## Summary
(2-3 sentence high-level overview)

## Key Discussion Points
- point 1

## Decisions Made
- decision 1 (or "None identified")

## Action Items
| Assignee | Task | Notes |
|----------|------|-------|
| Name | Description | context |

## Risks & Blockers
- risk 1 (or "None identified")

## Next Steps
- step 1

TRANSCRIPT:
{transcript}
"""

PARTIAL_SUMMARY_PROMPT = """
Summarize this portion of a meeting transcript in 3-5 bullet points.
Focus on key topics, decisions, and action items.

TRANSCRIPT PORTION:
{transcript}
"""

COMBINE_SUMMARIES_PROMPT = """
You are combining multiple partial meeting summaries into a final structured summary.

PARTIAL SUMMARIES:
{summaries}

Return ONLY valid markdown with these sections:
## Summary
## Key Discussion Points
## Decisions Made
## Action Items (table format)
## Risks & Blockers
## Next Steps
"""
```

---

### TASK 6.2 — Implement `backend/llm/chunker.py`

**Goal:** Split long transcripts into chunks for map-reduce summarization.

**Implement:**

```python
def estimate_tokens(text: str) -> int:
    """Rough estimate: len(text.split()) * 1.3"""

def chunk_transcript(transcript: str, max_tokens: int = 3000) -> list[str]:
    """
    Split transcript by speaker turns (lines).
    Accumulate lines into chunks of max_tokens.
    Each chunk must be a complete speaker turn (don't split mid-sentence).
    Return list of chunk strings.
    """
```

**Acceptance test:**
```python
from backend.llm.chunker import chunk_transcript, estimate_tokens

long_text = "Speaker 1: " + ("word " * 500 + "\n") * 20
chunks = chunk_transcript(long_text, max_tokens=3000)
assert len(chunks) >= 2
assert all(estimate_tokens(c) <= 3500 for c in chunks)
print(f"Chunked into {len(chunks)} parts")
```

---

### TASK 6.3 — Implement `backend/llm/summarizer.py`

**Goal:** Summarize meeting transcript using Ollama.

**Implement:**

```python
class MeetingSummarizer:
    async def summarize(self, transcript: str, meeting_id: str) -> dict:
        """
        1. Estimate token count
        2. If > settings.summary_chunk_size:
               chunks = chunk_transcript(transcript)
               partial_summaries = await asyncio.gather(*[
                   self._call_ollama(PARTIAL_SUMMARY_PROMPT.format(transcript=c))
                   for c in chunks
               ])
               combined = "\n\n---\n\n".join(partial_summaries)
               result = await self._call_ollama(
                   COMBINE_SUMMARIES_PROMPT.format(summaries=combined)
               )
           Else:
               result = await self._call_ollama(
                   MEETING_SUMMARY_PROMPT.format(transcript=transcript)
               )
        3. Store in DB via SummariesRepository
        4. Return {"content": result, "meeting_id": meeting_id}
        """

    async def _call_ollama(self, prompt: str) -> str:
        """
        POST to {settings.ollama_base_url}/api/generate
        Body: {"model": settings.ollama_model, "prompt": prompt, "stream": False}
        Return response["response"]
        Raise OllamaUnavailableError if connection fails.
        """
```

**`scripts/test_ollama.py`** should:
1. Check if Ollama is running
2. Send a test prompt
3. Print result

**Acceptance test:**
```bash
ollama serve &
python scripts/test_ollama.py
# Should print a summarization response
```

---

## PHASE 7 — FastAPI Server

---

### TASK 7.1 — Implement `backend/api/websocket.py`

**Goal:** WebSocket connection manager that broadcasts transcript events.

**Implement:**

```python
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}
        # key: meeting_id, value: list of connected WebSocket clients

    async def connect(self, websocket: WebSocket, meeting_id: str) -> None
    async def disconnect(self, websocket: WebSocket, meeting_id: str) -> None
    async def broadcast(self, meeting_id: str, message: dict) -> None
        """Send JSON message to all clients subscribed to this meeting_id."""

manager = ConnectionManager()
```

---

### TASK 7.2 — Implement all API routes

**`backend/api/routes/meetings.py`:**

```python
router = APIRouter(prefix="/api/meetings", tags=["meetings"])

POST   "/"                          → create_meeting(title: str)
GET    "/"                          → list_meetings()
GET    "/{meeting_id}"              → get_meeting(meeting_id)
PATCH  "/{meeting_id}"              → update_meeting(meeting_id, body)
DELETE "/{meeting_id}"              → delete_meeting(meeting_id)
POST   "/{meeting_id}/start"        → start_recording(meeting_id)
POST   "/{meeting_id}/stop"         → stop_recording(meeting_id)
```

**`backend/api/routes/transcripts.py`:**

```python
router = APIRouter(prefix="/api/meetings", tags=["transcripts"])

GET    "/{meeting_id}/transcript"   → get_transcript(meeting_id, page, limit)
```

**`backend/api/routes/summaries.py`:**

```python
router = APIRouter(prefix="/api/meetings", tags=["summaries"])

GET    "/{meeting_id}/summary"      → get_or_create_summary(meeting_id)
POST   "/{meeting_id}/summarize"    → force_summarize(meeting_id)
```

**`backend/api/routes/search.py`:**

```python
router = APIRouter(prefix="/api", tags=["search"])

POST   "/search"                    → semantic_search(query: str, limit: int = 10)
```

---

### TASK 7.3 — Implement `backend/api/server.py`

**Goal:** Main FastAPI app wiring all routes + WebSocket endpoint.

**Implement:**

```python
app = FastAPI(title="Parrot Script", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all routers
app.include_router(meetings_router)
app.include_router(transcripts_router)
app.include_router(summaries_router)
app.include_router(search_router)

# WebSocket endpoint
@app.websocket("/ws/meetings/{meeting_id}")
async def websocket_endpoint(websocket: WebSocket, meeting_id: str):
    await manager.connect(websocket, meeting_id)
    try:
        while True:
            await websocket.receive_text()  # keep alive
    except WebSocketDisconnect:
        await manager.disconnect(websocket, meeting_id)

# Startup event: init DB
@app.on_event("startup")
async def startup():
    await init_db()
```

---

### TASK 7.4 — Implement `backend/main.py`

**Goal:** Entry point that starts uvicorn.

```python
import uvicorn
from backend.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "backend.api.server:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
        log_level="info"
    )
```

**Acceptance test:**
```bash
python -m backend.main &
curl http://localhost:8000/api/meetings
# Should return [] with 200 OK
curl -X POST http://localhost:8000/api/meetings \
     -H "Content-Type: application/json" \
     -d '{"title": "Test Meeting"}'
# Should return meeting object with id
```

---

## PHASE 8 — Pipeline Integration

---

### TASK 8.1 — Implement `backend/core/pipeline.py`

**Goal:** Wire all components together — audio → transcription → diarization → DB → WebSocket.

**Implement:**

```python
class MeetingPipeline:
    def __init__(self, meeting_id: str):
        self.meeting_id = meeting_id
        self.capture = AudioCapture(device_index=settings.audio_device_index)
        self.transcriber = WhisperTranscriber()
        self.clusterer = SpeakerClusterer()
        self.segments_repo = SegmentsRepository()
        self.speakers_repo = SpeakersRepository()
        self.running = False
        self.start_epoch: float = 0.0

    async def start(self) -> None:
        """
        1. Reset clusterer
        2. Load Whisper model (if not loaded)
        3. Load voice embedder (if not loaded)
        4. Start audio capture
        5. Set self.running = True, record start_epoch
        6. Launch _process_loop as asyncio task
        """

    async def stop(self) -> None:
        """Stop capture, set running=False, flush remaining queue."""

    async def _process_loop(self) -> None:
        """
        While self.running:
            chunk = await self.capture.queue.get()
            segments = await self.transcriber.transcribe_async(chunk.data)
            for segment in segments:
                speaker = self.clusterer.assign_speaker(chunk.data)
                event = TranscriptSegmentEvent(
                    meeting_id=self.meeting_id,
                    speaker=speaker,
                    text=segment.text,
                    start_time=chunk.timestamp - self.start_epoch + segment.start,
                    end_time=chunk.timestamp - self.start_epoch + segment.end,
                    confidence=segment.confidence,
                    segment_id=str(uuid4())
                )
                await self.segments_repo.insert(event)
                await self.speakers_repo.upsert(self.meeting_id, speaker)
                await manager.broadcast(self.meeting_id, {
                    "type": "transcript",
                    "data": asdict(event)
                })
        """
```

**Note:** Import `manager` from `backend.api.websocket`

---

### TASK 8.2 — Wire pipeline into meeting start/stop routes

**Goal:** Calling `POST /api/meetings/{id}/start` actually starts the pipeline.

**Modify `backend/api/routes/meetings.py`:**

```python
# Global pipeline registry
active_pipelines: dict[str, MeetingPipeline] = {}

@router.post("/{meeting_id}/start")
async def start_recording(meeting_id: str, background_tasks: BackgroundTasks):
    pipeline = MeetingPipeline(meeting_id)
    active_pipelines[meeting_id] = pipeline
    background_tasks.add_task(pipeline.start)
    await meetings_repo.update(meeting_id, status="recording")
    return {"status": "recording", "meeting_id": meeting_id}

@router.post("/{meeting_id}/stop")
async def stop_recording(meeting_id: str):
    pipeline = active_pipelines.pop(meeting_id, None)
    if pipeline:
        await pipeline.stop()
    await meetings_repo.end_meeting(meeting_id)
    return {"status": "completed", "meeting_id": meeting_id}
```

**Acceptance test:**
```bash
# With BlackHole + Ollama running:
MEETING_ID=$(curl -s -X POST http://localhost:8000/api/meetings \
  -H "Content-Type: application/json" \
  -d '{"title": "Pipeline Test"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

curl -X POST http://localhost:8000/api/meetings/$MEETING_ID/start
sleep 30
curl -X POST http://localhost:8000/api/meetings/$MEETING_ID/stop
curl http://localhost:8000/api/meetings/$MEETING_ID/transcript
# Should show transcript segments
```

---

## PHASE 9 — Frontend (React)

---

### TASK 9.1 — Initialize React app

```bash
cd frontend
npm create vite@latest react-app -- --template react-ts
cd react-app
npm install
npm install axios react-markdown
```

**`vite.config.ts`** — add proxy:
```typescript
server: {
  proxy: {
    '/api': 'http://localhost:8000',
    '/ws': { target: 'ws://localhost:8000', ws: true }
  }
}
```

---

### TASK 9.2 — Implement `frontend/react-app/src/api/client.ts`

**Implement typed API functions:**

```typescript
export const api = {
  createMeeting: (title: string) => Promise<Meeting>
  listMeetings: () => Promise<Meeting[]>
  getMeeting: (id: string) => Promise<Meeting>
  startRecording: (id: string) => Promise<void>
  stopRecording: (id: string) => Promise<void>
  getTranscript: (id: string) => Promise<Segment[]>
  getSummary: (id: string) => Promise<Summary>
  generateSummary: (id: string) => Promise<Summary>
  search: (query: string) => Promise<SearchResult[]>
}
```

---

### TASK 9.3 — Implement `useWebSocket` hook

```typescript
// frontend/react-app/src/hooks/useWebSocket.ts
export function useWebSocket(meetingId: string) {
  const [segments, setSegments] = useState<Segment[]>([])
  const [status, setStatus] = useState<MeetingStatus>()

  useEffect(() => {
    const ws = new WebSocket(`ws://localhost:8000/ws/meetings/${meetingId}`)
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data)
      if (msg.type === "transcript") {
        setSegments(prev => [...prev, msg.data])
      } else if (msg.type === "status") {
        setStatus(msg.data)
      }
    }
    return () => ws.close()
  }, [meetingId])

  return { segments, status }
}
```

---

### TASK 9.4 — Implement UI Components

**`MeetingControls.tsx`** — Start / Stop buttons, meeting title, duration timer

**`LiveTranscript.tsx`** — Auto-scrolling list of segments, grouped by speaker, colored

**`SummaryPanel.tsx`** — Render markdown summary, action items table, "Generate" button

**`MeetingList.tsx`** — List of past meetings with date, duration, status badges

**`SearchBar.tsx`** — Search input, results list with meeting links

---

### TASK 9.5 — Implement `App.tsx`

**Implement two-panel layout:**
- Left panel: meeting list + search
- Right panel: active meeting with live transcript + summary tab

---

## PHASE 10 — Vector Search (Phase 3 Feature)

---

### TASK 10.1 — Implement `backend/storage/vector_store.py`

**Goal:** Store transcript embeddings in ChromaDB for semantic search.

**Implement:**

```python
class VectorStore:
    def __init__(self):
        self.client = chromadb.PersistentClient(path=settings.chroma_path)
        self.collection = self.client.get_or_create_collection("meetings")

    def embed_text(self, text: str) -> list[float]:
        """Use chromadb's default embedding function (sentence transformers)."""

    async def add_meeting(self, meeting_id: str, transcript: str, summary: str) -> None:
        """
        Chunk transcript into paragraphs.
        Add each chunk as a document with metadata: {meeting_id, type: "transcript"}.
        Add summary as a document with metadata: {meeting_id, type: "summary"}.
        """

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """
        Query the collection.
        Return list of {meeting_id, text, score} dicts.
        """
```

---

## PHASE 11 — Final Integration & Tests

---

### TASK 11.1 — Write integration test

**`tests/test_integration.py`:**

```python
# Use a sample 2-minute WAV file at tests/fixtures/sample_meeting.wav
# Test full pipeline:
#   1. Create meeting
#   2. Transcribe sample WAV file directly (bypass audio capture)
#   3. Assert > 5 segments created
#   4. Assert at least 1 speaker assigned
#   5. Generate summary
#   6. Assert summary contains "## Action Items"
```

---

### TASK 11.2 — Write `scripts/start_meeting.sh`

```bash
#!/bin/bash
echo "Checking prerequisites..."
command -v ffmpeg >/dev/null || { echo "Install FFmpeg: brew install ffmpeg"; exit 1; }
command -v ollama >/dev/null || { echo "Install Ollama: brew install ollama"; exit 1; }

echo "Starting Ollama..."
ollama serve &
sleep 2

echo "Starting backend..."
cd "$(dirname "$0")/.."
python -m backend.main &
sleep 2

echo ""
echo "✅ Parrot Script is running!"
echo "   API:      http://localhost:8000"
echo "   Docs:     http://localhost:8000/docs"
echo "   Frontend: http://localhost:5173"
echo ""
echo "Run frontend with: cd frontend/react-app && npm run dev"
```

---

### TASK 11.3 — Write `README.md`

**Include:**
1. Prerequisites (brew packages, Python version)
2. One-time setup instructions (BlackHole, Ollama model pull, `.env`)
3. Quick start (3 commands)
4. Architecture overview (brief)
5. Troubleshooting (common macOS audio issues)

---

## Done Checklist

- [ ] Task 1.1 — Project scaffold
- [ ] Task 1.2 — Config
- [ ] Task 1.3 — Events
- [ ] Task 2.1 — Database
- [ ] Task 2.2 — Repositories
- [ ] Task 3.1 — Audio devices
- [ ] Task 3.2 — VAD
- [ ] Task 3.3 — Audio capture
- [ ] Task 4.1 — Transcription models
- [ ] Task 4.2 — Whisper transcriber
- [ ] Task 5.1 — Voice embeddings
- [ ] Task 5.2 — Speaker clustering
- [ ] Task 6.1 — LLM prompts
- [ ] Task 6.2 — Transcript chunker
- [ ] Task 6.3 — Summarizer
- [ ] Task 7.1 — WebSocket manager
- [ ] Task 7.2 — API routes
- [ ] Task 7.3 — FastAPI app
- [ ] Task 7.4 — Main entrypoint
- [ ] Task 8.1 — Pipeline core
- [ ] Task 8.2 — Pipeline wired to routes
- [ ] Task 9.1 — React app init
- [ ] Task 9.2 — API client
- [ ] Task 9.3 — WebSocket hook
- [ ] Task 9.4 — UI components
- [ ] Task 9.5 — App layout
- [ ] Task 10.1 — Vector search
- [ ] Task 11.1 — Integration tests
- [ ] Task 11.2 — Start script
- [ ] Task 11.3 — README

---

*TASKS.md v1.0 | Pair with PLAN.md | Feed both files to Claude Code at project start*