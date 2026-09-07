from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256 TEXT NOT NULL UNIQUE,
    source_path TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    privacy TEXT NOT NULL,
    captured_at TEXT,
    stored_text_path TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents(id),
    task TEXT NOT NULL,
    owner TEXT,
    due_date TEXT,
    due_text TEXT,
    evidence_quote TEXT NOT NULL,
    action_type TEXT NOT NULL DEFAULT 'task',
    confidence TEXT NOT NULL DEFAULT 'medium',
    status TEXT NOT NULL DEFAULT 'candidate',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    event_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    details_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS email_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    recipient TEXT,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'candidate',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS context_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_ref TEXT NOT NULL,
    candidate_type TEXT NOT NULL,
    claim TEXT NOT NULL,
    evidence_quote TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'candidate',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source_ref, candidate_type, claim, evidence_quote)
);
CREATE TABLE IF NOT EXISTS action_proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    policy_json TEXT NOT NULL,
    receipt_json TEXT,
    status TEXT NOT NULL DEFAULT 'candidate',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_status_due ON tasks(status, due_date);
CREATE INDEX IF NOT EXISTS idx_email_drafts_status ON email_drafts(status, id);
CREATE INDEX IF NOT EXISTS idx_context_candidates_status ON context_candidates(status, id);
CREATE INDEX IF NOT EXISTS idx_action_proposals_status ON action_proposals(status, id);
"""

ALLOWED_TRANSITIONS = {
    "candidate": {"approved", "rejected"},
    "approved": {"completed", "rejected"},
    "rejected": set(),
    "completed": set(),
}

DRAFT_ALLOWED_TRANSITIONS = {
    "candidate": {"approved", "rejected"},
    "approved": {"exported", "rejected"},
    "rejected": set(),
    "exported": set(),
}

CONTEXT_ALLOWED_TRANSITIONS = {
    "candidate": {"confirmed", "rejected"},
    "confirmed": {"exported", "rejected"},
    "rejected": set(),
    "exported": set(),
}

ACTION_ALLOWED_TRANSITIONS = {
    "candidate": {"approved", "rejected"},
    "approved": {"simulated", "rejected"},
    "rejected": set(),
    "simulated": set(),
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(str(self.path))
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def audit(
        self,
        event_type: str,
        entity_type: str,
        entity_id: Optional[object] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO events(occurred_at,event_type,entity_type,entity_id,details_json) VALUES(?,?,?,?,?)",
                (now_iso(), event_type, entity_type, None if entity_id is None else str(entity_id), json.dumps(details or {}, ensure_ascii=False, sort_keys=True)),
            )

    def add_document(
        self,
        sha256: str,
        source_path: str,
        source_kind: str,
        privacy: str,
        stored_text_path: str,
        captured_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO documents(sha256,source_path,source_kind,privacy,captured_at,stored_text_path,created_at) VALUES(?,?,?,?,?,?,?)",
                (sha256, source_path, source_kind, privacy, captured_at, stored_text_path, now_iso()),
            )
            row = connection.execute("SELECT * FROM documents WHERE sha256=?", (sha256,)).fetchone()
        assert row is not None
        return dict(row)

    def add_task(self, document_id: int, item: Dict[str, Any]) -> int:
        timestamp = now_iso()
        with self.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO tasks(document_id,task,owner,due_date,due_text,evidence_quote,action_type,confidence,status,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    document_id,
                    item["task"],
                    item.get("owner"),
                    item.get("due_date"),
                    item.get("due_text"),
                    item["evidence_quote"],
                    item.get("action_type", "task"),
                    item.get("confidence", "medium"),
                    "candidate",
                    timestamp,
                    timestamp,
                ),
            )
            return int(cursor.lastrowid)

    def get_task(self, task_id: int) -> Dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT tasks.*, documents.source_path FROM tasks
                   JOIN documents ON documents.id=tasks.document_id WHERE tasks.id=?""",
                (task_id,),
            ).fetchone()
        if row is None:
            raise KeyError("task {} not found".format(task_id))
        return dict(row)

    def transition_task(self, task_id: int, target: str) -> Dict[str, Any]:
        current = self.get_task(task_id)
        allowed = ALLOWED_TRANSITIONS.get(current["status"], set())
        if target not in allowed:
            raise ValueError("invalid task transition: {} -> {}".format(current["status"], target))
        with self.connect() as connection:
            connection.execute(
                "UPDATE tasks SET status=?,updated_at=? WHERE id=?",
                (target, now_iso(), task_id),
            )
        updated = self.get_task(task_id)
        self.audit("task.transition", "task", task_id, {"from": current["status"], "to": target})
        return updated

    def list_tasks(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT tasks.*, documents.source_path FROM tasks JOIN documents ON documents.id=tasks.document_id"
        params = ()
        if status:
            query += " WHERE tasks.status=?"
            params = (status,)
        query += " ORDER BY CASE WHEN due_date IS NULL THEN 1 ELSE 0 END,due_date,tasks.id"
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def reminder_queue(self, through_date: Optional[str] = None) -> List[Dict[str, Any]]:
        query = """SELECT tasks.*, documents.source_path FROM tasks
                   JOIN documents ON documents.id=tasks.document_id
                   WHERE tasks.status='approved'"""
        params = ()
        if through_date:
            query += " AND due_date IS NOT NULL AND due_date<=?"
            params = (through_date,)
        query += " ORDER BY CASE WHEN due_date IS NULL THEN 1 ELSE 0 END,due_date,tasks.id"
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def add_email_draft(
        self,
        run_id: str,
        recipient: Optional[str],
        subject: str,
        body: str,
        evidence: List[Dict[str, str]],
    ) -> int:
        timestamp = now_iso()
        with self.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO email_drafts(run_id,recipient,subject,body,evidence_json,status,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (
                    run_id,
                    recipient,
                    subject,
                    body,
                    json.dumps(evidence, ensure_ascii=False, sort_keys=True),
                    "candidate",
                    timestamp,
                    timestamp,
                ),
            )
            draft_id = int(cursor.lastrowid)
        self.audit("email.draft.proposed", "email_draft", draft_id, {"run_id": run_id, "evidence_count": len(evidence)})
        return draft_id

    def get_email_draft(self, draft_id: int) -> Dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM email_drafts WHERE id=?", (draft_id,)).fetchone()
        if row is None:
            raise KeyError("email draft {} not found".format(draft_id))
        value = dict(row)
        value["evidence"] = json.loads(value.pop("evidence_json"))
        return value

    def list_email_drafts(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM email_drafts"
        params = ()
        if status:
            query += " WHERE status=?"
            params = (status,)
        query += " ORDER BY id DESC"
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        values = []
        for row in rows:
            value = dict(row)
            value["evidence"] = json.loads(value.pop("evidence_json"))
            values.append(value)
        return values

    def transition_email_draft(self, draft_id: int, target: str) -> Dict[str, Any]:
        current = self.get_email_draft(draft_id)
        allowed = DRAFT_ALLOWED_TRANSITIONS.get(current["status"], set())
        if target not in allowed:
            raise ValueError("invalid email draft transition: {} -> {}".format(current["status"], target))
        with self.connect() as connection:
            connection.execute(
                "UPDATE email_drafts SET status=?,updated_at=? WHERE id=?",
                (target, now_iso(), draft_id),
            )
        updated = self.get_email_draft(draft_id)
        self.audit("email.draft.transition", "email_draft", draft_id, {"from": current["status"], "to": target})
        return updated

    def add_context_candidate(self, item: Dict[str, str]) -> int:
        timestamp = now_iso()
        with self.connect() as connection:
            connection.execute(
                """INSERT OR IGNORE INTO context_candidates(source_ref,candidate_type,claim,evidence_quote,status,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (
                    item["source_ref"],
                    item["candidate_type"],
                    item["claim"],
                    item["evidence_quote"],
                    "candidate",
                    timestamp,
                    timestamp,
                ),
            )
            row = connection.execute(
                """SELECT * FROM context_candidates
                   WHERE source_ref=? AND candidate_type=? AND claim=? AND evidence_quote=?""",
                (item["source_ref"], item["candidate_type"], item["claim"], item["evidence_quote"]),
            ).fetchone()
        assert row is not None
        candidate_id = int(row["id"])
        self.audit("context.candidate.proposed", "context_candidate", candidate_id, {"source_ref": item["source_ref"]})
        return candidate_id

    def get_context_candidate(self, candidate_id: int) -> Dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM context_candidates WHERE id=?", (candidate_id,)).fetchone()
        if row is None:
            raise KeyError("context candidate {} not found".format(candidate_id))
        return dict(row)

    def list_context_candidates(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM context_candidates"
        params = ()
        if status:
            query += " WHERE status=?"
            params = (status,)
        query += " ORDER BY id DESC"
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def transition_context_candidate(self, candidate_id: int, target: str) -> Dict[str, Any]:
        current = self.get_context_candidate(candidate_id)
        allowed = CONTEXT_ALLOWED_TRANSITIONS.get(current["status"], set())
        if target not in allowed:
            raise ValueError("invalid context transition: {} -> {}".format(current["status"], target))
        with self.connect() as connection:
            connection.execute(
                "UPDATE context_candidates SET status=?,updated_at=? WHERE id=?",
                (target, now_iso(), candidate_id),
            )
        updated = self.get_context_candidate(candidate_id)
        self.audit("context.candidate.transition", "context_candidate", candidate_id, {"from": current["status"], "to": target})
        return updated

    def add_action_proposal(self, item: Dict[str, Any]) -> int:
        timestamp = now_iso()
        with self.connect() as connection:
            connection.execute(
                """INSERT OR IGNORE INTO action_proposals(action_type,payload_json,evidence_json,risk_level,idempotency_key,policy_json,status,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    item["action_type"],
                    json.dumps(item["payload"], ensure_ascii=False, sort_keys=True),
                    json.dumps(item["evidence"], ensure_ascii=False, sort_keys=True),
                    item["risk_level"],
                    item["idempotency_key"],
                    json.dumps(item["policy"], ensure_ascii=False, sort_keys=True),
                    "candidate",
                    timestamp,
                    timestamp,
                ),
            )
            row = connection.execute("SELECT * FROM action_proposals WHERE idempotency_key=?", (item["idempotency_key"],)).fetchone()
        assert row is not None
        action_id = int(row["id"])
        self.audit("action.proposed", "action_proposal", action_id, {"action_type": item["action_type"], "risk_level": item["risk_level"]})
        return action_id

    def _decode_action(self, row: sqlite3.Row) -> Dict[str, Any]:
        value = dict(row)
        value["payload"] = json.loads(value.pop("payload_json"))
        value["evidence"] = json.loads(value.pop("evidence_json"))
        value["policy"] = json.loads(value.pop("policy_json"))
        raw_receipt = value.pop("receipt_json")
        value["receipt"] = json.loads(raw_receipt) if raw_receipt else None
        return value

    def get_action_proposal(self, action_id: int) -> Dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM action_proposals WHERE id=?", (action_id,)).fetchone()
        if row is None:
            raise KeyError("action proposal {} not found".format(action_id))
        return self._decode_action(row)

    def list_action_proposals(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM action_proposals"
        params = ()
        if status:
            query += " WHERE status=?"
            params = (status,)
        query += " ORDER BY id DESC"
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._decode_action(row) for row in rows]

    def transition_action_proposal(self, action_id: int, target: str, receipt: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        current = self.get_action_proposal(action_id)
        allowed = ACTION_ALLOWED_TRANSITIONS.get(current["status"], set())
        if target not in allowed:
            raise ValueError("invalid action transition: {} -> {}".format(current["status"], target))
        with self.connect() as connection:
            connection.execute(
                "UPDATE action_proposals SET status=?,receipt_json=?,updated_at=? WHERE id=?",
                (target, json.dumps(receipt, ensure_ascii=False, sort_keys=True) if receipt is not None else None, now_iso(), action_id),
            )
        updated = self.get_action_proposal(action_id)
        self.audit("action.transition", "action_proposal", action_id, {"from": current["status"], "to": target, "receipt": receipt})
        return updated

    def recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]
