# Security Policy

## Supported version

Security fixes target the current `main` branch.

## Reporting a vulnerability

Do not open a public issue for a vulnerability, credential, private transcript, or personal-data exposure. Use GitHub's private vulnerability reporting feature after publication. Include the affected path, reproduction steps using synthetic data, impact, and a suggested mitigation when possible.

## Security boundaries

- Runtime state under `.localops/`, real transcripts, mail exports, and local model traces are private and excluded from Git.
- Cloud transport and external action adapters are disabled in this release.
- Approval changes local workflow state; it does not prove an email, calendar, or reminder action was executed.
- Public demos and tests use synthetic fixtures only.
