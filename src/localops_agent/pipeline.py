from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .config import Config
from .db import Store
from .extraction import MockExtractor, OllamaExtractor
from .routing import Route, choose_route


TEXT_EXTENSIONS = {".txt", ".md", ".vtt", ".srt"}


def extraction_view(text: str, suffix: str) -> str:
    if suffix.lower() not in {".vtt", ".srt"}:
        return text
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped == "WEBVTT" or stripped.isdigit() or "-->" in stripped:
            continue
        lines.append(stripped)
    return "\n".join(lines)


def source_capture_date(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).date().isoformat()


def ingest_text(
    config: Config,
    store: Store,
    source: Path,
    privacy: str,
    source_kind: str = "explicit_text",
) -> Dict[str, Any]:
    path = source.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError("source not found: {}".format(path))
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        raise ValueError("only explicit .txt, .md, .vtt, or .srt inputs are accepted")
    raw = path.read_bytes()
    if not raw.strip():
        raise ValueError("source is empty")
    digest = hashlib.sha256(raw).hexdigest()
    stored = config.state_dir / "documents" / "{}.txt".format(digest)
    if not stored.exists():
        shutil.copy2(str(path), str(stored))
    existed = False
    try:
        with store.connect() as connection:
            existed = connection.execute("SELECT 1 FROM documents WHERE sha256=?", (digest,)).fetchone() is not None
    except Exception:
        existed = False
    document = store.add_document(
        digest,
        str(path),
        source_kind,
        privacy,
        str(stored),
        source_capture_date(path),
    )
    store.audit("document.duplicate" if existed else "document.ingested", "document", document["id"], {"sha256": digest, "privacy": privacy})
    return {"document": document, "duplicate": existed, "text": raw.decode("utf-8-sig", errors="replace")}


def process_text(
    config: Config,
    store: Store,
    source: Path,
    privacy: str = "private",
    depth: str = "routine",
    engine: str = "auto",
    request_cloud: bool = False,
    allow_cloud: bool = False,
    source_kind: str = "explicit_text",
) -> Dict[str, Any]:
    ingested = ingest_text(config, store, source, privacy, source_kind=source_kind)
    document = ingested["document"]
    if ingested["duplicate"]:
        with store.connect() as connection:
            existing = connection.execute("SELECT COUNT(*) FROM tasks WHERE document_id=?", (document["id"],)).fetchone()[0]
        if existing:
            return {"status": "duplicate", "document_id": document["id"], "candidate_task_ids": [], "route": None}

    route: Optional[Route]
    if engine == "mock":
        route = Route("mock", "deterministic", "explicit offline test engine")
        extractor = MockExtractor()
    elif engine in {"auto", "ollama"}:
        route = choose_route(
            privacy,
            depth,
            config.routine_model,
            config.deep_model,
            request_cloud=request_cloud,
            allow_cloud=allow_cloud,
            cloud_model=config.cloud_model,
        )
        if route.provider != "ollama":
            raise NotImplementedError("cloud transport is intentionally not enabled in the MVP; routing gate passed but no private data was sent")
        extractor = OllamaExtractor(config.local_endpoint, route.model)
    else:
        raise ValueError("engine must be auto, ollama, or mock")

    store.audit("model.route", "document", document["id"], {"provider": route.provider, "model": route.model, "reason": route.reason, "privacy": privacy})
    prepared_text = extraction_view(ingested["text"], source.suffix)
    extraction = extractor.extract(prepared_text, document.get("captured_at"))
    analysis_path = config.state_dir / "analyses" / "document_{}.json".format(document["id"])
    analysis_path.write_text(json.dumps(extraction.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    task_ids = []
    for item in extraction.action_items:
        task_id = store.add_task(int(document["id"]), item)
        task_ids.append(task_id)
        store.audit("task.proposed", "task", task_id, {"document_id": document["id"], "evidence_quote": item["evidence_quote"]})
    if isinstance(extractor, OllamaExtractor) and depth == "deep":
        extractor.unload()
        store.audit("model.unloaded", "model", route.model, {"reason": "deep model memory release"})
    return {
        "status": "processed",
        "document_id": document["id"],
        "candidate_task_ids": task_ids,
        "analysis_path": str(analysis_path),
        "route": {"provider": route.provider, "model": route.model, "reason": route.reason},
        "summary_zh": extraction.summary_zh,
        "warnings": extraction.warnings,
    }
