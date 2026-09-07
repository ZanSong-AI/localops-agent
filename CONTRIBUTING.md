# Contributing

LocalOps is an evidence-bound portfolio system. Contributions should preserve its trust boundaries rather than add unconstrained autonomy.

## Development workflow

1. Create a focused branch.
2. Add or update synthetic tests for every behavior change.
3. Run `./scripts/verify_release.sh`.
4. Explain the evidence, authorization, privacy, and failure-mode impact in the pull request.

Do not include real mail, transcripts, account identifiers, local paths, credentials, model files, or generated private state. Changes that add external execution, cloud transport, mailbox mutation, or automatic approval require a separate design and threat-model review.
