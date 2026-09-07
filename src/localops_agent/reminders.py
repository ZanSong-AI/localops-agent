from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict


def ics_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def export_ics(task: Dict[str, Any], output: Path) -> Path:
    if task["status"] != "approved":
        raise PermissionError("only approved tasks can be exported as reminders")
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    due_line = ""
    if task.get("due_date"):
        due_line = "DTSTART;VALUE=DATE:{}\n".format(str(task["due_date"]).replace("-", ""))
    description = "Evidence: {}\nSource: {}".format(task.get("evidence_quote") or "", task.get("source_path") or "")
    body = (
        "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//LocalOps Agent//EN\nBEGIN:VTODO\n"
        "UID:localops-task-{}@localhost\nDTSTAMP:{}\n{}SUMMARY:{}\nDESCRIPTION:{}\nSTATUS:NEEDS-ACTION\nEND:VTODO\nEND:VCALENDAR\n"
    ).format(task["id"], timestamp, due_line, ics_escape(task["task"]), ics_escape(description))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(body, encoding="utf-8")
    return output
