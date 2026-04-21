# ScamSlayer

> AI-powered scam-baiter — an AI persona answers scammer calls, keeps them on the line, transcribes everything, mines highlights, and auto-generates short-form social clips.

**Yale SOM MGMT 673 — Generative AI & Social Media | Team Dead Ringers**  
ak3289 · ms4852 · na628 · prl28 · vm522 · yl2854

---

## Quickstart

### Prerequisites

- Python 3.11+
- Node 20+ and npm 10+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- Docker + Docker Compose (for Redis in local dev)
- [ngrok](https://ngrok.com/) (to expose your local server to Twilio)

### 1 — Clone

```bash
git clone <repo-url>
cd scamslayer
```

### 2 — Backend

```bash
# Install Python deps with uv (recommended)
uv sync

# Or with pip into a venv
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

### 3 — Frontend

```bash
cd frontend
npm install
```

### 4 — Environment variables

```bash
cp .env.example .env
# Fill in your API keys — see docs/SETUP.md for where to get each one
```

### 5 — Start local services (Redis)

```bash
docker compose up -d redis
```

### 6 — Run backend

```bash
uvicorn backend.app.main:app --reload --port 8000
```

### 7 — Run frontend dev server

```bash
cd frontend
npm run dev
# Opens on http://localhost:5173
```

### 8 — Expose to Twilio (for live call testing)

```bash
ngrok http 8000
# Copy the https URL into NGROK_URL in .env
# Point your Twilio number's webhook to: <NGROK_URL>/voice/incoming
```

---

## Project Status

| Agent | Status | Notes |
|---|---|---|
| Classifier Agent | **Mock** | Returns hardcoded `{scam: true, confidence: 0.95}` |
| Persona Agent | **Mock** | Returns static "Grandma Betty" persona |
| Dialogue Agent | **Partial** | Claude API wired; TTS/STT still mocked |
| Highlight Miner | **Mock** | Returns fixture highlights from transcript |
| Editor Agent | **Stub** | ffmpeg plumbing in place; clip assembly not complete |
| Social Agent | **Mock** | Returns hardcoded caption + hashtags |
| Twilio Webhooks | **Mock** | Accepts call, returns TwiML; no live audio yet |
| Deepgram STT | **Mock** | Returns fixture transcript chunks |
| ElevenLabs TTS | **Mock** | Returns silent audio bytes |

---

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full agentic flow diagram.

## Ethics & Legal

See [docs/ETHICS.md](docs/ETHICS.md). **Read before touching any call-related code.**

## Getting API Keys

See [docs/SETUP.md](docs/SETUP.md).
