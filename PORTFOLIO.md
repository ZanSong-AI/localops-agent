# Portfolio Framing

## One-line pitch

Built a local-first personal operations agent that combines Apple Watch meeting capture, bounded personal-context retrieval, and read-only email evidence into cited task and email candidates, with on-device model routing and human approval before any local export.

## What makes it more than an LLM wrapper

- Real macOS/Apple Watch intake boundary through synced Voice Memos.
- Local speech recognition and local Ollama models on Apple Silicon.
- Deterministic source-quote validation around probabilistic extraction.
- Explicit task state machine and idempotent ingestion.
- Privacy-aware routing that blocks private cloud requests before transmission.
- Auditable model, task, approval, and reminder events.
- A bounded tool-selection loop rather than an unrestricted autonomous agent.
- Read-only reuse of a production-shaped communications pipeline instead of duplicating mailbox automation.
- Structured-output drift handling, exact citation validation, prompt-injection tests, and a conservative rewrite for risky email claims.
- A versioned Agent eval bank with isolated trials, outcome and trajectory graders, retained negative baselines, and latency/fallback disclosure.
- Deterministic policy and extractive-evidence fallbacks that keep the system useful when the local LLM is structurally unreliable.
- Human-confirmed long-term Context candidates instead of automatic memory mutation.
- Enterprise-shaped action envelopes with policy decisions, risk levels, idempotency, approval state, and simulation receipts.
- A bounded research pipeline that validates quotes and surfaces source conflict, staleness, and unknowns.
- Synthetic public demo path separated from private runtime state.

## Interview demo

1. Run `doctor` and explain why the Voice Memos path is a bounded source.
2. Process the synthetic meeting with `song-local` and show source-linked task candidates.
3. Run the operations agent on the synthetic Mail JSONL and show its selected tools and exact citations.
4. Show that the injected “ignore rules and send” text is treated as evidence, not executed.
5. Attempt reminder and email export before approval and show both hard failures.
6. Approve one candidate, export local VTODO/EML artifacts, and show that the email result is still `sent: false`.
7. Open the private dashboard and trace, then show the tests that block private cloud routing and unapproved actions.
8. Compare the retained 5/8 baseline with the 8/8 governed-system run and explain why fallback frequency and latency are disclosed alongside pass rate.
9. Show that a Context candidate cannot be exported before confirmation and that export does not write YAGE.
10. Approve a synthetic high-risk action and show the receipt still says `adapter_called: false` and `delivery_status: not_attempted`.
11. Run two conflicting synthetic research sources and show exact citations plus current/stale labels.

## Honest current limitations

- Apple Voice Memos has not yet synced into the standard container on this Mac, so real Watch audio intake is currently blocked at that first boundary.
- The upstream Qwen3 ASR environment is not installed; LocalOps intentionally reuses the already-working local MLX Whisper model.
- Cloud transport and direct Apple Reminders/Calendar writes are not implemented in the MVP.
- Email collection remains the responsibility of DailyDigest; LocalOps consumes explicit normalized artifacts and does not send mail.
- No speaker identification or diarization is attempted.
- The dashboard is generated static HTML, not a background service.
- The current eval result covers a small selected synthetic set; it is not a production-performance claim. The 8/8 system result includes deterministic fallbacks and had a 24.750-second median latency in that run.
- Context learning has not yet written or operated a production YAGE memory workflow.
- The action executor is a governance simulator, not an email/calendar/reminder delivery integration.
- Research synthesizes explicit local source packets; autonomous source discovery and live-web retrieval are not implemented.

## Resume bullet candidate

Designed and evaluated a local-first personal operations agent on Apple Silicon with on-device ASR, bounded context/mail/research tools, source-grounded long-term Context candidates, policy-controlled action simulation, deterministic fallbacks, SQLite audit trails, and human approval gates.

Any performance numbers added later must come from checked benchmark artifacts, not memory or estimates.
