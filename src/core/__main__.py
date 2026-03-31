"""
Orchestrator CLI Entry Point
==============================

Usage:
    python -m src.core init --data-dir .astra --prompt "Add auth" --detection '{...}'
    python -m src.core record --data-dir .astra --role architect --output '...'
    python -m src.core record-hitl --data-dir .astra --gate post_plan --decision continue
    python -m src.core resume --data-dir .astra --run-dir .astra/runs/001-...

All commands output a single JSON action to stdout.
All logging goes to stderr.
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

from .config import load_config
from .orchestrator import Orchestrator

logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
logger = logging.getLogger(__name__)

STATE_FILE = ".orchestrator_state.json"


def _resolve_dirs(data_dir: str) -> tuple:
    """Resolve prompts and references dirs relative to the plugin root."""
    # Plugin root is 2 levels up from src/core/
    plugin_root = Path(__file__).parent.parent.parent
    prompts_dir = plugin_root / "src" / "prompts"
    references_dir = plugin_root / "references"
    return prompts_dir, references_dir


def _save_state(data_dir: Path, orch: Orchestrator) -> None:
    """Persist orchestrator state between CLI calls."""
    state = {
        "run_dir": str(orch.run_dir) if orch.run_dir else None,
        "project_dir": str(orch.project_dir) if orch.project_dir else None,
        "detection": orch._detection,
        "prompt": orch._prompt,
        "planner_sequence": orch._planner_sequence,
        "planner_index": orch._planner_index,
        "current_task_evaluators": orch._current_task_evaluators,
        "current_task_verdicts": orch._current_task_verdicts,
        "current_task_id_for_eval": orch._current_task_id_for_eval,
        "iteration_count": orch._iteration_count,
        "start_time": orch._start_time,
    }
    state_path = data_dir / STATE_FILE
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2))


def _load_state(data_dir: Path, orch: Orchestrator) -> None:
    """Restore orchestrator state from previous CLI call."""
    state_path = data_dir / STATE_FILE
    if not state_path.exists():
        return
    state = json.loads(state_path.read_text())
    if state.get("run_dir"):
        orch.run_dir = Path(state["run_dir"])
        from .event_store import EventStore
        orch._store = EventStore(orch.run_dir)
    if state.get("project_dir"):
        orch.project_dir = Path(state["project_dir"])
    orch._detection = state.get("detection", {})
    orch._prompt = state.get("prompt", "")
    orch._planner_sequence = state.get("planner_sequence", [])
    orch._planner_index = state.get("planner_index", 0)
    orch._current_task_evaluators = state.get("current_task_evaluators", [])
    orch._current_task_verdicts = state.get("current_task_verdicts", [])
    orch._current_task_id_for_eval = state.get("current_task_id_for_eval")
    orch._iteration_count = state.get("iteration_count", 0)
    orch._start_time = state.get("start_time", time.time())

    # Reload work plan if it exists
    if orch.run_dir:
        wp_path = orch.run_dir / "work_plan.json"
        if wp_path.exists():
            from .work_plan import WorkPlan
            orch._work_plan = WorkPlan.load(wp_path)


def _make_orchestrator(data_dir: str, config_path: str = None) -> tuple:
    """Create orchestrator with config."""
    data_dir = Path(data_dir)
    prompts_dir, references_dir = _resolve_dirs(data_dir)
    config = load_config(Path(config_path)) if config_path else load_config(Path("astra.yaml"))

    orch = Orchestrator(
        data_dir=data_dir,
        config=config,
        prompts_dir=prompts_dir,
        references_dir=references_dir,
    )
    return orch, data_dir


def cmd_init(args):
    orch, data_dir = _make_orchestrator(args.data_dir, args.config)
    if args.project_dir:
        orch.project_dir = Path(args.project_dir)

    detection = json.loads(args.detection) if args.detection else {}

    action = orch.init(
        prompt=args.prompt or "",
        detection=detection,
        plan_path=args.plan,
        spec_path=args.spec,
    )
    _save_state(data_dir, orch)
    print(json.dumps(action))


def cmd_record(args):
    orch, data_dir = _make_orchestrator(args.data_dir, args.config)
    _load_state(data_dir, orch)

    action = orch.record(
        role=args.role,
        output=args.output or "",
        task_id=args.task_id,
        verdict=args.verdict,
    )
    _save_state(data_dir, orch)
    print(json.dumps(action))


def cmd_record_hitl(args):
    orch, data_dir = _make_orchestrator(args.data_dir, args.config)
    _load_state(data_dir, orch)

    action = orch.record_hitl(
        gate=args.gate,
        decision=args.decision,
        instructions=args.instructions or "",
    )
    _save_state(data_dir, orch)
    print(json.dumps(action))


def cmd_resume(args):
    orch, data_dir = _make_orchestrator(args.data_dir, args.config)
    run_dir = Path(args.run_dir) if args.run_dir else None

    if run_dir is None:
        from .runs import RunManager
        rm = RunManager(data_dir)
        run_dir = rm.get_current()
        if run_dir is None:
            print(json.dumps({"action": "error", "message": "No current run to resume"}))
            return

    action = orch.resume(run_dir=run_dir)
    _save_state(data_dir, orch)
    print(json.dumps(action))


def main():
    parser = argparse.ArgumentParser(prog="python -m src.core", description="Astra orchestrator CLI")
    sub = parser.add_subparsers(dest="command")

    # init
    p_init = sub.add_parser("init", help="Start a new run")
    p_init.add_argument("--data-dir", required=True)
    p_init.add_argument("--prompt", default="")
    p_init.add_argument("--detection", default="{}")
    p_init.add_argument("--plan", default=None)
    p_init.add_argument("--spec", default=None)
    p_init.add_argument("--config", default=None)
    p_init.add_argument("--project-dir", default=None)

    # record
    p_rec = sub.add_parser("record", help="Record agent output")
    p_rec.add_argument("--data-dir", required=True)
    p_rec.add_argument("--role", required=True)
    p_rec.add_argument("--output", default="")
    p_rec.add_argument("--task-id", default=None)
    p_rec.add_argument("--verdict", default=None)
    p_rec.add_argument("--config", default=None)

    # record-hitl
    p_hitl = sub.add_parser("record-hitl", help="Record HITL gate decision")
    p_hitl.add_argument("--data-dir", required=True)
    p_hitl.add_argument("--gate", required=True)
    p_hitl.add_argument("--decision", required=True)
    p_hitl.add_argument("--instructions", default="")
    p_hitl.add_argument("--config", default=None)

    # resume
    p_resume = sub.add_parser("resume", help="Resume an interrupted run")
    p_resume.add_argument("--data-dir", required=True)
    p_resume.add_argument("--run-dir", default=None)
    p_resume.add_argument("--config", default=None)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "init": cmd_init,
        "record": cmd_record,
        "record-hitl": cmd_record_hitl,
        "resume": cmd_resume,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
