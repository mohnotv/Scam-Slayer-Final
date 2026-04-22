# ScamSlayer — Ethics & Legal Compliance

**Read this before touching any call-related code.**

ScamSlayer operates in a legally and ethically sensitive space: it uses AI to intercept and engage telephone callers. This document explains the constraints we operate under, why they exist, and what the code does (and must not do) to stay within them.

---

## 1. Core Principle: Inbound Only

**ScamSlayer never initiates outbound calls.** It only engages callers who dial into our Twilio number.

### Why this matters

The FCC's February 2024 ruling (In the Matter of Rules and Regulations Implementing the Telephone Consumer Protection Act) explicitly classified AI-generated voices used in robocalls as a violation of the TCPA without prior express written consent. An outbound AI caller — even targeting known scammers — would be illegal under this ruling.

Inbound-only operation means the *scammer* is the one initiating contact. We are responding, not soliciting.

### How it's enforced in code

- `voice.py` only registers `POST /voice/incoming` (inbound webhook) and `WS /voice/stream`.
- There is no outbound-call route, no Twilio `calls.create()` call, and no job queue task that dials numbers.
- **Do not add outbound calling capability without explicit legal review.**

---

## 2. Recording Laws

Telephone recording law varies by jurisdiction and applies even when the "caller" is a scammer.

### Federal baseline

Federal law (18 U.S.C. § 2511) allows recording a call you participate in without notifying the other party ("one-party consent"). The AI persona is a participant, so federal law would permit recording.

### State law (stricter)

Twelve US states require **all parties** to consent to recording ("two-party" or "all-party" consent): California, Connecticut, Florida, Illinois, Maryland, Massachusetts, Michigan, Montana, Nevada, New Hampshire, Oregon, Pennsylvania, and Washington. A scammer calling from or into one of these states triggers this requirement.

### Demo policy

For this course project:
- Only test with team members calling in. Do not publish the phone number.
- Do not place the number on any website, forum, or public listing.
- All recorded audio stays on local machines or the demo server and is deleted after the demo.

### Production path (if this were to launch)

- Add an IVR disclosure before the persona picks up: *"This call may be recorded for quality and research purposes."*
- Geo-fence or add a blanket "this call is recorded" disclosure to comply with the strictest state standard.
- Consult an attorney before enabling live calls outside of team-member testing.

---

## 3. PII Handling

Scammers sometimes ask for — or volunteers — real-looking Social Security numbers, credit card numbers, and addresses. These must never reach the database in plaintext.

### Current state

The simulate endpoint does not scrub PII because it uses scripted utterances from the developer. The live WebSocket handler writes transcript segments directly to the DB without scrubbing.

### Required before any live public deployment

Add a PII scrubber in `backend/app/routes/voice.py` before the `TranscriptSegment` INSERT:

```python
import re

_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CC_RE  = re.compile(r"\b(?:\d[ -]?){15,16}\b")

def scrub_pii(text: str) -> str:
    text = _SSN_RE.sub("[SSN REDACTED]", text)
    text = _CC_RE.sub("[CC REDACTED]", text)
    return text
```

### Data retention

- `analysis/data/` is gitignored. Never commit scraped audio, real transcripts, or PII-laden datasets.
- The SQLite DB (`scamslayer.db`) is also gitignored.
- If deploying to Fly.io, ensure the volume is encrypted at rest (Fly volumes are encrypted by default).

---

## 4. API Keys & Secrets

| Rule | Detail |
|---|---|
| All keys in `.env` only | `.env` is gitignored. Never commit it. |
| `.env.example` ships in the repo | Placeholder values only — no real credentials. |
| Never in the report PDF | The written report must not contain any API key, even partially. |
| Rotate immediately if leaked | If a key is accidentally committed: revoke it in the provider console before pushing any fix. Use `git filter-repo` or contact GitHub support to purge the secret from history. |
| Shared team key | Create a single key per service under a shared team account. Rotate it after the course ends. |

---

## 5. Rate Limits & Cost Guards

Runaway API calls can produce unexpected bills. Safeguards in place:

| Guard | Implementation |
|---|---|
| Max call duration | `MAX_CALL_DURATION_SECONDS` (default 300 s) enforced in `voice.py`; the WebSocket is closed and the call is hung up via Twilio API after this limit. |
| Deepgram session cleanup | The streaming session is explicitly closed in the `"stop"` event handler in `voice.py`. |
| ElevenLabs session cleanup | Same — closed when the call ends, not left open indefinitely. |
| Anthropic spend limit | Set a hard monthly budget alert in [console.anthropic.com/settings/limits](https://console.anthropic.com/settings/limits). Recommended: $10/month for a course demo. |
| Twilio trial limits | The Twilio free trial prevents calls longer than a few minutes and restricts calls to verified numbers only — a built-in guard during development. |

---

## 6. Responsible Use

### Target audience for the technique

Scam-baiting is a well-established citizen counter-fraud practice (see: Kitboga, Pleasant Green, Scammer Payback). Its goal is to:

1. Waste scammers' time so they have less time for real victims.
2. Generate public awareness content that helps potential victims recognize scam scripts.
3. Gather transcripts that help researchers study fraud patterns.

### What this system must not be used for

- **Harassing legitimate callers.** If a caller is clearly not a scammer, hang up gracefully.
- **Targeting specific individuals.** The system responds to inbound calls only; do not configure it to call or engage a specific person.
- **Competing businesses or political calls.** TCPA and FEC rules apply.
- **Evidence for law enforcement without counsel.** Recording laws vary; consult an attorney before sharing recordings with law enforcement.

### On the "AI persona" question

Grandma Betty is an AI persona pretending to be an elderly person. This raises a honesty question: is it ethical to deceive the scammer?

Our position: scammers operate by deception (false authority, false urgency, false identity). Using a counter-deception against a bad-faith actor is ethically distinct from deceiving a good-faith caller. The system is designed to waste scammers' time, not to extract information or money from them.

Betty is explicitly programmed to **never provide real financial information** (no real SSNs, bank accounts, or wire transfer instructions) even in character. This is enforced in the Dialogue Agent's system prompt.

---

## 7. Course & Academic Integrity

- This project is a technical demonstration for MGMT 673. It is not a commercial product.
- No real scammer calls were made or recorded in the course of development. All testing used the `/api/calls/simulate` endpoint with scripted utterances between team members.
- The TeleAntiFraud-28k dataset (cited in the report) is used for analysis only and is not redistributed.
- Kitboga-style YouTube clips were scraped for virality feature analysis under fair use (research, no redistribution of the underlying clips).
