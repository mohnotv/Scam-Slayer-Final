# Ethics & Legal Compliance

## Core Principle: Inbound Only

ScamSlayer **never initiates outbound calls**. It only engages callers who dial in.

This is non-negotiable for FCC/TCPA compliance following the February 2024 ruling that
classified AI-generated voices in robocalls as illegal without prior consent.

## Recording Laws

- **Federal (federal one-party consent):** recording a call you participate in is legal federally.
- **State two-party consent states (CA, FL, IL, etc.):** both parties must consent.
- **Demo policy:** for this project, only test calls between team members. Do not place
  the number on any public-facing platform without proper disclosures in place.
- **IVR disclosure:** future production version should play "This call may be recorded"
  before the persona picks up.

## PII Handling

- No real SSNs, credit card numbers, or addresses should ever reach the DB.
- If a test scammer says a real-looking SSN: redact it in the transcript before storing.
  (Implement a regex scrubber in `backend/app/agents/dialogue.py` before prod.)
- `analysis/data/` is gitignored. Never commit scraped audio or PII-laden transcripts.

## API Keys & Secrets

- All keys in `.env` only. `.env` is gitignored.
- `.env.example` ships in repo with placeholder values.
- **NEVER** commit keys. **NEVER** put keys in the report PDF.
- Rotate keys immediately if accidentally pushed.

## Rate Limits & Cost Guards

- `MAX_CALL_DURATION_SECONDS` (default 300) is enforced in the WebSocket handler.
  The call is programmatically hung up after this limit.
- Deepgram and ElevenLabs sessions are closed when the call ends, not left dangling.
- Add a hard budget alert in Anthropic console for the team's API key.

## Responsible Disclosure

The scam-baiting technique is aimed at socially harmful actors (scammers targeting elderly victims).
The system should not be repurposed to troll, harass, or waste the time of legitimate callers.
