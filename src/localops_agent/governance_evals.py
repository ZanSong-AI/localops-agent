from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List

from .actions import propose_action, simulate_action
from .config import Config
from .context_learning import export_context_candidate, propose_context_candidates
from .db import Store
from .research import run_research


def _expect_error(name: str, expected: type, operation: Callable[[], Any]) -> Dict[str, Any]:
    try:
        operation()
    except expected as exc:
        return {"case_id": name, "passed": True, "evidence": "{}: {}".format(expected.__name__, exc)}
    except Exception as exc:
        return {"case_id": name, "passed": False, "evidence": "unexpected {}: {}".format(type(exc).__name__, exc)}
    return {"case_id": name, "passed": False, "evidence": "expected {} was not raised".format(expected.__name__)}


def run_governance_eval(project_root: Path, output_dir: Path) -> Dict[str, Any]:
    root = project_root.expanduser().resolve()
    fixtures = root / "tests" / "fixtures"
    trials: List[Dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="localops-governance-eval-") as temp_name:
        config = Config.load(root=root, state_dir=Path(temp_name) / "state")
        config.ensure_state()
        store = Store(config.database)

        context = propose_context_candidates(config, store, fixtures / "synthetic_context_note.md", engine="mock")
        context_source = (fixtures / "synthetic_context_note.md").read_text(encoding="utf-8")
        context_ok = bool(context["candidates"]) and all(
            item["status"] == "candidate" and item["evidence_quote"] in context_source for item in context["candidates"]
        )
        trials.append({"case_id": "context_candidates_are_grounded", "passed": context_ok, "evidence": context})
        candidate_id = int(context["candidates"][0]["id"])
        trials.append(
            _expect_error(
                "context_export_requires_confirmation",
                PermissionError,
                lambda: export_context_candidate(store, candidate_id, Path(temp_name) / "blocked.md"),
            )
        )

        action = propose_action(store, fixtures / "synthetic_action.json")
        trials.append(
            _expect_error(
                "action_simulation_requires_approval",
                PermissionError,
                lambda: simulate_action(store, int(action["action_id"])),
            )
        )
        store.transition_action_proposal(int(action["action_id"]), "approved")
        simulated = simulate_action(store, int(action["action_id"]))
        simulation_ok = (
            simulated["status"] == "simulated"
            and simulated["external_actions"] == "none"
            and simulated["receipt"]["adapter_called"] is False
            and simulated["receipt"]["delivery_status"] == "not_attempted"
        )
        trials.append({"case_id": "approved_action_is_still_simulation_only", "passed": simulation_ok, "evidence": simulated})

        trials.append(
            _expect_error(
                "research_rejects_private_packet",
                PermissionError,
                lambda: run_research(
                    config,
                    store,
                    "private test",
                    fixtures / "synthetic_research.jsonl",
                    privacy="private",
                    engine="mock",
                ),
            )
        )
        research = run_research(
            config,
            store,
            "Compare synthetic benchmark values.",
            fixtures / "synthetic_research.jsonl",
            privacy="public",
            engine="mock",
        )
        research_ok = (
            research["external_actions"] == "none"
            and len(research["findings"]) == 2
            and len(research["conflicts"]) == 1
            and any(item["freshness"]["status"] == "stale" for item in research["sources"])
        )
        trials.append({"case_id": "research_citations_conflicts_and_freshness", "passed": research_ok, "evidence": research})

    passed = sum(1 for item in trials if item["passed"])
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "case_count": len(trials),
        "passed_cases": passed,
        "pass_rate": round(passed / len(trials), 4),
        "status": "passed" if passed == len(trials) else "failed",
        "external_actions": "none",
        "cases": [{"case_id": item["case_id"], "passed": item["passed"]} for item in trials],
    }
    target = output_dir.expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    (target / "trials.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in trials), encoding="utf-8"
    )
    (target / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# LocalOps Phase 2-4 Governance Eval",
        "",
        "- Passed: `{}/{}`".format(passed, len(trials)),
        "- External actions: `none`",
        "",
        "| Case | Passed |",
        "|---|---:|",
    ]
    lines.extend("| `{}` | {} |".format(item["case_id"], "yes" if item["passed"] else "no") for item in trials)
    lines.extend(
        [
            "",
            "This synthetic evaluation verifies governance behavior only. It does not claim real YAGE writes, message delivery, Apple app mutation, autonomous web collection, or production performance.",
            "",
        ]
    )
    (target / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return {**summary, "output_dir": str(target)}
