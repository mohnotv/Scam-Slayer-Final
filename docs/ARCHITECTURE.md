# ScamSlayer — Agentic Architecture

## End-to-End Flow

```mermaid
flowchart TD
    CALLER([Scammer calls Twilio number])
    TW[Twilio Voice\nMedia Streams]
    CL[Classifier Agent\nscam? + type]
    PA[Persona Agent\nselect character]
    DG[Deepgram STT\nNova-3 streaming]
    DI[Dialogue Agent\nClaude Sonnet]
    EL[ElevenLabs TTS\nstreaming voice]
    DB[(SQLite DB\ncalls · transcripts\nhighlights · events)]
    HM[Highlight Miner Agent\nfrustration detection]
    ED[Editor Agent\nffmpeg 9:16 clip]
    SO[Social Agent\ncaption + hashtags]
    UI[Dashboard\nReact + Vite]

    CALLER -->|inbound only| TW
    TW -->|POST /voice/incoming| CL
    CL -->|ClassifierResult| PA
    PA -->|Persona row| TW
    TW <-->|WS /voice/stream| DG
    DG -->|TranscriptChunk| DI
    DI -->|utterance text| EL
    EL -->|audio bytes| TW
    CL & PA & DI & HM & ED & SO -->|AgentEvents| DB
    TW -->|call ended| HM
    HM -->|Highlight rows| ED
    ED -->|Clip row| SO
    DB -->|REST /calls /clips| UI
```

## Agent Responsibilities

| Agent | Trigger | Inputs | Outputs | Status |
|---|---|---|---|---|
| Classifier | Incoming call | caller metadata | ClassifierResult | Mock |
| Persona | Post-classification | scam_type | Persona row | Mock |
| Dialogue | Each STT chunk | transcript + history | utterance text | Partial (Claude wired) |
| Highlight Miner | Call ended | transcript rows | Highlight rows | Mock |
| Editor | Post-highlights | highlights + audio | Clip row | Stub |
| Social | Post-editor | clip + call + highlights | caption + hashtags | Mock |

## Data Flow — DB Tables

```
Call ──┬── Transcript (many)
       ├── Highlight (many)
       ├── Clip (many)
       ├── AgentEvent (many)  ← full audit log
       └── Persona (FK)
```

## WebSocket Protocol (Twilio → Backend)

Twilio sends JSON frames over the WS:
- `{"event": "connected"}` — stream established
- `{"event": "start", "start": {...}}` — call metadata
- `{"event": "media", "media": {"payload": "<base64-mulaw>"}}` — audio chunk
- `{"event": "stop"}` — call ended

Backend streams TTS audio back as base64-encoded mulaw in `{"event": "media"}` frames.
