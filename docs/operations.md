# Operations

## Local Setup

### Python

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Frontend

```bash
cd frontend
npm install
cd ../..
```

### Environment

```bash
cp .env.example .env
```

Review at minimum:

- `AUDIO_DEVICE_INDEX`
- `OLLAMA_MODEL`
- `API_TOKEN`
- `CORS_ORIGINS`

## Runtime Commands

### Backend with reload

```bash
source .venv/bin/activate
uvicorn backend.api.server:app --host 127.0.0.1 --port 8000 --reload
```

### Backend without reload

```bash
source .venv/bin/activate
uvicorn backend.api.server:app --host 127.0.0.1 --port 8000 --log-level info
```

### Frontend dev server

```bash
cd frontend
npm run dev
```

### Production-style backend

```bash
source .venv/bin/activate
gunicorn -w 2 -k uvicorn.workers.UvicornWorker --bind 127.0.0.1:8000 backend.api.server:app
```

### Helper startup

```bash
./scripts/start_meeting.sh
```

This helper script:

- verifies `ffmpeg` and `ollama` exist
- starts `ollama serve`
- starts `uvicorn backend.api.server:app`
- writes logs to `/tmp/parrot-script-ollama.log` and `/tmp/parrot-script-backend.log`

## Environment Variables

### Backend/API

- `API_HOST`: defaults to `127.0.0.1`
- `API_PORT`: defaults to `8000`
- `API_RELOAD`: default reload toggle for `backend.main`
- `API_WORKERS`: worker count when not using reload
- `API_LOG_LEVEL`: uvicorn log level
- `API_TOKEN`: shared bearer token for REST and WebSocket auth
- `CORS_ORIGINS`: JSON-style or comma-parsed origin list

### Audio

- `AUDIO_DEVICE_INDEX`
- `AUDIO_SAMPLE_RATE`
- `AUDIO_CHUNK_SECONDS`
- `AUDIO_VAD_AGGRESSIVENESS`

### Whisper

- `WHISPER_MODEL`
- `WHISPER_DEVICE`
- `WHISPER_COMPUTE_TYPE`
- `WHISPER_BEAM_SIZE`

### Ollama

- `OLLAMA_BASE_URL`
- `OLLAMA_MODEL`
- `OLLAMA_TIMEOUT`

### Storage

- `DB_PATH`
- `CHROMA_PATH`

### Diarization and summaries

- `MAX_SPEAKERS`
- `SPEAKER_CLUSTER_THRESHOLD`
- `EMBEDDING_WINDOW_SIZE`
- `SUMMARY_CHUNK_SIZE`
- `SUMMARY_MAX_TOKENS`

## Network and Security Posture

### Intended network shape

- Vite dev server listens on `127.0.0.1:5173`
- FastAPI listens on `127.0.0.1:8000`
- Ollama listens on `127.0.0.1:11434`

### Security assumptions

- The API is protected by a single shared token.
- CORS is configured for the local frontend origins.
- WebSocket auth uses the same token as the REST API.
- The main protection goal is to reduce accidental or remote access to local services.
- The app does not attempt to sandbox data from other malicious local processes.

### Security-sensitive files

- `backend/config.py`
- `backend/api/auth.py`
- `backend/api/server.py`
- `frontend/react-app/src/api/client.ts`
- `frontend/react-app/src/hooks/useWebSocket.ts`
- `frontend/react-app/vite.config.ts`

## Audio Capture Notes

- Audio capture relies on OS-specific FFmpeg frameworks (`avfoundation`, `dshow`, `pulse`). Provide the right `device_index` depending on platform.
- BlackHole (macOS), Stereo Mix (Windows), or pavucontrol (Linux) is the expected routing path for system-audio.
- `scripts/list_audio_devices.py` helps identify the current device index.
- The app captures whichever device is configured. If that device includes unrelated system audio, it will also be transcribed.

## Validation and Quality Gates

### Backend tests

```bash
PYTHONPYCACHEPREFIX=/tmp/parrot-script-pycache .venv/bin/python -m pytest -q
```

### Frontend typecheck

```bash
cd frontend/react-app
npm run typecheck
```

### Frontend build

```bash
cd frontend/react-app
npm run build
```

### Utility checks

- `scripts/test_whisper.py --file <wav>`: basic transcription smoke test.
- `scripts/test_ollama.py`: local Ollama connectivity and generate call.

## Troubleshooting

### Backend unreachable

- Check `uvicorn` is running on `127.0.0.1:8000`.
- Open `http://127.0.0.1:8000/health`.
- Confirm the frontend is using the correct token.
- Confirm Vite proxy settings still point to `127.0.0.1:8000`.

### WebSocket keeps reconnecting

- Confirm the selected meeting exists and the backend is up.
- Confirm the token matches `API_TOKEN`.
- Check whether the socket is closing with auth failure.
- Watch the runtime panel in the UI for `unauthorized` vs `reconnecting` state.

### Summary route fails

- Check `ollama serve` is running.
- Confirm the model exists in `ollama list`.
- Confirm `OLLAMA_BASE_URL` is reachable.
- Check for `503 Ollama unavailable` responses.

### No transcript appears

- Confirm FFmpeg can access the configured audio device.
- Confirm the audio device actually receives meeting audio.
- Check whether VAD is filtering out all chunks.
- Run `scripts/test_whisper.py` on a known WAV file to isolate Whisper from capture.

## Deployment Caveat

This repo is production-leaning for local/private use, but it is not a full multi-user web product. If you expose it beyond loopback, you need stronger auth, secret handling, reverse-proxy controls, and transport hardening.
