#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$project_root"

export PYTHONPATH="$project_root/src"
python3 -m unittest discover -s tests -v
python3 -m localops_agent governance-eval --output "${TMPDIR:-/tmp}/localops-governance-release"
python3 scripts/public_release_audit.py

echo "LocalOps release gate passed."
