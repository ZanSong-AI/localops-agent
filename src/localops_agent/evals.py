from __future__ import annotations

import json
import statistics
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .config import Config
from .db import Store
from .extraction import evidence_is_present
from .mail_ops import EvidenceItem, load_mail_evidence
from .ops_agent import run_operations_agent


def load_eval_cases(path: Path) -> List[Dict[str, Any]]:
    source = path.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError("eval cases not found: {}".format(source))
    cases: List[Dict[str, Any]] = []
    seen = set()
    for line_number, raw_line in enumerate(source.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not raw_line.strip():
            continue
        try:
            case = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ValueError("invalid eval JSONL at line {}".format(line_number)) from exc
        if not isinstance(case, dict) or not case.get("id") or not case.get("goal") or not isinstance(case.get("expect"), dict):
            raise ValueError("eval case {} must contain id, goal, and expect".format(line_number))
        case_id = str(case["id"])
        if case_id in seen:
            raise ValueError("duplicate eval case id: {}".format(case_id))
        if case.get("suite") not in {"regression", "capability"}:
            raise ValueError("eval case {} has unsupported suite".format(case_id))
        seen.add(case_id)
        cases.append(case)
    if not cases:
        raise ValueError("eval case file is empty")
    return cases


def _write_mail_fixture(case: Dict[str, Any], directory: Path) -> Optional[Path]:
    records = case.get("mail_records")
    raw = case.get("mail_jsonl_raw")
    if records is None and raw is None:
        return None
    path = directory / "mail.jsonl"
    if raw is not None:
        path.write_text(str(raw), encoding="utf-8")
    else:
        if not isinstance(records, list):
            raise ValueError("mail_records must be a list")
        path.write_text("".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in records), encoding="utf-8")
    return path


def _source_map(mail_path: Optional[Path], context_text: Optional[str]) -> Dict[str, EvidenceItem]:
    sources: Dict[str, EvidenceItem] = {}
    if mail_path is not None:
        try:
            for item in load_mail_evidence(mail_path, max_items=50):
                sources[item.source_ref] = item
        except (ValueError, FileNotFoundError):
            pass
    if context_text:
        sources["yage-context"] = EvidenceItem("yage-context", "yage_context", context_text, {})
    return sources


def _citation_check(result: Dict[str, Any], store: Store, sources: Dict[str, EvidenceItem]) -> Tuple[bool, List[str]]:
    failures: List[str] = []
    citations: List[Dict[str, Any]] = list(result.get("findings") or [])
    draft_id = result.get("email_draft_id")
    if draft_id is not None:
        citations.extend(store.get_email_draft(int(draft_id)).get("evidence") or [])
    for item in citations:
        source_ref = str(item.get("source_ref") or "")
        quote = str(item.get("evidence_quote") or "")
        source = sources.get(source_ref)
        if source is None or not evidence_is_present(quote, source.text):
            failures.append("{}:{}".format(source_ref or "missing-ref", quote[:80]))
    return not failures, failures


def _record_check(checks: Dict[str, bool], details: Dict[str, Any], name: str, passed: bool, detail: Any = None) -> None:
    checks[name] = bool(passed)
    if detail is not None:
        details[name] = detail


def run_eval_trial(project_root: Path, case: Dict[str, Any], engine: str, trial_number: int) -> Dict[str, Any]:
    started = time.perf_counter()
    expect = case["expect"]
    with tempfile.TemporaryDirectory(prefix="localops-eval-") as temp_name:
        trial_root = Path(temp_name)
        config = Config.load(root=project_root, state_dir=trial_root / "state")
        config.ensure_state()
        store = Store(config.database)
        mail_path = _write_mail_fixture(case, trial_root)
        context_text = str(case.get("context_text") or "") or None

        def context_loader(_config: Config, _query: str, limit: int) -> str:
            if not context_text:
                raise RuntimeError("synthetic eval case provided no YAGE context")
            if limit > 6:
                raise ValueError("eval observed an unbounded YAGE request")
            return context_text

        result: Optional[Dict[str, Any]] = None
        caught: Optional[Exception] = None
        try:
            result = run_operations_agent(
                config,
                store,
                str(case["goal"]),
                mail_jsonl=mail_path,
                recipient=case.get("recipient"),
                engine=engine,
                context_limit=int(case.get("context_limit") or 6),
                max_mail_items=int(case.get("max_mail_items") or 20),
                context_loader=context_loader,
            )
        except Exception as exc:  # eval harness grades expected failures without hiding them
            caught = exc

        checks: Dict[str, bool] = {}
        details: Dict[str, Any] = {}
        expected_error = expect.get("error_contains")
        if expected_error:
            error_text = "{}: {}".format(type(caught).__name__, caught) if caught else ""
            _record_check(checks, details, "expected_error", caught is not None and str(expected_error) in error_text, error_text)
        else:
            _record_check(
                checks,
                details,
                "no_unexpected_error",
                caught is None,
                None if caught is None else "{}: {}".format(type(caught).__name__, caught),
            )

        trace_snapshot: Optional[Dict[str, Any]] = None
        if result is not None:
            plan = result.get("plan") or {}
            for field in ("use_yage_context", "use_mail_evidence", "prepare_email_draft"):
                if field in expect:
                    _record_check(checks, details, "plan.{}".format(field), plan.get(field) is expect[field], {"actual": plan.get(field), "expected": expect[field]})
            allowed_statuses = expect.get("allowed_statuses") or ([expect["status"]] if expect.get("status") else [])
            if allowed_statuses:
                _record_check(checks, details, "outcome.status", result.get("status") in allowed_statuses, {"actual": result.get("status"), "allowed": allowed_statuses})
            _record_check(checks, details, "outcome.external_actions", result.get("external_actions") == "none", result.get("external_actions"))
            minimum_findings = int(expect.get("min_findings") or 0)
            _record_check(checks, details, "outcome.min_findings", len(result.get("findings") or []) >= minimum_findings, len(result.get("findings") or []))
            if "draft_created" in expect:
                _record_check(checks, details, "outcome.draft_created", (result.get("email_draft_id") is not None) is bool(expect["draft_created"]), result.get("email_draft_id"))
            if result.get("email_draft_id") is not None:
                draft = store.get_email_draft(int(result["email_draft_id"]))
                _record_check(checks, details, "outcome.draft_stays_candidate", draft.get("status") == "candidate", draft.get("status"))

            sources = _source_map(mail_path, context_text)
            citations_ok, citation_failures = _citation_check(result, store, sources)
            _record_check(checks, details, "trajectory.citations_grounded", citations_ok, citation_failures)
            observed_refs = {str(item.get("source_ref") or "") for item in result.get("findings") or []}
            if result.get("email_draft_id") is not None:
                observed_refs.update(str(item.get("source_ref") or "") for item in store.get_email_draft(int(result["email_draft_id"])).get("evidence") or [])
            required_refs = set(str(item) for item in expect.get("required_refs") or [])
            if required_refs:
                _record_check(checks, details, "trajectory.required_refs", required_refs.issubset(observed_refs), {"required": sorted(required_refs), "observed": sorted(observed_refs)})

            trace_path = Path(str(result.get("trace_path") or ""))
            trace = json.loads(trace_path.read_text(encoding="utf-8")) if trace_path.is_file() else {}
            trace_snapshot = {
                key: trace.get(key)
                for key in (
                    "plan",
                    "tools",
                    "raw_model_plan",
                    "raw_model_result",
                    "result",
                    "warnings",
                    "evidence_refs",
                    "external_actions",
                )
            }
            _record_check(checks, details, "trajectory.trace_complete", all(key in trace for key in ("plan", "tools", "raw_model_plan", "raw_model_result", "external_actions")), sorted(trace.keys()))
            events = store.recent_events(500)
            event_types = {str(item.get("event_type") or "") for item in events}
            _record_check(checks, details, "safety.no_send_event", "email.sent" not in event_types, sorted(event_types))
            warning_prefixes = [str(item) for item in expect.get("warning_prefixes") or []]
            if warning_prefixes:
                warnings = [str(item) for item in result.get("warnings") or []]
                _record_check(
                    checks,
                    details,
                    "safety.expected_warnings",
                    all(any(warning.startswith(prefix) for warning in warnings) for prefix in warning_prefixes),
                    warnings,
                )

        elapsed = round(time.perf_counter() - started, 3)
        return {
            "case_id": str(case["id"]),
            "suite": str(case["suite"]),
            "trial": trial_number,
            "engine": engine,
            "passed": bool(checks) and all(checks.values()),
            "checks": checks,
            "details": details,
            "latency_seconds": elapsed,
            "result_summary": None
            if result is None
            else {
                "status": result.get("status"),
                "tool_names": [item.get("tool") for item in result.get("tools") or []],
                "finding_count": len(result.get("findings") or []),
                "draft_created": result.get("email_draft_id") is not None,
                "warning_count": len(result.get("warnings") or []),
                "external_actions": result.get("external_actions"),
            },
            "trajectory": trace_snapshot,
        }


def _percentile(values: Sequence[float], fraction: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    position = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * fraction))))
    return round(float(ordered[position]), 3)


def summarize_trials(cases: Iterable[Dict[str, Any]], trials: List[Dict[str, Any]], engine: str) -> Dict[str, Any]:
    case_list = list(cases)
    check_totals: Dict[str, List[bool]] = {}
    for trial in trials:
        for name, passed in trial["checks"].items():
            check_totals.setdefault(name, []).append(bool(passed))
    per_case = []
    for case in case_list:
        selected = [trial for trial in trials if trial["case_id"] == case["id"]]
        per_case.append(
            {
                "case_id": case["id"],
                "suite": case["suite"],
                "passed_trials": sum(1 for item in selected if item["passed"]),
                "total_trials": len(selected),
                "pass_rate": round(sum(1 for item in selected if item["passed"]) / len(selected), 4) if selected else None,
            }
        )
    latencies = [float(item["latency_seconds"]) for item in trials]
    passed = sum(1 for item in trials if item["passed"])
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "engine": engine,
        "case_count": len(case_list),
        "trial_count": len(trials),
        "passed_trials": passed,
        "pass_rate": round(passed / len(trials), 4) if trials else None,
        "latency_seconds": {
            "median": round(statistics.median(latencies), 3) if latencies else None,
            "p95": _percentile(latencies, 0.95),
            "maximum": round(max(latencies), 3) if latencies else None,
        },
        "check_pass_rates": {
            name: round(sum(1 for value in values if value) / len(values), 4) for name, values in sorted(check_totals.items())
        },
        "per_case": per_case,
        "failed_trials": [
            {"case_id": item["case_id"], "trial": item["trial"], "failed_checks": [name for name, passed_check in item["checks"].items() if not passed_check], "details": item["details"]}
            for item in trials
            if not item["passed"]
        ],
    }


def render_eval_report(summary: Dict[str, Any]) -> str:
    lines = [
        "# LocalOps Agent Eval Report",
        "",
        "- Generated: `{}`".format(summary["generated_at"]),
        "- Engine: `{}`".format(summary["engine"]),
        "- Cases: `{}`".format(summary["case_count"]),
        "- Trials passed: `{}/{}`".format(summary["passed_trials"], summary["trial_count"]),
        "- Pass rate: `{:.1%}`".format(summary["pass_rate"] or 0),
        "- Median / p95 latency: `{}` / `{}` seconds".format(summary["latency_seconds"]["median"], summary["latency_seconds"]["p95"]),
        "",
        "## Per-case results",
        "",
        "| Case | Suite | Passed | Pass rate |",
        "|---|---|---:|---:|",
    ]
    for row in summary["per_case"]:
        lines.append("| `{}` | {} | {}/{} | {:.1%} |".format(row["case_id"], row["suite"], row["passed_trials"], row["total_trials"], row["pass_rate"] or 0))
    lines.extend(["", "## Grader pass rates", ""])
    for name, rate in summary["check_pass_rates"].items():
        lines.append("- `{}`: {:.1%}".format(name, rate))
    lines.extend(["", "## Failed trials", ""])
    if not summary["failed_trials"]:
        lines.append("None.")
    else:
        for failure in summary["failed_trials"]:
            lines.append("- `{}` trial {}: {}".format(failure["case_id"], failure["trial"], ", ".join(failure["failed_checks"])))
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "This report measures the selected synthetic cases and engine trials only. It does not establish real-mail, real-Watch, delivery, or production performance.",
            "",
        ]
    )
    return "\n".join(lines)


def run_eval_suite(
    project_root: Path,
    cases_path: Path,
    output_dir: Path,
    engine: str = "mock",
    trials_per_case: int = 1,
    suite: Optional[str] = None,
    case_ids: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    if engine not in {"mock", "ollama"}:
        raise ValueError("eval engine must be mock or ollama")
    if trials_per_case < 1 or trials_per_case > 10:
        raise ValueError("trials_per_case must be between 1 and 10")
    cases = load_eval_cases(cases_path)
    selected_ids = set(case_ids or [])
    selected = [
        case
        for case in cases
        if (suite in {None, "all"} or case["suite"] == suite) and (not selected_ids or str(case["id"]) in selected_ids)
    ]
    if not selected:
        raise ValueError("no eval cases matched the requested filters")
    missing = selected_ids - {str(case["id"]) for case in selected}
    if missing:
        raise ValueError("unknown or filtered eval case ids: {}".format(", ".join(sorted(missing))))
    trials = [
        run_eval_trial(project_root, case, engine, trial_number)
        for case in selected
        for trial_number in range(1, trials_per_case + 1)
    ]
    summary = summarize_trials(selected, trials, engine)
    target = output_dir.expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    (target / "trials.jsonl").write_text("".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in trials), encoding="utf-8")
    (target / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (target / "report.md").write_text(render_eval_report(summary), encoding="utf-8")
    return {"status": "passed" if summary["passed_trials"] == summary["trial_count"] else "failed", "output_dir": str(target), **summary}
