#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
demo_state="$(mktemp -d "${TMPDIR:-/tmp}/localops-demo.XXXXXX")"
trap 'rm -rf "$demo_state"' EXIT

export PYTHONPATH="$project_root/src"
export LOCALOPS_STATE_DIR="$demo_state/state"
cp "$project_root/tests/fixtures/synthetic_meeting.txt" "$demo_state/synthetic_meeting.txt"

python3 -m localops_agent process "$demo_state/synthetic_meeting.txt" --engine mock --privacy public
python3 -m localops_agent tasks --status candidate
python3 -m localops_agent governance-eval --output "$demo_state/governance"

echo "Safe demo complete: synthetic data only; external actions none."
