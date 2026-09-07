from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

from .db import Store, now_iso
from .extraction import evidence_is_present


ACTION_POLICY = {
    "email_send": {"risk_level": "high", "adapter_enabled": False, "required_fields": ["recipient", "subject", "body"]},
    "calendar_create": {"risk_level": "high", "adapter_enabled": False, "required_fields": ["title", "start"]},
    "reminder_create": {"risk_level": "medium", "adapter_enabled": False, "required_fields": ["title"]},
    "local_report_export": {"risk_level": "low", "adapter_enabled": False, "required_fields": ["title", "content"]},
}


def load_action_spec(path: Path) -> Dict[str, Any]:
    source = path.expanduser().resolve()
    if source.suffix.casefold() != ".json":
        raise ValueError("action proposal requires an explicitly selected .json specification")
    if not source.is_file():
        raise FileNotFoundError("action specification not found: {}".format(source))
    value = json.loads(source.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("action specification must be a JSON object")
    return value


def _validated_evidence(items: Any) -> List[Dict[str, str]]:
    if not isinstance(items, list) or not items:
        raise ValueError("action proposal requires at least one source-backed evidence item")
    accepted: List[Dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("action evidence items must be objects")
        source_ref = str(item.get("source_ref") or "").strip()
        quote = str(item.get("evidence_quote") or "").strip()
        source_text = str(item.get("source_text") or "")
        if not source_ref or not evidence_is_present(quote, source_text):
            raise ValueError("action evidence quote must match its explicit source text")
        accepted.append({"source_ref": source_ref, "evidence_quote": quote})
    return accepted


def propose_action(store: Store, spec_path: Path) -> Dict[str, Any]:
    spec = load_action_spec(spec_path)
    action_type = str(spec.get("action_type") or "").strip()
    policy_template = ACTION_POLICY.get(action_type)
    if policy_template is None:
        raise ValueError("unsupported action_type; no adapter or policy exists")
    payload = spec.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("action payload must be an object")
    missing = [field for field in policy_template["required_fields"] if not str(payload.get(field) or "").strip()]
    if missing:
        raise ValueError("action payload missing required fields: {}".format(", ".join(missing)))
    evidence = _validated_evidence(spec.get("evidence"))
    normalized = {"action_type": action_type, "payload": payload, "evidence": evidence}
    idempotency_key = str(spec.get("idempotency_key") or "").strip() or hashlib.sha256(
        json.dumps(normalized, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    policy = {
        "decision": "candidate_only",
        "adapter_enabled": bool(policy_template["adapter_enabled"]),
        "human_approval_required": True,
        "simulation_required": True,
        "external_execution_authorized": False,
        "reason": "No external action adapter is enabled in this release.",
    }
    action_id = store.add_action_proposal(
        {
            "action_type": action_type,
            "payload": payload,
            "evidence": evidence,
            "risk_level": policy_template["risk_level"],
            "idempotency_key": idempotency_key,
            "policy": policy,
        }
    )
    return {"status": "candidate", "action_id": action_id, "idempotency_key": idempotency_key, "policy": policy, "external_actions": "none"}


def simulate_action(store: Store, action_id: int) -> Dict[str, Any]:
    action = store.get_action_proposal(action_id)
    if action["status"] != "approved":
        raise PermissionError("action simulation requires a human-approved proposal")
    receipt = {
        "simulated_at": now_iso(),
        "action_type": action["action_type"],
        "idempotency_key": action["idempotency_key"],
        "policy_decision": "simulation_only",
        "adapter_called": False,
        "external_actions": "none",
        "delivery_status": "not_attempted",
    }
    updated = store.transition_action_proposal(action_id, "simulated", receipt=receipt)
    return {"status": updated["status"], "action_id": action_id, "receipt": receipt, "external_actions": "none"}
