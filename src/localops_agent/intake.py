from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import Config
from .transcription import local_asr_paths


def doctor(config: Config) -> Dict[str, Any]:
    intake_src = config.intake_repo / "src"
    asr = local_asr_paths(config)
    return {
        "status": "ok" if config.intake_repo.exists() else "blocked",
        "checks": {
            "intake_skill_present": config.intake_repo.exists(),
            "voice_memos_source_exists": config.voice_memos.exists(),
            "voice_memos_source": str(config.voice_memos),
            "intake_python_source_present": intake_src.exists(),
            "existing_mlx_whisper_adapter": all(asr[key].exists() for key in ("whisper", "ffmpeg", "model")),
            "existing_mlx_whisper_model": str(asr["model"]),
            "ollama_endpoint": config.local_endpoint,
        },
        "notes": [
            "Voice Memos must sync through macOS before LocalOps can read them.",
            "No microphone capture, speaker identification, or unrelated directory scan is performed.",
            "Nightly automatic processing is disabled until the operator explicitly enables it.",
        ],
    }


def run_upstream_sync(config: Config, day: Optional[str] = None, dry_run: bool = True) -> Dict[str, Any]:
    if not config.intake_repo.exists():
        raise FileNotFoundError("project-local intake-skill is missing")
    selected_day = day or date.today().strftime("%Y%m%d")
    command = [
        sys.executable,
        "-m",
        "intake_skill",
        "sync",
        "--source",
        str(config.voice_memos),
        "--data-dir",
        str(config.state_dir / "intake"),
        "--date",
        selected_day,
    ]
    if dry_run:
        command.append("--dry-run")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(config.intake_repo / "src") + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(command, cwd=str(config.intake_repo), env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise RuntimeError("intake sync failed ({}): {}".format(result.returncode, result.stderr.strip()))
    return json.loads(result.stdout)


def transcript_csv_to_text(path: Path, output: Path) -> Dict[str, Any]:
    source = path.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError("transcript not found: {}".format(source))
    with source.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["speaker", "content"]:
            raise ValueError("intake transcript must have exactly speaker,content columns")
        rows: List[str] = []
        for row in reader:
            content = (row.get("content") or "").strip()
            if content:
                rows.append(content)
    if not rows:
        raise ValueError("intake transcript has no non-empty content rows")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n\n".join(rows) + "\n", encoding="utf-8")
    return {"source": str(source), "output": str(output), "row_count": len(rows)}
