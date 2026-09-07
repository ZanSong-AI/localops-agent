# Public Release Checklist

## Automated gates

- [x] `./scripts/verify_release.sh` passes.
- [x] No personal path, real account identifier, credential, private trace, or `.env` file is included.
- [x] The upstream intake skill is recorded as a pinned Git submodule and remains MIT licensed.
- [x] GitHub Actions use least-privilege permissions and full commit SHAs.

## Claim boundaries

- [x] README and portfolio wording state that real Watch intake is unverified.
- [x] Local `.eml`/`.ics` export is not described as delivery or Apple app mutation.
- [x] External adapters and cloud transport remain disabled.
- [x] Evaluation results are labeled synthetic and system-level.

## Human publication gate

- [x] Repository visibility and name approved by the owner on 2026-09-06.
- [x] Git author identity reviewed before the first commit.
- [ ] First hosted GitHub Actions run passes.
- [ ] Repository links work from a logged-out browser.
