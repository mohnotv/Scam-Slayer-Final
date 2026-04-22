# ScamSlayer — Setup & API Key Walkthrough

This guide covers every external credential the project uses, where to get it, and exactly where to put it. All keys go in `.env` (gitignored — never commit this file).

```bash
cp .env.example .env   # start here
```

---

## Minimum to run the demo (no real calls)

You need **zero external API keys** if `MOCK_CLAUDE=true` (the default). Just install deps and run:

```bash
uvicorn backend.app.main:app --reload --port 8000
# frontend:
cd frontend && npm run dev
```

Open `http://localhost:5173`, click **Simulate New Call**, and the full 6-agent pipeline runs locally.

To get real Claude dialogue (recommended for the demo):

```
MOCK_CLAUDE=false
ANTHROPIC_API_KEY=sk-ant-...
```

---

## 1. Anthropic (Claude Sonnet)

Used by: **Dialogue Agent** (real conversation), and optionally the Classifier and Social agents.

**Steps:**
1. Go to [console.anthropic.com](https://console.anthropic.com) and sign in.
2. Click **Settings** (bottom-left) → **API Keys** → **Create Key**.
3. Name it `scamslayer-dev` and copy the key immediately (shown once).
4. In `.env`:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   MOCK_CLAUDE=false
   ```

**Model:** `claude-sonnet-4-5` (set in `backend/app/config.py`). The Dialogue Agent uses 1–2 API calls per scammer utterance.

**Cost estimate (demo):** < $0.05 per simulated call at Sonnet pricing. Set a [spend limit](https://console.anthropic.com/settings/limits) in the console to avoid surprises.

---

## 2. Twilio (phone number + webhooks)

Used by: **voice.py** (`POST /voice/incoming`, `WS /voice/stream`). Not needed for simulate mode.

**Steps:**
1. Sign up at [twilio.com/try-twilio](https://www.twilio.com/try-twilio) — free trial gives ~$15 credit, enough for hours of testing.
2. From the [Console Dashboard](https://console.twilio.com/):
   - Copy **Account SID** (starts with `AC`) → `TWILIO_ACCOUNT_SID`
   - Copy **Auth Token** → `TWILIO_AUTH_TOKEN`
3. Buy a phone number:
   - **Phone Numbers** → **Manage** → **Buy a number**
   - Filter: Country = US, Capabilities = Voice. Buy any number.
4. Configure the number's webhook:
   - **Phone Numbers** → **Manage** → click your number
   - Under **Voice Configuration**:
     - **A call comes in:** Webhook, HTTP POST, `<NGROK_URL>/voice/incoming`
     - **Call Status Changes:** `<NGROK_URL>/voice/status`
   - Save.
5. Enable Media Streams (required for real-time audio):
   - Same number settings page → **Experimental features** → enable **Media Streams**.
6. In `.env`:
   ```
   TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   TWILIO_PHONE_NUMBER=+15005550006
   ```

**Testing:** Call your Twilio number from a cell phone. You should hear the persona respond (or silence in mock TTS mode).

---

## 3. Deepgram (speech-to-text)

Used by: the WebSocket handler in **voice.py** to transcribe live call audio. Not needed for simulate mode.

**Steps:**
1. Sign up at [console.deepgram.com](https://console.deepgram.com) — $200 free credit on signup.
2. **API Keys** → **Create a New API Key** → name it `scamslayer`.
3. Copy the key:
   ```
   DEEPGRAM_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

**Model used:** `nova-3` — Deepgram's lowest-latency model, optimized for telephone audio (8 kHz μ-law). Configured in `backend/app/services/deepgram_client.py`.

**Cost estimate:** Nova-3 is ~$0.0043/min for streaming. A 5-minute call costs ~$0.02.

---

## 4. ElevenLabs (text-to-speech)

Used by: the WebSocket handler to synthesize Betty's voice in real time. Not needed for simulate mode.

**Steps:**
1. Sign up at [elevenlabs.io](https://elevenlabs.io) — free tier includes 10,000 characters/month.
2. Click your profile avatar (top-right) → **API Keys** → **Create API Key**.
3. Copy the key:
   ```
   ELEVENLABS_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
4. Find Betty's voice ID — the default is `EXAVITQu4vr4xnSDxMaL` (Bella, a warm elderly-sounding voice). To browse other voices:
   ```bash
   curl https://api.elevenlabs.io/v1/voices \
     -H "xi-api-key: $ELEVENLABS_API_KEY" | jq '.voices[] | {name, voice_id}'
   ```
5. Update the Persona record in the DB or seed script to use your chosen voice ID.

**Cost estimate:** Free tier is plenty for demos. Paid plans start at $5/month for 30,000 chars.

---

## 5. ngrok (Twilio webhook tunnel)

Required to receive live Twilio calls on your local machine. Not needed for simulate mode.

**Steps:**
1. Install:
   ```bash
   # macOS
   brew install ngrok

   # Linux / Windows: download from https://ngrok.com/download
   ```
2. Sign up for a free account at [ngrok.com](https://ngrok.com) and get your authtoken from the dashboard.
3. Authenticate once:
   ```bash
   ngrok config add-authtoken <YOUR_AUTHTOKEN>
   ```
4. Start the tunnel (keep this terminal open during testing):
   ```bash
   ngrok http 8000
   ```
   You'll see output like:
   ```
   Forwarding  https://a1b2c3d4.ngrok-free.app -> http://localhost:8000
   ```
5. Copy the `https://...ngrok-free.app` URL:
   ```
   NGROK_URL=https://a1b2c3d4.ngrok-free.app
   ```
6. Paste `<NGROK_URL>/voice/incoming` as your Twilio webhook URL (see step 4 in Twilio section).

> **Note:** The free ngrok URL changes every time you restart ngrok. Update the Twilio webhook URL after each restart, or pay for a static ngrok domain ($8/month).

---

## 6. Redis (background jobs with arq)

Used by: the `arq` job queue for post-call processing (highlight mining, clip assembly). Optional for the simulate endpoint, which runs synchronously.

**Local dev:**
```bash
docker compose up -d redis
# Redis runs on localhost:6379 — no auth, matches the REDIS_URL default
```

**Production (Fly.io):**
```bash
fly redis create --name scamslayer-redis --region iad
# Copy the connection URL it prints:
REDIS_URL=redis://default:password@scamslayer-redis.flycast:6379
```

---

## Complete `.env` Reference

```bash
# ── LLM ───────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-...        # required if MOCK_CLAUDE=false
MOCK_CLAUDE=true                    # false = real Claude, true = fixture responses

# ── Twilio ────────────────────────────────────────────────────────────────────
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_PHONE_NUMBER=+15005550006

# ── Deepgram ──────────────────────────────────────────────────────────────────
DEEPGRAM_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# ── ElevenLabs ────────────────────────────────────────────────────────────────
ELEVENLABS_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# ── ngrok ─────────────────────────────────────────────────────────────────────
NGROK_URL=https://xxxx.ngrok-free.app   # added to CORS allow_origins

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL=sqlite+aiosqlite:///./scamslayer.db
# For Postgres: DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/scamslayer

# ── Redis ─────────────────────────────────────────────────────────────────────
REDIS_URL=redis://localhost:6379

# ── App ───────────────────────────────────────────────────────────────────────
LOG_LEVEL=INFO
DEBUG=false
MAX_CALL_DURATION_SECONDS=300       # hard hangup guard
```

---

## Checking your setup

```bash
# Backend health check
curl http://localhost:8000/health
# → {"status": "ok", "service": "scamslayer"}

# Run a simulate call (no external keys needed)
curl -X POST http://localhost:8000/api/calls/simulate \
  -H "Content-Type: application/json" \
  -d '{"scammer_utterances": ["This is the IRS, you owe $3000.", "Pay now or be arrested."]}'

# Run the full test suite
.venv/bin/pytest backend/tests/ -v
```
