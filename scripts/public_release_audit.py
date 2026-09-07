from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {
    ".git",
    ".localops",
    ".venv",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "data",
    "logs",
    "tmp",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
MAX_BYTES = 10 * 1024 * 1024
REQUIRED = {
    "README.md",
    "LICENSE",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "PRIVACY.md",
    "ARCHITECTURE.md",
    "PORTFOLIO.md",
    "VALIDATION.md",
    "PUBLIC_RELEASE_CHECKLIST.md",
    ".github/workflows/ci.yml",
    ".github/dependabot.yml",
    "docs/FAILURE_HANDLING.md",
    "docs/OWNERSHIP.md",
}
TEXT_SUFFIXES = {"", ".cfg", ".ini", ".json", ".jsonl", ".md", ".py", ".toml", ".txt", ".yml", ".yaml"}
PATTERNS = {
    "personal macOS path": re.compile(r"/" r"Users/[^/\s]+/"),
    "personal UCLA or Georgia Tech account": re.compile(r"[A-Za-z0-9._%+-]+@(?:g\.)?(?:ucla|gatech)\.edu", re.I),
    "private key": re.compile(r"BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY"),
    "GitHub token": re.compile(r"(?:ghp|github_pat)_[A-Za-z0-9_]{20,}"),
    "API secret pattern": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
}


def candidate_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in EXCLUDED_PARTS for part in path.relative_to(ROOT).parts):
            continue
        if path.suffix in EXCLUDED_SUFFIXES:
            continue
        if path.name == "DECISIONS.md" or (path.name == "trials.jsonl" and "evals" in path.parts):
            continue
        files.append(path)
    return sorted(files)


def main() -> int:
    failures: list[str] = []
    files = candidate_files()
    rels = {path.relative_to(ROOT).as_posix() for path in files}
    for missing in sorted(REQUIRED - rels):
        failures.append(f"missing required public file: {missing}")
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        if path.stat().st_size > MAX_BYTES:
            failures.append(f"oversized public file: {rel}")
        if path.name == ".env" or path.suffix in {".key", ".p12", ".pfx", ".pem"}:
            failures.append(f"prohibited public filename: {rel}")
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in PATTERNS.items():
            if pattern.search(text):
                failures.append(f"{label}: {rel}")
    if failures:
        print("Public release audit failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"Public release audit passed: {len(files)} candidate files checked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
