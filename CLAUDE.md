# ScamSlayer — Project Context for Claude Code

## What This Project Is

ScamSlayer is the Yale SOM "Generative AI and Social Media" (Prof. Tauhid Zaman) final project by team **Dead Ringers**. It is an AI-powered scam-baiter: when a scammer calls, an AI persona (e.g. "Grandma Betty") answers, keeps them on the line, transcribes everything, flags the funniest moments, and auto-generates short-form social clips.

**Course framing: this is an analytics-based solution for a novel application (syllabus option 2).** Social media is a core pillar, not a bonus. The end-to-end pipeline closes the loop from raw scammer calls → transcripts → highlight analytics → viral short-form video.

## Team

Six members: Adithya Kumaresan Shanmugasundaram (ak3289), Manasa Sunkavalli (ms4852), Nick Arndt (na628), Pranay Loya (prl28), Vishal Mohnot (vm522), Yarin Lin (yl2854).

## Rubric Requirements (must be satisfied by final submission)

1. **Written report (10-15 pages, PDF).** Sections: Executive summary (with GitHub URL up top), Introduction (problem, market, GenAI angle, ethics), Implementation (system description, stack, agentic flow diagram, repo link), Results and Analysis (screenshots, sample outputs, honest critique, economics, competitive landscape), Conclusion (findings, roadmap), References.
2. **Final presentation (~10-15 min).** Problem → demo → AI angle → one honest limitation → what's next.
3. **GitHub repository** with a clear README that lets anyone clone, install, and run the full demo end-to-end.

## Architectural Decisions (locked in — do not change without discussion)

- **Language:** Python 3.11+ backend, TypeScript React frontend.
- **Backend framework:** FastAPI with WebSocket support.
- **Frontend:** React + Vite + TypeScript + Tailwind CSS. Simple, clean dashboard — no heavy UI lib.
- **Telephony:** Twilio Voice + Media Streams (WebSocket audio). Inbound-only for legal safety (see Ethics).
- **STT:** Deepgram streaming API (Nova-3 model).
- **LLM:** Anthropic Claude Sonnet (default: claude-sonnet-4-5). Use `anthropic` Python SDK.
- **TTS:** ElevenLabs streaming API. Persona voices configured per character.
- **Persistence:** SQLite for MVP (calls, transcripts, highlights, personas). Postgres migration path documented, not implemented.
- **Queue / background jobs:** Python `asyncio` tasks + `arq` (Redis) for post-call processing (highlight mining, clip export).
- **Video editing:** `ffmpeg` via `ffmpeg-python`. Vertical 9:16 output, baked-in captions via `whisper-timestamped` → SRT → ffmpeg burn-in.
- **Deployment (dev):** `ngrok` tunneling to local FastAPI for Twilio webhooks.
- **Deployment (demo):** Fly.io (app + Redis). Dockerfile required.

## Repo Layout (target)

```
scamslayer/
├── README.md                 ← clear setup + run instructions (rubric requirement)
├── CLAUDE.md                 ← this file
├── docker-compose.yml        ← local dev: backend, redis, ngrok
├── .env.example              ← every env var, placeholder values
├── pyproject.toml            ← Python deps (uv or poetry)
├── backend/
│   ├── app/
│   │   ├── main.py           ← FastAPI entrypoint
│   │   ├── routes/
│   │   │   ├── voice.py      ← Twilio webhooks + media stream WS
│   │   │   ├── calls.py      ← REST: list/fetch calls, transcripts, highlights
│   │   │   ├── personas.py   ← CRUD for personas
│   │   │   └── clips.py      ← GET generated video clips
│   │   ├── agents/
│   │   │   ├── persona.py    ← character generation + config
│   │   │   ├── dialogue.py   ← live LLM dialogue loop
│   │   │   ├── classifier.py ← scam classifier (rule-based MVP → ML)
│   │   │   ├── highlights.py ← transcript + audio highlight mining
│   │   │   ├── editor.py     ← ffmpeg clip assembly
│   │   │   └── social.py     ← caption + hashtag generator
│   │   ├── services/
│   │   │   ├── twilio_client.py
│   │   │   ├── deepgram_client.py
│   │   │   ├── elevenlabs_client.py
│   │   │   └── claude_client.py
│   │   ├── db/
│   │   │   ├── models.py     ← SQLAlchemy models
│   │   │   ├── session.py
│   │   │   └── migrations/
│   │   └── config.py         ← pydantic Settings
│   ├── tests/                ← pytest
│   └── scripts/
│       ├── seed_personas.py
│       └── run_highlight_job.py
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── src/
│   │   ├── App.tsx
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx    ← live call monitor
│   │   │   ├── CallDetail.tsx   ← transcript + highlights view
│   │   │   ├── Personas.tsx     ← create/edit personas
│   │   │   └── Clips.tsx        ← preview + download generated clips
│   │   ├── components/
│   │   └── lib/api.ts
│   └── tailwind.config.js
├── analysis/                 ← Jupyter notebooks for dataset work
│   ├── 01_scam_classifier_teleantifraud.ipynb
│   ├── 02_virality_scrape_kitboga.ipynb
│   ├── 03_virality_features.ipynb
│   └── data/                 ← gitignored; large files
└── docs/
    ├── ARCHITECTURE.md       ← agentic flow diagram (mermaid)
    ├── SETUP.md              ← getting API keys, ngrok, Twilio config
    ├── ETHICS.md             ← consent, recording laws, TCPA, data handling
    └── PRESENTATION.md       ← slide outline
```

## Agentic Flow

Six agents, orchestrated:

1. **Classifier Agent** — on incoming call: confidence score scam/not-scam from caller metadata + first 10s of audio.
2. **Persona Agent** — selects or generates a persona (backstory, voice, speech tics) appropriate to the scam type.
3. **Dialogue Agent** — live STT → LLM → TTS loop during the call. System prompt locks persona in character and optimizes for stall time.
4. **Highlight Miner Agent** — post-call: scans transcript + audio for frustration spikes (volume, profanity, sentiment drops), outputs timestamp-tagged highlight list.
5. **Editor Agent** — stitches highlights into vertical 9:16 clip, bakes captions, adds intro/outro cards.
6. **Social Agent** — writes caption, picks hashtags, suggests posting time based on virality analysis of Kitboga-style content.

## Data

- **TeleAntiFraud-28k** (arXiv 2503.24115) — train/evaluate the Classifier Agent.
- **Scraped Kitboga / Pleasant Green / Scammer Payback clips** (yt-dlp + YouTube Data API) — train the virality features used by the Social Agent. Store in `analysis/data/` (gitignored).
- **BothBosu/scam-dialogue** (Hugging Face) — supplementary transcript data for persona prompting.

## Ethics & Legal (non-negotiable — read before coding anything call-related)

- **Inbound only.** The system NEVER initiates outbound calls. It only engages callers who dial in. This is critical for TCPA / FCC compliance (Feb 2024 AI robocall ruling).
- **Recording disclosure.** All call recordings must comply with state two-party consent laws. For the demo, simulate calls with team members only.
- **No real PII.** Test data only. Redact anything that looks like a real SSN, CC, or address in logs.
- **Secrets.** All API keys in `.env` only. `.env` is gitignored. `.env.example` ships in repo with placeholder values. NEVER commit keys. NEVER put keys in the report PDF.
- **Rate limits.** Include timeouts and max-call-length guards so a runaway bill can't happen.

## Coding Conventions

- **Python:** type hints mandatory. `ruff` for lint, `black` for format, `mypy` for types. Async for anything touching network I/O.
- **TypeScript:** strict mode. Functional components + hooks. No class components.
- **Tests:** pytest for backend. At least smoke tests for each agent. Frontend: Vitest for lib/, no need for component tests on MVP.
- **Commits:** conventional commits (`feat:`, `fix:`, `docs:`). One logical change per commit.
- **Docs:** every agent gets a docstring explaining inputs, outputs, and side effects. ARCHITECTURE.md kept current with code.

## Build Principles

- **Ship vertical slices.** Prefer an end-to-end thin pipeline (even if each stage is dumb) over one perfectly-built stage.
- **Mocks over nothing.** If an API isn't wired up yet, return a hardcoded fixture so downstream work isn't blocked.
- **Observable.** Every agent logs structured JSON events to the DB so the dashboard can replay any call.
- **No AI slop.** Avoid generic ChatGPT-flavored error messages, generic UI, or boilerplate that doesn't serve the product. If a detail looks cookie-cutter, improve it.

## What NOT To Build (explicit scope cuts)

- No user auth / accounts. Single-tenant demo.
- No real TikTok/Instagram posting API integration. Clips are rendered and downloadable, nothing more.
- No custom voice cloning. Use ElevenLabs pre-made voices.
- No mobile app. Web dashboard only.
- No real-time translation. English only.
