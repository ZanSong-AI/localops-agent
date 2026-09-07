from __future__ import annotations

import html
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _task_rows(tasks: Iterable[Dict[str, Any]]) -> str:
    rows = []
    for task in tasks:
        rows.append(
            "<tr><td>{}</td><td><span class='badge {}'>{}</span></td><td>{}</td><td>{}</td><td>{}</td><td><code>{}</code></td></tr>".format(
                task["id"],
                html.escape(task["status"]),
                html.escape(task["status"]),
                html.escape(task["task"]),
                html.escape(task.get("owner") or "—"),
                html.escape(task.get("due_date") or task.get("due_text") or "—"),
                html.escape(task.get("evidence_quote") or ""),
            )
        )
    return "\n".join(rows) or "<tr><td colspan='6'>No tasks yet.</td></tr>"


def _draft_rows(drafts: Iterable[Dict[str, Any]]) -> str:
    rows = []
    for draft in drafts:
        refs = ", ".join(str(item.get("source_ref") or "") for item in draft.get("evidence") or [])
        rows.append(
            "<tr><td>{}</td><td><span class='badge {}'>{}</span></td><td>{}</td><td>{}</td><td><code>{}</code></td></tr>".format(
                draft["id"],
                html.escape(draft["status"]),
                html.escape(draft["status"]),
                html.escape(draft.get("recipient") or "—"),
                html.escape(draft.get("subject") or ""),
                html.escape(refs),
            )
        )
    return "\n".join(rows) or "<tr><td colspan='5'>No email drafts yet.</td></tr>"


def _context_rows(candidates: Iterable[Dict[str, Any]]) -> str:
    rows = []
    for item in candidates:
        rows.append(
            "<tr><td>{}</td><td><span class='badge {}'>{}</span></td><td>{}</td><td>{}</td><td><code>{}</code></td></tr>".format(
                item["id"],
                html.escape(item["status"]),
                html.escape(item["status"]),
                html.escape(item.get("candidate_type") or ""),
                html.escape(item.get("claim") or ""),
                html.escape(item.get("evidence_quote") or ""),
            )
        )
    return "\n".join(rows) or "<tr><td colspan='5'>No Context candidates yet.</td></tr>"


def _action_rows(actions: Iterable[Dict[str, Any]]) -> str:
    rows = []
    for item in actions:
        policy = item.get("policy") or {}
        receipt = item.get("receipt") or {}
        execution = receipt.get("delivery_status") or ("adapter disabled" if not policy.get("adapter_enabled") else "not run")
        rows.append(
            "<tr><td>{}</td><td><span class='badge {}'>{}</span></td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                item["id"],
                html.escape(item["status"]),
                html.escape(item["status"]),
                html.escape(item.get("action_type") or ""),
                html.escape(item.get("risk_level") or ""),
                html.escape(str(execution)),
            )
        )
    return "\n".join(rows) or "<tr><td colspan='5'>No action proposals yet.</td></tr>"


def render_dashboard(
    tasks: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    output: Path,
    email_drafts: Optional[List[Dict[str, Any]]] = None,
    context_candidates: Optional[List[Dict[str, Any]]] = None,
    action_proposals: Optional[List[Dict[str, Any]]] = None,
) -> Path:
    drafts = email_drafts or []
    contexts = context_candidates or []
    actions = action_proposals or []
    counts = {status: sum(1 for item in tasks if item["status"] == status) for status in ("candidate", "approved", "completed", "rejected")}
    event_rows = "\n".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td><code>{}</code></td></tr>".format(
            html.escape(event["occurred_at"]), html.escape(event["event_type"]), html.escape(event["entity_type"]), html.escape(event["details_json"])
        )
        for event in events
    ) or "<tr><td colspan='4'>No audit events yet.</td></tr>"
    page = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LocalOps Agent</title><style>
:root {{ color-scheme: light; --ink:#17202a; --muted:#667085; --panel:#fff; --bg:#f4f1eb; --green:#176b52; --amber:#a85d00; --line:#ded8cc; }}
body {{ margin:0; font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:var(--ink); background:var(--bg); }}
main {{ max-width:1100px; margin:0 auto; padding:48px 24px; }}
h1 {{ font-size:38px; margin:0 0 6px; }} .subtitle {{ color:var(--muted); margin-bottom:28px; }}
.cards {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }} .card,section {{ background:var(--panel); border:1px solid var(--line); border-radius:16px; padding:18px; }}
.num {{ font-size:30px; font-weight:700; }} section {{ margin-top:18px; overflow:auto; }}
table {{ width:100%; border-collapse:collapse; }} th,td {{ text-align:left; padding:10px; border-bottom:1px solid var(--line); vertical-align:top; }}
th {{ color:var(--muted); font-size:12px; text-transform:uppercase; }} code {{ white-space:normal; }}
.badge {{ border-radius:999px; padding:3px 8px; background:#eee; }} .approved {{ background:#d8f3e8; color:var(--green); }} .candidate {{ background:#fff0d0; color:var(--amber); }}
.flow {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; background:#16211e; color:#dff8ec; padding:14px; border-radius:12px; }}
@media(max-width:700px) {{ .cards {{ grid-template-columns:repeat(2,1fr); }} }}
</style></head><body><main>
<h1>LocalOps Agent</h1><div class="subtitle">Local-first personal operations with evidence and human approval boundaries.</div>
<div class="cards"><div class="card"><div class="num">{candidate}</div>Candidate</div><div class="card"><div class="num">{approved}</div>Approved</div><div class="card"><div class="num">{completed}</div>Completed</div><div class="card"><div class="num">{rejected}</div>Rejected</div></div>
<section><h2>Safety flow</h2><div class="flow">Explicit evidence → local model + deterministic policy → candidate → human review → local export or simulation only</div></section>
<section><h2>Tasks</h2><table><thead><tr><th>ID</th><th>Status</th><th>Task</th><th>Owner</th><th>Due</th><th>Source quote</th></tr></thead><tbody>{task_rows}</tbody></table></section>
<section><h2>Email drafts</h2><table><thead><tr><th>ID</th><th>Status</th><th>Recipient</th><th>Subject</th><th>Evidence refs</th></tr></thead><tbody>{draft_rows}</tbody></table></section>
<section><h2>Context candidates</h2><table><thead><tr><th>ID</th><th>Status</th><th>Type</th><th>Claim</th><th>Source quote</th></tr></thead><tbody>{context_rows}</tbody></table></section>
<section><h2>Governed actions</h2><table><thead><tr><th>ID</th><th>Status</th><th>Action</th><th>Risk</th><th>Execution</th></tr></thead><tbody>{action_rows}</tbody></table></section>
<section><h2>Recent audit events</h2><table><thead><tr><th>Time</th><th>Event</th><th>Entity</th><th>Details</th></tr></thead><tbody>{event_rows}</tbody></table></section>
</main></body></html>""".format(
        task_rows=_task_rows(tasks),
        draft_rows=_draft_rows(drafts),
        context_rows=_context_rows(contexts),
        action_rows=_action_rows(actions),
        event_rows=event_rows,
        **counts
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8")
    return output
