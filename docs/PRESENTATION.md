# Presentation Outline (~12 min)

## Slide 1 — Hook (1 min)
- Open with a 30s clip of Grandma Betty keeping a scammer on the line.
- "This call was 100% AI. The scammer had no idea."

## Slide 2 — Problem (1 min)
- $10B+ lost to phone scams annually (FTC 2023).
- Elderly victims targeted disproportionately.
- Existing solutions: spam filters (passive), legal enforcement (slow).
- Scam-baiting works — it wastes attacker resources and is entertaining enough to go viral.

## Slide 3 — Our Solution (1.5 min)
- ScamSlayer: inbound AI persona + viral content pipeline.
- Show the agentic flow diagram (ARCHITECTURE.md).
- Six agents: Classifier → Persona → Dialogue → Highlight Miner → Editor → Social.

## Slide 4 — GenAI Angle (2 min)
- Claude Sonnet powers the Dialogue Agent. Show the system prompt and a real transcript snippet.
- Why LLMs are uniquely suited: flexible persona adherence, ability to improvise stalls.
- ElevenLabs voice cloning: makes it convincingly human over the phone.

## Slide 5 — Demo (3 min)
- Live or recorded demo:
  1. Simulated scam call → dashboard shows call appearing.
  2. Real-time transcript populates.
  3. Highlight reel is mined post-call.
  4. Generated clip with captions is shown.
  5. Social caption + hashtags displayed.

## Slide 6 — Social Media Angle (1.5 min)
- Kitboga / Pleasant Green → millions of views per video.
- Our virality feature analysis (notebook 03): what makes scam-bait clips go viral.
- Pipeline closes the loop: call → clip → optimised post.

## Slide 7 — Honest Limitation (1 min)
- STT/TTS latency is the hardest problem. Current round-trip: ~800ms.
  Real-time phone conversation needs <300ms. Streaming chunked TTS is the fix.
- Recording consent in multi-party states requires additional legal groundwork for prod.

## Slide 8 — What's Next (1 min)
- Plug in Deepgram streaming + ElevenLabs streaming (one-session swap each).
- Real scammer dataset fine-tuning for the Classifier Agent.
- Fly.io production deploy with a real Twilio number.

## Slide 9 — References
- TeleAntiFraud-28k dataset (arXiv 2503.24115)
- FTC 2023 Consumer Sentinel Network Report
- FCC AI Robocall Ruling (Feb 2024)
- Kitboga YouTube channel — virality benchmarks
