from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import Config
from .db import Store


REQUIRED_MAIL_FIELDS = {"external_id", "account", "timestamp", "sender", "subject", "body"}


@dataclass(frozen=True)
class EvidenceItem:
    source_ref: str
    source_kind: str
    text: str
    metadata: Dict[str, str]


def _single_line(value: Any, limit: int = 1000) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def load_mail_evidence(path: Path, max_items: int = 20) -> List[EvidenceItem]:
    source = path.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError("mail evidence not found: {}".format(source))
    if source.suffix.lower() != ".jsonl":
        raise ValueError("mail evidence must be an explicitly selected .jsonl file")
    if max_items < 1 or max_items > 50:
        raise ValueError("max_items must be between 1 and 50")

    items: List[EvidenceItem] = []
    seen = set()
    for line_number, raw_line in enumerate(source.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not raw_line.strip():
            continue
        try:
            record = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ValueError("invalid mail JSONL at line {}".format(line_number)) from exc
        if not isinstance(record, dict) or not REQUIRED_MAIL_FIELDS.issubset(record):
            raise ValueError("mail record {} is missing required fields".format(line_number))
        source_ref = _single_line(record.get("external_id"), 300)
        if not source_ref:
            raise ValueError("mail record {} has no external_id".format(line_number))
        if source_ref in seen:
            continue
        seen.add(source_ref)
        account = _single_line(record.get("account"), 300)
        timestamp = _single_line(record.get("timestamp"), 100)
        sender = _single_line(record.get("sender"), 500)
        subject = _single_line(record.get("subject"), 1000)
        body = str(record.get("body") or "").strip()[:12000]
        text = "\n".join(
            [
                "Account: {}".format(account),
                "Timestamp: {}".format(timestamp),
                "Sender: {}".format(sender),
                "Subject: {}".format(subject),
                "Body:\n{}".format(body),
            ]
        )
        items.append(
            EvidenceItem(
                source_ref=source_ref,
                source_kind="apple_mail",
                text=text,
                metadata={
                    "account": account,
                    "timestamp": timestamp,
                    "sender": sender,
                    "subject": subject,
                    "read_status_at_collection": _single_line(record.get("read_status_at_collection"), 20),
                },
            )
        )
        if len(items) >= max_items:
            break
    if not items:
        raise ValueError("mail evidence contains no usable records")
    return items


def ingest_mail_jsonl(config: Config, store: Store, path: Path, max_items: int = 20) -> Dict[str, Any]:
    source = path.expanduser().resolve()
    raw = source.read_bytes() if source.is_file() else b""
    items = load_mail_evidence(source, max_items=max_items)
    digest = hashlib.sha256(raw + b"\0max_items=" + str(max_items).encode("ascii")).hexdigest()
    stored = config.state_dir / "documents" / "mail_{}.txt".format(digest)
    rendered = "\n\n".join(
        "[SOURCE ref={} kind={}]\n{}".format(item.source_ref, item.source_kind, item.text) for item in items
    ) + "\n"
    if not stored.exists():
        stored.write_text(rendered, encoding="utf-8")
    with store.connect() as connection:
        existed = connection.execute("SELECT 1 FROM documents WHERE sha256=?", (digest,)).fetchone() is not None
    document = store.add_document(
        digest,
        str(source),
        "apple_mail_jsonl",
        "private",
        str(stored),
        None,
    )
    store.audit(
        "mail.evidence.duplicate" if existed else "mail.evidence.ingested",
        "document",
        document["id"],
        {"message_count": len(items), "source_path": str(source)},
    )
    return {"document": document, "duplicate": existed, "items": items, "stored_text_path": str(stored)}


def export_eml(draft: Dict[str, Any], output: Path) -> Path:
    if draft.get("status") != "approved":
        raise PermissionError("only approved email drafts can be exported")
    recipient = str(draft.get("recipient") or "").strip()
    subject = str(draft.get("subject") or "").strip()
    if not recipient:
        raise ValueError("approved email draft needs a recipient before export")
    if "\n" in recipient or "\r" in recipient or "\n" in subject or "\r" in subject:
        raise ValueError("email headers cannot contain line breaks")
    message = EmailMessage()
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(str(draft.get("body") or ""))
    target = output.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(message.as_bytes())
    return target
