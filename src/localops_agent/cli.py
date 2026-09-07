from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional

from .actions import propose_action, simulate_action
from .config import Config
from .context_learning import export_context_candidate, propose_context_candidates
from .dashboard import render_dashboard
from .db import Store
from .evals import run_eval_suite
from .governance_evals import run_governance_eval
from .intake import doctor as intake_doctor
from .intake import run_upstream_sync, transcript_csv_to_text
from .mail_ops import export_eml
from .ops_agent import run_operations_agent
from .pipeline import process_text
from .reminders import export_ics
from .research import run_research
from .transcription import transcribe_explicit


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def ollama_status(config: Config) -> Dict[str, Any]:
    try:
        with urllib.request.urlopen(config.local_endpoint.rstrip("/") + "/api/tags", timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
        names = sorted(str(item.get("name")) for item in payload.get("models", []) if item.get("name"))
        return {
            "reachable": True,
            "models": names,
            "routine_model_available": any(name.split(":")[0] == config.routine_model for name in names),
            "deep_model_available": any(name.split(":")[0] == config.deep_model for name in names),
        }
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        return {"reachable": False, "error": str(exc), "models": []}


def command_doctor(config: Config) -> None:
    result = intake_doctor(config)
    result["checks"]["ollama"] = ollama_status(config)
    result["checks"]["state_dir"] = str(config.state_dir)
    result["privacy_boundary"] = {
        "default": "local-only",
        "cloud": "public/sanitized text plus explicit --allow-cloud; transport disabled in MVP",
        "external_actions": "approval required",
    }
    print_json(result)


def command_context(config: Config, question: str, limit: int) -> None:
    retriever = config.root.parent / "YAGE" / "yage-context-kb" / "scripts" / "agent_context.py"
    if not retriever.exists():
        raise FileNotFoundError("YAGE retriever not found: {}".format(retriever))
    result = subprocess.run([sys.executable, str(retriever), question, "--limit", str(limit)], text=True, check=True)
    if result.returncode:
        raise RuntimeError("YAGE retrieval failed")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local-first evidence-bound personal operations agent")
    parser.add_argument("--state-dir", type=Path, help="Override private runtime state directory")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Check local models, Voice Memos intake, and privacy defaults")

    process = sub.add_parser("process", help="Process one explicitly selected text transcript")
    process.add_argument("source", type=Path)
    process.add_argument("--privacy", choices=["private", "sensitive", "public", "sanitized"], default="private")
    process.add_argument("--depth", choices=["routine", "deep"], default="routine")
    process.add_argument("--engine", choices=["auto", "ollama", "mock"], default="auto")
    process.add_argument("--request-cloud", action="store_true")
    process.add_argument("--allow-cloud", action="store_true")

    tasks = sub.add_parser("tasks", help="List proposed and reviewed tasks")
    tasks.add_argument("--status", choices=["candidate", "approved", "rejected", "completed"])
    for name in ("approve", "reject", "complete"):
        transition = sub.add_parser(name, help="Move one task through the audited review flow")
        transition.add_argument("task_id", type=int)
    due = sub.add_parser("due", help="Show approved reminders only")
    due.add_argument("--through", default=None, help="Optional YYYY-MM-DD cutoff")
    reminder = sub.add_parser("export-ics", help="Export one approved task as a local VTODO file")
    reminder.add_argument("task_id", type=int)
    reminder.add_argument("--output", type=Path)
    dashboard = sub.add_parser("dashboard", help="Build a private static local dashboard")
    dashboard.add_argument("--output", type=Path)

    sync = sub.add_parser("watch-sync", help="Preview or sync already-synced Apple Voice Memos")
    sync.add_argument("--date", default=None, help="YYYYMMDD, defaults to today")
    sync.add_argument("--apply", action="store_true", help="Copy/convert planned files; default is dry-run")
    watch_day = sub.add_parser("watch-day", help="Run Apple Watch sync, local transcription, and task proposal for one day")
    watch_day.add_argument("--date", default=None, help="YYYYMMDD, defaults to today")
    watch_day.add_argument("--language", default=None)
    watch_day.add_argument("--engine", choices=["auto", "ollama", "mock"], default="auto")
    intake = sub.add_parser("intake-day", help="Process an Intake Skill transcript CSV for one day")
    intake.add_argument("day", help="YYYYMMDD")
    intake.add_argument("--engine", choices=["auto", "ollama", "mock"], default="auto")
    intake.add_argument("--depth", choices=["routine", "deep"], default="routine")
    transcribe = sub.add_parser("transcribe", help="Transcribe one explicitly selected local media file with MLX Whisper")
    transcribe.add_argument("media", type=Path)
    transcribe.add_argument("--language", default=None)
    transcribe.add_argument("--process", action="store_true", help="Immediately propose tasks from the generated VTT")
    transcribe.add_argument("--engine", choices=["auto", "ollama", "mock"], default="auto")

    context = sub.add_parser("context", help="Retrieve a small evidence bundle from the local YAGE knowledge base")
    context.add_argument("question")
    context.add_argument("--limit", type=int, default=6)

    operations = sub.add_parser("ops-run", help="Run the bounded local operations agent over explicit evidence")
    operations.add_argument("goal")
    operations.add_argument("--mail-jsonl", type=Path, help="Explicit DailyDigest/Apple Mail read-only JSONL evidence")
    operations.add_argument("--recipient", help="Explicit recipient for a candidate email draft")
    operations.add_argument("--engine", choices=["auto", "ollama", "mock"], default="auto")
    operations.add_argument("--context-limit", type=int, default=6)
    operations.add_argument("--max-mail-items", type=int, default=20)

    drafts = sub.add_parser("drafts", help="List candidate and reviewed local email drafts")
    drafts.add_argument("--status", choices=["candidate", "approved", "rejected", "exported"])
    for name in ("approve-draft", "reject-draft"):
        transition = sub.add_parser(name, help="Move one email draft through the audited review flow")
        transition.add_argument("draft_id", type=int)
    email_export = sub.add_parser("export-eml", help="Export one approved email draft locally; never sends it")
    email_export.add_argument("draft_id", type=int)
    email_export.add_argument("--output", type=Path)

    evaluate = sub.add_parser("eval-run", help="Run isolated synthetic Agent trials and graders")
    evaluate.add_argument("--cases", type=Path, default=None, help="Eval JSONL; defaults to evals/cases.jsonl")
    evaluate.add_argument("--output", type=Path, default=None, help="Output directory; defaults to private runtime state")
    evaluate.add_argument("--engine", choices=["mock", "ollama"], default="mock")
    evaluate.add_argument("--trials", type=int, default=1)
    evaluate.add_argument("--suite", choices=["all", "regression", "capability"], default="all")
    evaluate.add_argument("--case", action="append", dest="case_ids", help="Run one case ID; repeat to select multiple")

    context_learn = sub.add_parser("context-learn", help="Propose long-term Context candidates from one explicit local source")
    context_learn.add_argument("source", type=Path)
    context_learn.add_argument("--engine", choices=["auto", "ollama", "mock"], default="auto")
    context_candidates = sub.add_parser("context-candidates", help="List Context candidates and reviewed states")
    context_candidates.add_argument("--status", choices=["candidate", "confirmed", "rejected", "exported"])
    for name in ("confirm-context", "reject-context"):
        transition = sub.add_parser(name, help="Human review transition for one Context candidate")
        transition.add_argument("candidate_id", type=int)
    context_export = sub.add_parser("export-context", help="Export one confirmed candidate for manual YAGE review")
    context_export.add_argument("candidate_id", type=int)
    context_export.add_argument("--output", type=Path)

    action_propose = sub.add_parser("propose-action", help="Create an evidence-bound enterprise action proposal from explicit JSON")
    action_propose.add_argument("spec", type=Path)
    actions = sub.add_parser("actions", help="List governed action proposals")
    actions.add_argument("--status", choices=["candidate", "approved", "rejected", "simulated"])
    for name in ("approve-action", "reject-action"):
        transition = sub.add_parser(name, help="Human review transition for one action proposal")
        transition.add_argument("action_id", type=int)
    simulation = sub.add_parser("simulate-action", help="Simulate one approved action; no adapter is called")
    simulation.add_argument("action_id", type=int)

    research = sub.add_parser("research-run", help="Research an explicit public/sanitized local source packet")
    research.add_argument("question")
    research.add_argument("--sources", type=Path, required=True)
    research.add_argument("--privacy", choices=["public", "sanitized", "private", "sensitive"], default="public")
    research.add_argument("--engine", choices=["auto", "ollama", "mock"], default="auto")
    governance_eval = sub.add_parser("governance-eval", help="Run synthetic phase 2-4 governance scenarios")
    governance_eval.add_argument("--output", type=Path, default=None)
    return parser


def main(argv: Optional[list] = None) -> None:
    args = build_parser().parse_args(argv)
    config = Config.load(state_dir=args.state_dir)
    config.ensure_state()
    store = Store(config.database)
    if args.command == "doctor":
        command_doctor(config)
    elif args.command == "process":
        print_json(process_text(config, store, args.source, args.privacy, args.depth, args.engine, args.request_cloud, args.allow_cloud))
    elif args.command == "tasks":
        print_json(store.list_tasks(args.status))
    elif args.command in {"approve", "reject", "complete"}:
        target = {"approve": "approved", "reject": "rejected", "complete": "completed"}[args.command]
        print_json(store.transition_task(args.task_id, target))
    elif args.command == "due":
        print_json(store.reminder_queue(args.through))
    elif args.command == "export-ics":
        task = store.get_task(args.task_id)
        output = args.output or config.state_dir / "exports" / "task_{}.ics".format(task["id"])
        created = export_ics(task, output.expanduser().resolve())
        store.audit("reminder.exported", "task", task["id"], {"path": str(created), "kind": "ics"})
        print_json({"status": "exported", "task_id": task["id"], "path": str(created)})
    elif args.command == "dashboard":
        output = (args.output or config.state_dir / "dashboard.html").expanduser().resolve()
        created = render_dashboard(
            store.list_tasks(),
            store.recent_events(),
            output,
            store.list_email_drafts(),
            store.list_context_candidates(),
            store.list_action_proposals(),
        )
        print_json({"status": "generated", "path": str(created)})
    elif args.command == "watch-sync":
        result = run_upstream_sync(config, args.date or date.today().strftime("%Y%m%d"), dry_run=not args.apply)
        store.audit("watch.sync.preview" if not args.apply else "watch.sync", "intake", args.date, result.get("counts", {}))
        print_json(result)
    elif args.command == "watch-day":
        if not config.voice_memos.exists():
            raise RuntimeError("Apple Voice Memos has not synced to the standard Mac container; open Voice Memos and enable iCloud sync, then rerun doctor")
        selected_day = args.date or date.today().strftime("%Y%m%d")
        sync_result = run_upstream_sync(config, selected_day, dry_run=False)
        processed = []
        destinations = sorted({item["destination"] for item in sync_result.get("items", [])})
        for destination in destinations:
            transcript = transcribe_explicit(config, Path(destination), language=args.language)
            proposal = process_text(config, store, Path(transcript["transcript"]), "private", "routine", args.engine, source_kind="apple_voice_memos")
            processed.append({"transcription": transcript, "proposal": proposal})
        store.audit("watch.day", "intake", selected_day, {"audio_count": len(destinations), "processed_count": len(processed)})
        print_json({"status": "processed" if processed else "no_content", "day": selected_day, "sync": sync_result, "items": processed})
    elif args.command == "intake-day":
        csv_path = config.state_dir / "intake" / args.day / "transcript_{}.csv".format(args.day)
        text_path = config.state_dir / "intake" / args.day / "localops_source_{}.txt".format(args.day)
        transcript_csv_to_text(csv_path, text_path)
        print_json(process_text(config, store, text_path, "private", args.depth, args.engine, source_kind="apple_voice_memos"))
    elif args.command == "transcribe":
        result = transcribe_explicit(config, args.media, language=args.language)
        store.audit("media.transcribed", "document", None, {"source": result["source"], "transcript": result["transcript"], "model": result["model"]})
        if args.process:
            result["processing"] = process_text(config, store, Path(result["transcript"]), "private", "routine", args.engine, source_kind="explicit_media")
        print_json(result)
    elif args.command == "context":
        command_context(config, args.question, args.limit)
    elif args.command == "ops-run":
        print_json(
            run_operations_agent(
                config,
                store,
                args.goal,
                mail_jsonl=args.mail_jsonl,
                recipient=args.recipient,
                engine=args.engine,
                context_limit=args.context_limit,
                max_mail_items=args.max_mail_items,
            )
        )
    elif args.command == "drafts":
        print_json(store.list_email_drafts(args.status))
    elif args.command in {"approve-draft", "reject-draft"}:
        target = "approved" if args.command == "approve-draft" else "rejected"
        print_json(store.transition_email_draft(args.draft_id, target))
    elif args.command == "export-eml":
        draft = store.get_email_draft(args.draft_id)
        output = args.output or config.state_dir / "exports" / "email_draft_{}.eml".format(draft["id"])
        created = export_eml(draft, output)
        updated = store.transition_email_draft(args.draft_id, "exported")
        store.audit("email.draft.exported", "email_draft", args.draft_id, {"path": str(created), "kind": "eml", "sent": False})
        print_json({"status": updated["status"], "draft_id": args.draft_id, "path": str(created), "sent": False})
    elif args.command == "eval-run":
        stamp = date.today().isoformat()
        cases = (args.cases or config.root / "evals" / "cases.jsonl").expanduser().resolve()
        output = (args.output or config.state_dir / "evals" / "{}-{}".format(stamp, args.engine)).expanduser().resolve()
        print_json(
            run_eval_suite(
                config.root,
                cases,
                output,
                engine=args.engine,
                trials_per_case=args.trials,
                suite=args.suite,
                case_ids=args.case_ids,
            )
        )
    elif args.command == "context-learn":
        print_json(propose_context_candidates(config, store, args.source, engine=args.engine))
    elif args.command == "context-candidates":
        print_json(store.list_context_candidates(args.status))
    elif args.command in {"confirm-context", "reject-context"}:
        target = "confirmed" if args.command == "confirm-context" else "rejected"
        print_json(store.transition_context_candidate(args.candidate_id, target))
    elif args.command == "export-context":
        output = args.output or config.state_dir / "exports" / "context_candidate_{}.md".format(args.candidate_id)
        created = export_context_candidate(store, args.candidate_id, output)
        print_json({"status": "exported", "candidate_id": args.candidate_id, "path": str(created), "yage_written": False})
    elif args.command == "propose-action":
        print_json(propose_action(store, args.spec))
    elif args.command == "actions":
        print_json(store.list_action_proposals(args.status))
    elif args.command in {"approve-action", "reject-action"}:
        target = "approved" if args.command == "approve-action" else "rejected"
        print_json(store.transition_action_proposal(args.action_id, target))
    elif args.command == "simulate-action":
        print_json(simulate_action(store, args.action_id))
    elif args.command == "research-run":
        print_json(run_research(config, store, args.question, args.sources, privacy=args.privacy, engine=args.engine))
    elif args.command == "governance-eval":
        output = (args.output or config.state_dir / "evals" / "{}-governance".format(date.today().isoformat())).expanduser().resolve()
        print_json(run_governance_eval(config.root, output))


if __name__ == "__main__":
    main()
