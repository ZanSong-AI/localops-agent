from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List

from .config import Config
from .db import Store
from .extraction import evidence_is_present
from .ops_agent import OllamaOpsModel


CONTEXT_SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "candidate_type": {"type": "string", "enum": ["observation", "preference", "principle"]},
                    "claim": {"type": "string"},
                    "evidence_quote": {"type": "string"},
                },
                "required": ["candidate_type", "claim", "evidence_quote"],
            },
        },
        "questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["candidates", "questions"],
}


def _read_explicit_source(path: Path) -> str:
    source = path.expanduser().resolve()
    if source.suffix.casefold() not in {".md", ".txt"}:
        raise ValueError("context learning accepts only an explicitly selected .md or .txt source")
    if not source.is_file():
        raise FileNotFoundError("context source not found: {}".format(source))
    text = source.read_text(encoding="utf-8-sig")
    if not text.strip():
        raise ValueError("context source is empty")
    return text


def _mock_candidates(text: str) -> List[Dict[str, str]]:
    candidates: List[Dict[str, str]] = []
    for line in text.splitlines():
        quote = line.strip().lstrip("- ")
        if not quote or quote.startswith("#"):
            continue
        lowered = quote.casefold()
        candidate_type = "preference" if any(token in lowered for token in ("prefer", "偏好", "希望", "不喜欢")) else "observation"
        candidates.append({"candidate_type": candidate_type, "claim": quote, "evidence_quote": quote})
        if len(candidates) == 6:
            break
    return candidates


def _model_candidates(config: Config, text: str) -> Dict[str, Any]:
    model = OllamaOpsModel(config.local_endpoint, config.routine_model)
    prompt = """你是本地 Context 候选观察器。只从下面明确提供的本地证据中提出最多 6 条长期 Context 候选。

规则：
- 只能返回 observation、preference 或 principle 候选；它们都不是已确认规则。
- 每条 evidence_quote 必须从来源逐字复制。
- 不推断身份、情绪、隐私属性或长期偏好。
- 一次性任务状态优先标为 observation；没有证据就不生成。
- 顶层仅返回 candidates 和 questions。

<source>
{}
</source>""".format(text)
    return model._chat(prompt, CONTEXT_SCHEMA)


def propose_context_candidates(config: Config, store: Store, source_path: Path, engine: str = "auto") -> Dict[str, Any]:
    text = _read_explicit_source(source_path)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    source_ref = "context-source:{}".format(digest[:16])
    stored = config.state_dir / "documents" / "{}.txt".format(digest)
    stored.write_text(text, encoding="utf-8")
    document = store.add_document(digest, str(source_path.expanduser().resolve()), "explicit_context_source", "private", str(stored))

    warnings: List[str] = []
    questions: List[str] = []
    if engine == "mock":
        raw: Dict[str, Any] = {"candidates": _mock_candidates(text), "questions": []}
        provider = "mock"
    elif engine in {"auto", "ollama"}:
        provider = "ollama"
        try:
            raw = _model_candidates(config, text)
        except ValueError as exc:
            raw = {"candidates": _mock_candidates(text), "questions": [], "model_error": str(exc)}
            warnings.append("used deterministic extractive candidates after invalid structured model output")
    else:
        raise ValueError("context engine must be auto, ollama, or mock")

    accepted: List[Dict[str, Any]] = []
    for item in raw.get("candidates") or []:
        if not isinstance(item, dict):
            warnings.append("dropped non-object context candidate")
            continue
        candidate_type = str(item.get("candidate_type") or item.get("type") or "").strip()
        claim = str(item.get("claim") or item.get("description") or item.get("summary") or "").strip()
        quote = str(item.get("evidence_quote") or "").strip()
        if candidate_type not in {"observation", "preference", "principle"} or not claim or not evidence_is_present(quote, text):
            warnings.append("dropped unsupported context candidate")
            continue
        if not item.get("candidate_type") or not item.get("claim"):
            warnings.append("normalized known context candidate aliases")
        candidate_id = store.add_context_candidate(
            {"source_ref": source_ref, "candidate_type": candidate_type, "claim": claim, "evidence_quote": quote}
        )
        accepted.append({"id": candidate_id, "candidate_type": candidate_type, "claim": claim, "evidence_quote": quote, "status": "candidate"})
    for item in raw.get("questions") or []:
        if str(item).strip():
            questions.append(str(item).strip())
    store.audit(
        "context.learning.run",
        "document",
        document["id"],
        {"provider": provider, "candidate_count": len(accepted), "source_ref": source_ref, "external_actions": "none"},
    )
    run_id = uuid.uuid4().hex
    trace = {
        "run_id": run_id,
        "source_ref": source_ref,
        "provider": provider,
        "raw_model_result": raw,
        "accepted_candidate_ids": [item["id"] for item in accepted],
        "warnings": sorted(set(warnings)),
        "external_actions": "none",
    }
    trace_path = config.state_dir / "context_learning_runs" / "{}.json".format(run_id)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text(json.dumps(trace, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "status": "candidate" if accepted else "needs_human",
        "source_ref": source_ref,
        "document_id": document["id"],
        "candidates": accepted,
        "questions": questions,
        "warnings": sorted(set(warnings)),
        "trace_path": str(trace_path),
        "external_actions": "none",
    }


def export_context_candidate(store: Store, candidate_id: int, output: Path) -> Path:
    candidate = store.get_context_candidate(candidate_id)
    if candidate["status"] != "confirmed":
        raise PermissionError("only a human-confirmed context candidate can be exported")
    target = output.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    body = """# Confirmed Context Candidate

- Type: `{candidate_type}`
- Source ref: `{source_ref}`
- Status at export: `confirmed`

## Claim

{claim}

## Evidence quote

> {evidence_quote}

This local artifact is ready for manual YAGE review. Export does not modify the YAGE knowledge base.
""".format(**candidate)
    target.write_text(body, encoding="utf-8")
    store.transition_context_candidate(candidate_id, "exported")
    store.audit("context.candidate.exported", "context_candidate", candidate_id, {"path": str(target), "yage_written": False})
    return target
