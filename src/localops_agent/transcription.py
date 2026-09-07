from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .config import Config


MEDIA_EXTENSIONS = {".m4a", ".mp3", ".wav", ".aiff", ".aac", ".mp4", ".mov", ".mkv"}


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z\u3400-\u4dbf\u4e00-\u9fff]+", "-", value)
    return cleaned.strip("-").lower()[:80] or "recording"


def local_asr_paths(config: Config) -> Dict[str, Path]:
    tools = config.root.parent / "DTS" / "context_tools"
    venv = tools / ".asr-venv"
    return {
        "whisper": venv / "bin" / "mlx_whisper",
        "ffmpeg": venv / "bin" / "ffmpeg",
        "model": tools / ".models" / "whisper-large-v3-turbo",
        "cache": tools / ".cache" / "huggingface",
        "venv": venv,
    }


def transcribe_explicit(
    config: Config,
    media: Path,
    output_dir: Optional[Path] = None,
    language: Optional[str] = None,
) -> Dict[str, Any]:
    source = media.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError("media file not found: {}".format(source))
    if source.suffix.lower() not in MEDIA_EXTENSIONS:
        raise ValueError("unsupported explicit media type: {}".format(source.suffix))
    paths = local_asr_paths(config)
    missing = [str(paths[key]) for key in ("whisper", "ffmpeg", "model") if not paths[key].exists()]
    if missing:
        raise RuntimeError("local MLX Whisper is incomplete: {}".format(", ".join(missing)))
    audio_check = subprocess.run(
        [str(paths["ffmpeg"]), "-v", "error", "-i", str(source), "-map", "0:a:0", "-t", "1", "-f", "null", "-"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if audio_check.returncode:
        raise ValueError("no usable audio track was found in the selected file")
    when = datetime.fromtimestamp(source.stat().st_mtime)
    destination = (output_dir or config.state_dir / "transcripts" / when.strftime("%Y%m%d")).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    name = "{}_{}".format(when.strftime("%Y%m%d_%H%M"), _slug(source.stem))
    command = [
        str(paths["whisper"]),
        str(source),
        "--model",
        str(paths["model"]),
        "--output-dir",
        str(destination),
        "--output-name",
        name,
        "--output-format",
        "all",
        "--word-timestamps",
        "True",
        "--hallucination-silence-threshold",
        "2",
        "--verbose",
        "False",
    ]
    if language:
        command.extend(["--language", language])
    env = os.environ.copy()
    env["PATH"] = str(paths["venv"] / "bin") + os.pathsep + env.get("PATH", "")
    env["HF_HOME"] = str(paths["cache"])
    result = subprocess.run(command, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise RuntimeError("local transcription failed ({}): {}".format(result.returncode, result.stderr[-2000:]))
    vtt = destination / "{}.vtt".format(name)
    transcript_text = vtt.read_text(encoding="utf-8", errors="replace").strip() if vtt.is_file() else ""
    cue_text = "\n".join(
        line.strip()
        for line in transcript_text.splitlines()
        if line.strip() and line.strip() != "WEBVTT" and "-->" not in line
    )
    if not cue_text:
        raise RuntimeError("transcription command produced no spoken content: {}".format(vtt))
    return {
        "status": "transcribed",
        "source": str(source),
        "transcript": str(vtt),
        "model": str(paths["model"]),
        "local_only": True,
    }
