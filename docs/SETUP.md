# Getting API Keys & Local Setup

## Anthropic (Claude)
1. Sign in at console.anthropic.com
2. Settings → API Keys → Create Key
3. Paste as `ANTHROPIC_API_KEY` in `.env`
4. Default model: `claude-sonnet-4-5` (set in `config.py`)

## Twilio
1. Sign up at twilio.com/try-twilio (free trial gives $15 credit)
2. Console → Account SID + Auth Token → paste into `.env`
3. Buy a phone number (Voice capable)
4. Phone Numbers → Manage → your number → Voice Configuration:
   - Webhook (HTTP POST): `<NGROK_URL>/voice/incoming`
   - Status Callback: `<NGROK_URL>/voice/status`
5. Enable Media Streams on the number under "Experimental features"

## Deepgram
1. Sign up at console.deepgram.com
2. API Keys → Create Key
3. Paste as `DEEPGRAM_API_KEY`
4. Model used: `nova-3` (lowest latency, highest accuracy for English phone audio)

## ElevenLabs
1. Sign up at elevenlabs.io
2. Profile → API Keys → copy key → `ELEVENLABS_API_KEY`
3. To find voice IDs: GET `https://api.elevenlabs.io/v1/voices` with your key
4. Default voice for Grandma Betty: `EXAVITQu4vr4xnSDxMaL` (Bella)

## ngrok
1. Install: `brew install ngrok` (Mac) or download from ngrok.com
2. Sign up (free tier works) and run: `ngrok config add-authtoken <token>`
3. Start tunnel: `ngrok http 8000`
4. Copy the `https://xxxx.ngrok-free.app` URL into `NGROK_URL` in `.env`
5. Keep ngrok running the entire time you're testing calls

## Redis (for arq background jobs)
Local dev: `docker compose up -d redis` — that's it.
Prod (Fly.io): `fly redis create` and paste the connection URL as `REDIS_URL`.
