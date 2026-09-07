# LocalOps Agent

LocalOps Agent is a local-first personal operations system for Apple Watch meeting capture, bounded YAGE context retrieval, read-only email evidence, evidence-bound task and email proposals, human approval, reminders, and auditable model routing.

It is a portfolio project and a real personal tool. The first rule is simple: understanding may be automatic; action is not.

## What works now

- Reuses YAGE's public [`grapeot/intake-skill`](https://github.com/grapeot/intake-skill) contract to find Apple Voice Memos already synced to macOS.
- Uses the Mac's existing MLX Whisper model for private, on-device transcription.
- Uses `song-local` for routine extraction and `song-deep` only for explicit deep review.
- Requires a source quote for every proposed task. Unsupported tasks are dropped rather than guessed.
- Stores every task as `candidate`; only a human can move it to `approved`.
- Shows only approved tasks in the reminder queue and exports approved tasks as local `.ics` VTODO files.
- Keeps state in SQLite, model output in JSON, and transitions in an audit log.
- Generates a private static HTML dashboard.
- Retrieves a small, bounded YAGE context bundle when explicitly requested.
- Can let `song-local` choose between bounded YAGE Context and an explicitly selected DailyDigest/Apple Mail JSONL source.
- Produces cited information findings and candidate email drafts without changing Mail state.
- Requires a separate human transition before an email draft can be exported as a local `.eml`; sending is not a tool.
- Stores a private per-run trace with the plan, safe tool calls, raw model result, validated citations, warnings, and `external_actions: none`.
- Includes a synthetic regression/capability eval harness with isolated trials, trajectory graders, exact-citation checks, latency reporting, and retained failure reports.
- Falls back to deterministic policy, extractive evidence, and a conservative candidate draft when the local model returns invalid structure; the fallback cannot approve or send.
- Proposes long-term Context candidates from one explicit local note, preserves exact evidence, and requires the operator to confirm before a local YAGE-review artifact can be exported.
- Stores evidence-bound enterprise action envelopes with risk, policy, idempotency keys, approval state, and simulation receipts; no external adapter is enabled.
- Synthesizes an explicit public/sanitized research packet locally, validates source quotes, flags source conflicts, and labels missing/stale publication dates.

## Safety boundary

- Private and sensitive content can only use local models.
- A cloud route requires both `public`/`sanitized` classification and explicit `--allow-cloud`; cloud transport is deliberately not implemented in this MVP.
- Transcript text is untrusted input, not instructions.
- No microphone recording, speaker identification, contact lookup, automatic message sending, mailbox mutation, calendar mutation, or public dashboard exposure.
- Nightly automatic processing is disabled until the operator explicitly chooses to enable it.
- Context export does not write the YAGE knowledge base; action simulation never calls Mail, Calendar, Reminders, or messaging adapters; research does not autonomously browse the web.
- Runtime data lives under `.localops/` and is ignored by Git.

## Quick start

No package install is required for the development commands:

```bash
cd LocalOpsAgent
export PYTHONPATH=src
python3 -m localops_agent doctor
python3 -m localops_agent process tests/fixtures/synthetic_meeting.txt --engine mock --privacy public
python3 -m localops_agent tasks --status candidate
python3 -m localops_agent approve 1
python3 -m localops_agent due
python3 -m localops_agent export-ics 1
python3 -m localops_agent dashboard
```

Open `.localops/dashboard.html` locally after generation. The synthetic fixture contains no real meeting or personal data.

## Personal operations workflow

The v0.2 operations path reuses existing read-only DailyDigest artifacts rather than controlling Apple Mail again:

```bash
python3 -m localops_agent ops-run \
  "Read the selected synthetic mail and prepare a candidate email reply" \
  --mail-jsonl tests/fixtures/synthetic_mail.jsonl \
  --recipient reviewer@example.com \
  --engine mock

python3 -m localops_agent drafts --status candidate
python3 -m localops_agent approve-draft 1
python3 -m localops_agent export-eml 1
```

`export-eml` creates a local draft file and reports `sent: false`. There is deliberately no `send-email` command. A real DailyDigest JSONL must be selected explicitly; LocalOps never scans an inbox or changes read/archive/reply state.

The bounded run is:

```text
Operator goal
  -> local planner selects YAGE Context and/or explicit Mail evidence
  -> safe read-only tools return bounded evidence
  -> song-local creates cited findings and an optional candidate email
  -> deterministic evidence/risk validation
  -> human approve/reject
  -> local .eml export only
```

## Apple Watch workflow

1. Record with Voice Memos on Apple Watch.
2. Let Voice Memos sync to the Mac through Apple's normal sync path.
3. Preview the intake plan:

   ```bash
   python3 -m localops_agent watch-sync --date 20260815
   ```

4. Run the local day pipeline when ready:

   ```bash
   python3 -m localops_agent watch-day --date 20260815
   ```

The day pipeline is:

```text
Apple Watch Voice Memo
  -> macOS Voice Memos sync
  -> YAGE intake normalization
  -> local MLX Whisper transcript
  -> song-local evidence extraction
  -> candidate tasks
  -> operator approves/rejects
  -> local reminder export
```

If the standard Voice Memos folder is absent, LocalOps stops and explains how to restore the official sync path. It does not search unrelated folders.

For a one-off local file that the operator explicitly selects:

```bash
python3 -m localops_agent transcribe /absolute/path/to/recording.m4a --process
```

## Model routing

| Content / request | Route | Behavior |
|---|---|---|
| Private + routine | `song-local` | Default, local only |
| Private + deep | `song-deep` | Explicit high-value review; unload after use |
| Public/sanitized + explicit cloud request | Cloud gate | Requires permission; transport not enabled in MVP |
| Any private cloud request | Blocked | Hard failure before network transmission |

## Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

The suite covers routing, evidence validation, schema drift, idempotency, bounded context, read-only mail ingestion, prompt injection, email approval gates, reminder/email export, and dashboard escaping.

Run the complete public release gate:

```bash
./scripts/verify_release.sh
```

The release gate runs the 27-test unit suite, the six-case cross-stage governance evaluation, and a public-tree audit for personal paths, account identifiers, private files, oversized artifacts, and common credential patterns.

## Agent evaluations

The eval bank contains only synthetic public evidence. Run the deterministic regression suite first, then a selected local-model capability set:

```bash
PYTHONPATH=src python3 -m localops_agent eval-run \
  --engine mock --trials 1 --suite all \
  --output evals/reports/local-mock

PYTHONPATH=src python3 -m localops_agent eval-run \
  --engine ollama --trials 2 --suite capability \
  --case cap_mail_summary --case cap_mail_reply \
  --case cap_injection --case cap_yage_context \
  --output evals/reports/song-local
```

Each run writes `summary.json`, `trials.jsonl`, and `report.md`. A passing result means only that the selected synthetic trials passed their graders; it does not prove real-mail, real-Watch, delivery, or production performance.

## Long-term Context candidate workflow

```bash
python3 -m localops_agent context-learn /absolute/path/to/explicit-note.md --engine ollama
python3 -m localops_agent context-candidates --status candidate
python3 -m localops_agent confirm-context 1
python3 -m localops_agent export-context 1
```

The model cannot update YAGE rules. It only proposes source-quoted candidates. `export-context` creates a local Markdown artifact for manual YAGE review and reports `yage_written: false`.

## Governed action workflow

```bash
python3 -m localops_agent propose-action tests/fixtures/synthetic_action.json
python3 -m localops_agent approve-action 1
python3 -m localops_agent simulate-action 1
```

The current action catalog models email, calendar, reminder, and local-report proposals, but all adapters are disabled. Even an approved action can only produce a simulation receipt with `adapter_called: false` and `delivery_status: not_attempted`.

## Research workflow

```bash
python3 -m localops_agent research-run \
  "Compare the synthetic benchmark values" \
  --sources tests/fixtures/synthetic_research.jsonl \
  --privacy public --engine ollama
```

Sources must be an explicitly selected local JSONL packet classified as `public` or `sanitized`, with URL, source reference, and source text. The Agent does not fetch URLs; it synthesizes only the supplied packet and returns a candidate report.

Run the cross-stage negative-path evaluation with:

```bash
PYTHONPATH=src python3 -m localops_agent governance-eval \
  --output evals/reports/local-governance
```

## Project map

- `src/localops_agent/intake.py`: YAGE Intake Skill adapter.
- `src/localops_agent/transcription.py`: existing local MLX Whisper adapter.
- `src/localops_agent/extraction.py`: Ollama extraction, schema normalization, and evidence checks.
- `src/localops_agent/db.py`: SQLite state machine and audit log.
- `src/localops_agent/routing.py`: privacy-aware model routing.
- `src/localops_agent/reminders.py`: approved-only local reminder export.
- `src/localops_agent/mail_ops.py`: explicit read-only mail evidence and approved-only `.eml` export.
- `src/localops_agent/ops_agent.py`: bounded local planning, tools, citation checks, safe draft fallback, and run tracing.
- `src/localops_agent/evals.py`: isolated synthetic trials, outcome/trajectory graders, and reports.
- `src/localops_agent/context_learning.py`: source-grounded Context candidates and confirmation-gated export.
- `src/localops_agent/actions.py`: action policy envelopes, idempotency, approval, and simulation receipts.
- `src/localops_agent/research.py`: bounded public/sanitized research packets, citations, freshness, and conflicts.
- `src/localops_agent/governance_evals.py`: negative-path evaluations across Context, action, and research stages.
- `evals/cases.jsonl`: versioned regression and capability cases.
- `src/localops_agent/dashboard.py`: static local status view.
- `tests/fixtures/`: synthetic public demo data only.

See [`ARCHITECTURE.md`](ARCHITECTURE.md), [`PRIVACY.md`](PRIVACY.md), [`PORTFOLIO.md`](PORTFOLIO.md), [`docs/FAILURE_HANDLING.md`](docs/FAILURE_HANDLING.md), and [`docs/OWNERSHIP.md`](docs/OWNERSHIP.md) for design, failure evidence, and interview framing.
