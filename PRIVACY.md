# Privacy and Action Policy

## Data classes

- `private`: personal meetings, audio, transcripts, reminders, personal Context. Local models only.
- `sensitive`: credentials, health, employment, financial, or legally sensitive content. Local models only; some future actions may be permanently unsupported.
- `sanitized`: manually stripped of identifying/private details. Cloud remains opt-in.
- `public`: intentionally public or synthetic material. Cloud remains opt-in.

## Default behavior

- Audio and transcripts remain on the Mac.
- Runtime state is stored under `.localops/` and excluded from source control.
- The system reads only the standard Voice Memos container or a file explicitly passed by the operator.
- Mail evidence must be an explicitly selected local `.jsonl` produced by the existing read-only DailyDigest pipeline. LocalOps does not open Mail, change read state, archive, delete, reply, or scan accounts.
- YAGE retrieval is local, query-scoped, and capped at six evidence items per Agent run.
- No model can approve its own proposal.
- Long-term Context observations remain `candidate` until the operator confirms them. Local export does not write YAGE files or promote an external author's view into a user rule.
- Research accepts only source packets the operator classifies as `public` or `sanitized`; private/sensitive packets are rejected before model use.
- Unknown owner or date stays unknown. Relative dates stay as source text unless a later human review resolves them.

## Prompt injection

Transcript content is treated as quoted, untrusted data. Instructions spoken in a recording cannot change LocalOps policy, choose a cloud route, approve tasks, or trigger an executor.

## External actions

This MVP exports an approved task to a local `.ics` file and an approved email draft to a local `.eml` file. Neither export is imported or sent. There is no email-send tool. Calendar writes, messages, purchases, submissions, deletions, mailbox changes, and account changes require separate future adapters and explicit confirmation at the action boundary.

The enterprise action gateway stores proposals for testing policy and approval behavior, but all adapters are disabled. `simulate-action` records `adapter_called: false`, `external_actions: none`, and `delivery_status: not_attempted`. Approval therefore does not imply delivery or mutation.

Per-run traces may contain private derived text and therefore stay under `.localops/`, which is excluded from source control. Public examples use only synthetic mail, synthetic meeting text, and non-private screenshots.
