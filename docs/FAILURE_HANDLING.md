# Failure Handling Evidence

LocalOps treats model and source failures as observable states. It does not convert uncertainty into approval or external execution.

| Failure | Implemented response | Evidence |
|---|---|---|
| Unsupported citation | Drop the finding or task unless the quote appears in the selected source | `extraction.py`, `ops_agent.py`, citation tests |
| Structured-output drift | Normalize only known aliases, preserve warnings, and keep exact-evidence validation | normalization tests and retained evaluation warnings |
| Invalid model output | Make one bounded semantic retry, then use extractive or conservative deterministic fallbacks | `ops_agent.py`, retained 5/8 and 8/8 capability reports |
| Prompt injection in mail/transcript | Treat the text as untrusted evidence, add a warning, and expose no approval/send capability | prompt-injection tests and capability case |
| Private cloud request | Reject before transport; cloud transport is not implemented | `routing.py`, cloud-gate tests |
| Incomplete run | Persist plan, tools, raw result, normalized result, warnings, and `external_actions` in a private trace | trace-completeness graders |
| Unapproved action | Refuse export or simulation until the human state transition exists | task, email, context, and action-gate tests |
| Approved external action | Produce a simulation receipt only; all adapters remain disabled | `actions.py`, governance evaluation |

## Interview failure story

The initial local-model capability run passed 5 of 8 selected synthetic trials. Repeated failures were missing evidence, incomplete grounded findings, and invalid structured output. A first retry-only change still passed 5 of 8 while increasing latency. The system therefore retained those failed runs, added deterministic evidence extraction and conservative candidate-draft fallbacks, and passed 8 of 8 selected system-level trials. This is a governed-system result, not a claim that the model became perfect; four trials still used extractive fallback and two used deterministic planning/draft fallback.

## Limitations

Real Apple Watch intake and real-mail processing remain unverified. There is no email delivery, calendar/reminder mutation, cloud transport, or autonomous web retrieval. Evaluation covers selected synthetic cases and is not production evidence.
