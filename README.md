# ScamSlayer

> AI-powered scam-baiter — an AI persona answers scammer calls, keeps them on the line, transcribes everything, mines the funniest moments, and auto-generates short-form social clips.

**Yale SOM MGMT 673 — Generative AI & Social Media | Team Dead Ringers**  
ak3289 · ms4852 · na628 · prl28 · vm522 · yl2854

---

## Screenshots

### Dashboard — Live Call Monitor

![Dashboard](docs/screenshots/dashboard.png)

> [TODO: screenshot — call table with scam badges, "Simulate New Call" button]

### Simulate Dialog

![Simulate dialog](docs/screenshots/simulate_dialog.png)

> [TODO: screenshot — modal with textarea pre-filled with IRS scam lines, spinning loader]

### Call Detail — Transcript + Highlights

![Call detail](docs/screenshots/call_detail.png)

> [TODO: screenshot — chat bubbles (scammer red / Betty green), highlight sidebar with virality bars, clip player]

### Personas

![Personas](docs/screenshots/personas.png)

> [TODO: screenshot — Grandma Betty card with backstory, voice ID, scam-type badges]

---

## What's Mocked vs Real

| Component | State | What the mock does | What the real version needs |
|---|---|---|---|
| **Classifier Agent** | Mock | Always returns `{is_scam: true, confidence: 0.87, scam_type: "irs_impersonation"}` | Anthropic Claude call with TeleAntiFraud-28k prompt |
| **Persona Agent** | Mock | Always upserts and returns "Grandma Betty" | Per-scam-type persona selection from DB, dynamic generation |
| **Dialogue Agent** | Partial | Cycles through `fixtures/betty_responses.json` (13 lines); Claude SDK wired, toggled by `MOCK_CLAUDE=true` | Set `MOCK_CLAUDE=false` + `ANTHROPIC_API_KEY` |
| **Highlight Miner Agent** | Mock | Returns 3 template highlights with realistic scores | Sentiment + volume spike analysis on real transcript |
| **Editor Agent** | Stub | Runs `ffmpeg` to generate a 1-second black placeholder `.mp4`; falls back to empty file if ffmpeg missing | Real ffmpeg assembly from audio segments + caption burn-in |
| **Social Agent** | Mock | Hardcoded 8 hashtags + caption from top highlight snippet | Claude call for caption; post-time from Kitboga virality model |
| **Twilio Webhooks** | Stub | Accepts `POST /voice/incoming`, returns TwiML `<Connect><Stream>`; WebSocket handler scaffolded | Live Twilio number + ngrok tunnel |
| **Deepgram STT** | Mock | WebSocket receives audio frames but returns no transcript | `DEEPGRAM_API_KEY` + live audio stream from Twilio |
| **ElevenLabs TTS** | Mock | Returns silent bytes | `ELEVENLABS_API_KEY` + voice streaming |
| **`/api/calls/simulate`** | **Fully working** | Runs the entire 6-agent pipeline from scripted utterances — no Twilio required | Used for all demos |

> **TL;DR for the demo:** set `MOCK_CLAUDE=false` and supply `ANTHROPIC_API_KEY` to get real Claude dialogue. Everything else runs in mock mode with no other keys required.

---

## Quickstart

### Prerequisites

- Python 3.11+
- Node 20+ and npm 10+
- `ffmpeg` on PATH (optional — Editor Agent falls back to a stub if missing)

### 1 — Clone

```bash
git clone <repo-url>
cd scamslayer
```

### 2 — Python environment

```bash
# With uv (recommended — faster, no activation needed)
pip install uv
uv sync

# Or plain pip
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

### 3 — Frontend

```bash
cd frontend && npm install && cd ..
```

### 4 — Environment

```bash
cp .env.example .env
# Minimum to run the simulate demo:
#   ANTHROPIC_API_KEY=sk-ant-...   (only needed if MOCK_CLAUDE=false)
#   MOCK_CLAUDE=true               (default — skips all LLM calls)
```

### 5 — Start backend

```bash
uvicorn backend.app.main:app --reload --port 8000
```

The database (`scamslayer.db`) is created automatically on first boot.

### 6 — Start frontend

```bash
cd frontend && npm run dev
# → http://localhost:5173
```

### 7 — Run a simulation

Open `http://localhost:5173`, click **Simulate New Call**, paste scammer lines, and watch the pipeline run. No phone or API key required.

### 8 — (Optional) Live call testing

```bash
# Install and authenticate ngrok
ngrok http 8000
# Copy the https URL → NGROK_URL in .env
# Point your Twilio number's Voice webhook to: <NGROK_URL>/voice/incoming
```

See [docs/SETUP.md](docs/SETUP.md) for full API-key acquisition steps.

---

## Running Tests

```bash
# All backend tests (92 passing as of Phase 4)
.venv/bin/pytest backend/tests/ -v

# Single file
.venv/bin/pytest backend/tests/test_simulate.py -v
```

---

## Project Layout

```
scamslayer/
├── backend/
│   ├── app/
│   │   ├── main.py              FastAPI entrypoint + lifespan
│   │   ├── config.py            pydantic-settings; all env vars
│   │   ├── routes/
│   │   │   ├── calls.py         POST /simulate · GET /calls · GET /calls/{id} · …
│   │   │   ├── personas.py      CRUD /personas
│   │   │   ├── clips.py         /clips · /clips/{id}/generate
│   │   │   └── voice.py         Twilio /voice/incoming + WebSocket /voice/stream
│   │   ├── agents/
│   │   │   ├── classifier.py    ClassifierAgent → ClassifierResult
│   │   │   ├── persona.py       PersonaAgent   → PersonaResult
│   │   │   ├── dialogue.py      DialogueAgent  → DialogueResult
│   │   │   ├── highlights.py    HighlightMinerAgent → HighlightsResult
│   │   │   ├── editor.py        EditorAgent    → EditorResult
│   │   │   ├── social.py        SocialAgent    → SocialResult
│   │   │   └── fixtures/
│   │   │       └── betty_responses.json   13 in-character stall lines
│   │   └── db/
│   │       ├── models.py        SQLAlchemy 2.x: Call · Persona · TranscriptSegment · …
│   │       └── session.py       async engine · get_db · init_db
│   └── tests/                   pytest-asyncio, 92 tests
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── Dashboard.tsx    call table + simulate modal
│       │   ├── CallDetail.tsx   chat bubbles + highlight sidebar + clip player
│       │   ├── Personas.tsx     read-only persona cards
│       │   └── Clips.tsx        clip grid with inline video
│       └── lib/api.ts           typed fetch helpers for all endpoints
├── docs/
│   ├── ARCHITECTURE.md          mermaid agentic flow diagram
│   ├── SETUP.md                 API key acquisition walkthrough
│   ├── ETHICS.md                legal & ethical constraints
│   └── PRESENTATION.md          slide outline
├── analysis/                    Jupyter notebooks (virality, classifier)
├── .env.example                 all env vars with placeholder values
├── docker-compose.yml           Redis for arq background jobs
└── pyproject.toml               Python deps + pytest config
```

---

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full agentic flow diagram.

## Ethics & Legal

See [docs/ETHICS.md](docs/ETHICS.md). **Read before touching any call-related code.**

## API Keys

See [docs/SETUP.md](docs/SETUP.md) for where to get every credential.
