"""
CLI-Driven Orchestrator
========================

State machine that returns JSON action instructions.
The SKILL.md is a thin executor — this module makes all decisions.

Usage:
    orch = Orchestrator(data_dir, config, prompts_dir, references_dir)
    action = orch.init(prompt="Add auth", detection={...})
    # action = {"action": "dispatch_agent", "role": "architect", "model": "opus", "prompt": "..."}

    action = orch.record(role="architect", output="...")
    # action = {"action": "dispatch_agent", "role": "adversary", ...}

    action = orch.record_hitl(gate="post_plan", decision="continue")
    # action = {"action": "dispatch_agent", "role": "generator", ...}
"""

import json
import logging
from pathlib import Path
from typing import Optional

from .event_store import EventStore
from .planner import build_role_prompt, get_role_sequence, resolve_model
from .repo_map import generate_lightweight_map
from .runs import RunManager
from .work_plan import WorkPlan

logger = logging.getLogger(__name__)


class Orchestrator:
    """State machine orchestrator returning JSON action instructions."""

    def __init__(
        self,
        data_dir: Path,
        config: dict,
        prompts_dir: Path,
        references_dir: Path,
    ):
        self._data_dir = Path(data_dir)
        self._config = config
        self._prompts_dir = Path(prompts_dir)
        self._references_dir = Path(references_dir)
        self._run_manager = RunManager(self._data_dir)
        self.run_dir: Optional[Path] = None
        self.project_dir: Optional[Path] = None
        self._store: Optional[EventStore] = None
        self._work_plan: Optional[WorkPlan] = None
        self._planner_sequence: list = []
        self._planner_index: int = 0
        self._detection: dict = {}
        self._prompt: str = ""

    def init(
        self,
        prompt: str = "",
        detection: Optional[dict] = None,
        plan_path: Optional[str] = None,
        spec_path: Optional[str] = None,
    ) -> dict:
        """Start a new run. Returns the first action."""
        strategy = self._config.get("strategy", "feature")
        self.run_dir = self._run_manager.create_run(strategy)
        self._store = EventStore(self.run_dir)
        self._detection = detection or {}
        self._prompt = prompt

        self._store.append({
            "type": "run_started",
            "data": {"run_id": self.run_dir.name, "prompt": prompt},
        })

        # Write sentinel
        self._write_sentinel()

        # Determine input mode
        if plan_path:
            return self._load_plan_and_start_generator(plan_path)
        elif spec_path:
            input_mode = "spec"
        else:
            input_mode = "prompt"

        # Start planner pipeline
        self._planner_sequence = get_role_sequence(
            input_mode, task_count=10,  # estimate, adjusted after architect
            thresholds=self._config.get("pipeline_depth"),
        )
        self._planner_index = 0
        return self._dispatch_next_planner_role()

    def record(
        self,
        role: str,
        output: str,
        task_id: Optional[str] = None,
        verdict: Optional[str] = None,
    ) -> dict:
        """Record an agent's output and return the next action."""
        self._store.append({
            "type": f"{role}_completed",
            "data": {"role": role, "task_id": task_id, "verdict": verdict},
        })

        # Planner phase
        if role in ("architect", "adversary", "refiner", "validator", "verifier"):
            return self._handle_planner_output(role, output)

        # Generator phase
        if role == "generator":
            return self._handle_generator_output(task_id, verdict, output)

        return {"action": "error", "message": f"Unknown role: {role}"}

    def record_hitl(self, gate: str, decision: str, instructions: str = "") -> dict:
        """Record a HITL gate decision and return next action."""
        self._store.append({
            "type": "hitl_gate",
            "data": {"gate_name": gate, "action": decision, "instructions": instructions},
        })

        if decision == "abort":
            self._cleanup()
            return {"action": "complete", "reason": "Aborted by user at gate: " + gate}

        if gate == "post_plan":
            return self._start_generator_loop()

        return {"action": "error", "message": f"Unknown gate: {gate}"}

    def resume(self, run_dir: Path) -> dict:
        """Resume a previous run from its event log."""
        self.run_dir = Path(run_dir)
        self._store = EventStore(self.run_dir)
        state = self._store.materialize_state()

        # Load work plan if it exists
        wp_path = self.run_dir / "work_plan.json"
        if wp_path.exists():
            self._work_plan = WorkPlan.load(wp_path)

        self._write_sentinel()

        if state["phase"] == "init":
            return {"action": "resume", "phase": "init", "message": "Run initialized but no progress"}
        elif state["phase"] == "generator":
            return self._start_generator_loop()
        elif state["phase"] == "complete":
            return {"action": "complete", "reason": "Run already complete"}

        return {"action": "resume", "phase": state["phase"]}

    # -------------------------------------------------------------------------
    # Planner logic
    # -------------------------------------------------------------------------

    def _dispatch_next_planner_role(self) -> dict:
        if self._planner_index >= len(self._planner_sequence):
            return {"action": "error", "message": "Planner sequence exhausted"}

        role = self._planner_sequence[self._planner_index]
        replacements = self._build_planner_replacements(role)
        prompt = build_role_prompt(
            role, self._prompts_dir, replacements,
            references_dir=self._references_dir,
        )
        model = resolve_model(role, self._config)
        # Architect/refiner produce JSON work plans, others produce markdown
        ext = ".json" if role in ("architect", "refiner", "fixer") else ".md"
        save_path = str(self.run_dir / f"{role}_output{ext}")

        return {
            "action": "dispatch_agent",
            "role": role,
            "model": model,
            "prompt": prompt,
            "save_output_to": save_path,
        }

    def _handle_planner_output(self, role: str, output: str) -> dict:
        # Try to parse work plan from output
        if role in ("architect", "refiner", "fixer"):
            self._try_load_work_plan(output)

        self._planner_index += 1

        # After architect, recalculate sequence based on actual task count
        if role == "architect" and self._work_plan:
            task_count = self._work_plan.count_tasks()["total"]
            input_mode = "spec" if not self._prompt else "prompt"
            self._planner_sequence = get_role_sequence(
                input_mode, task_count=task_count,
                thresholds=self._config.get("pipeline_depth"),
            )
            self._planner_index = 1  # Skip architect (already done)

        # Check if planner sequence is complete
        if self._planner_index >= len(self._planner_sequence):
            self._store.append({"type": "planner_completed", "data": {}})
            if self._config.get("hitl", {}).get("post_plan", True):
                return self._present_hitl_gate("post_plan")
            return self._start_generator_loop()

        return self._dispatch_next_planner_role()

    def _try_load_work_plan(self, output: str) -> None:
        """Try to parse work plan JSON from agent output."""
        try:
            data = json.loads(output)
            if "phases" in data:
                self._work_plan = WorkPlan(data)
                wp_path = self.run_dir / "work_plan.json"
                self._work_plan.save(wp_path)
        except (json.JSONDecodeError, TypeError):
            # Agent might output markdown with embedded JSON
            import re
            match = re.search(r'\{[\s\S]*"phases"[\s\S]*\}', output)
            if match:
                try:
                    data = json.loads(match.group())
                    self._work_plan = WorkPlan(data)
                    wp_path = self.run_dir / "work_plan.json"
                    self._work_plan.save(wp_path)
                except (json.JSONDecodeError, TypeError):
                    pass

    # -------------------------------------------------------------------------
    # Generator loop
    # -------------------------------------------------------------------------

    def _start_generator_loop(self) -> dict:
        if self._work_plan is None:
            wp_path = self.run_dir / "work_plan.json"
            if wp_path.exists():
                self._work_plan = WorkPlan.load(wp_path)
            else:
                return {"action": "error", "message": "No work plan available"}

        return self._dispatch_next_task()

    def _dispatch_next_task(self) -> dict:
        task = self._work_plan.get_next_task()
        if task is None:
            self._cleanup()
            return {
                "action": "complete",
                "summary": self._work_plan.count_tasks(),
            }

        # Write current_task.json
        task_path = self.run_dir / "current_task.json"
        task_path.write_text(json.dumps(task, indent=2))

        self._store.append({
            "type": "task_started",
            "data": {"task_id": task["id"], "title": task.get("description", "")},
        })

        replacements = self._build_generator_replacements(task)
        prompt = build_role_prompt(
            "generator", self._prompts_dir, replacements,
            references_dir=self._references_dir,
        )
        model = resolve_model("generator", self._config)

        return {
            "action": "dispatch_agent",
            "role": "generator",
            "model": model,
            "prompt": prompt,
            "save_output_to": str(self.run_dir / f"generator_{task['id']}.md"),
            "task_id": task["id"],
        }

    def _handle_generator_output(
        self, task_id: Optional[str], verdict: Optional[str], output: str
    ) -> dict:
        if task_id and verdict == "PASS":
            wp_path = self.run_dir / "work_plan.json"
            self._work_plan.mark_task_done(task_id, wp_path)
            self._store.append({
                "type": "task_completed",
                "data": {"task_id": task_id, "verdict": "PASS"},
            })
        elif task_id and verdict == "FAIL":
            wp_path = self.run_dir / "work_plan.json"
            attempts = self._work_plan.increment_task_attempts(task_id, wp_path)
            if attempts >= 3:
                self._work_plan.mark_task_blocked(task_id, "max retries", wp_path)
                self._store.append({
                    "type": "task_completed",
                    "data": {"task_id": task_id, "verdict": "BLOCKED"},
                })
            else:
                self._store.append({
                    "type": "task_retry",
                    "data": {"task_id": task_id, "attempt": attempts},
                })
                # Re-dispatch same task with feedback
                return self._dispatch_next_task()

        return self._dispatch_next_task()

    def _load_plan_and_start_generator(self, plan_path: str) -> dict:
        """Load existing work plan and skip to generator."""
        self._work_plan = WorkPlan.load(Path(plan_path))
        wp_dest = self.run_dir / "work_plan.json"
        self._work_plan.save(wp_dest)
        self._store.append({"type": "planner_completed", "data": {"source": "plan_file"}})
        return self._start_generator_loop()

    # -------------------------------------------------------------------------
    # Verdict combination
    # -------------------------------------------------------------------------

    @staticmethod
    def combine_verdicts(verdicts: list) -> dict:
        """Combine multiple evaluator verdicts into a single result.

        Args:
            verdicts: List of {agent, verdict, details} dicts.

        Returns:
            {verdict: "PASS"|"FAIL", reasons: list[str]}
        """
        reasons = []
        for v in verdicts:
            if v.get("verdict") == "FAIL":
                reasons.append(f"{v.get('agent', 'unknown')}: {v.get('details', 'failed')}")

        return {
            "verdict": "FAIL" if reasons else "PASS",
            "reasons": reasons,
        }

    # -------------------------------------------------------------------------
    # Scope drift detection
    # -------------------------------------------------------------------------

    @staticmethod
    def _detect_scope_drift_static(run_dir, task: dict) -> list:
        """Check if files were touched that aren't in the task's target_files.

        Returns list of undeclared file paths.
        """
        run_dir = Path(run_dir)
        touched_path = run_dir / "files_touched.txt"
        if not touched_path.exists():
            return []

        target_files = set(task.get("target_files", []))
        touched = set()
        for line in touched_path.read_text().strip().split("\n"):
            line = line.strip()
            if line:
                touched.add(line)

        undeclared = []
        for f in touched:
            # Check if any target_file matches (exact or suffix match)
            matched = False
            for t in target_files:
                if f == t or f.endswith("/" + t) or t.endswith("/" + f.split("/")[-1]):
                    matched = True
                    break
            if not matched:
                undeclared.append(f)

        return undeclared

    # -------------------------------------------------------------------------
    # HITL
    # -------------------------------------------------------------------------

    def _present_hitl_gate(self, gate: str) -> dict:
        context = {}
        if self._work_plan:
            context["task_count"] = self._work_plan.count_tasks()["total"]
            context["phase_count"] = len(self._work_plan.data.get("phases", []))
        return {"action": "hitl_gate", "gate": gate, "context": context}

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _get_repo_map(self) -> str:
        """Generate repo map from project_dir, caching the result."""
        if not hasattr(self, "_repo_map_cache"):
            if self.project_dir and Path(self.project_dir).exists():
                self._repo_map_cache = generate_lightweight_map(self.project_dir)
            else:
                self._repo_map_cache = ""
        return self._repo_map_cache

    def _build_scoped_context(self, task: dict) -> str:
        """Build scoped context: only this task + its dependency chain."""
        if not self._work_plan:
            return json.dumps(task, indent=2)

        context_tasks = [task]
        visited = {task["id"]}

        # Walk dependency chain
        queue = list(task.get("depends_on", []))
        while queue:
            dep_id = queue.pop(0)
            if dep_id in visited:
                continue
            visited.add(dep_id)
            dep_task = self._work_plan.get_task(dep_id)
            if dep_task:
                context_tasks.append(dep_task)
                queue.extend(dep_task.get("depends_on", []))

        return json.dumps(context_tasks, indent=2)

    def _build_planner_replacements(self, role: str) -> dict:
        replacements = {
            "{{DETECTION_JSON}}": json.dumps(self._detection, indent=2),
            "{{REPO_MAP}}": self._get_repo_map(),
            "{{USER_PROMPT}}": self._prompt,
        }
        if self._work_plan:
            replacements["{{WORK_PLAN}}"] = json.dumps(self._work_plan.data, indent=2)
        if role in ("adversary", "refiner"):
            # Load previous output
            for prev_role in ("architect", "adversary"):
                prev_path = self.run_dir / f"{prev_role}_output.md"
                if prev_path.exists():
                    replacements[f"{{{{{prev_role.upper()}_OUTPUT}}}}"] = prev_path.read_text()
        return replacements

    def _build_generator_replacements(self, task: dict) -> dict:
        return {
            "{{DETECTION_JSON}}": json.dumps(self._detection, indent=2),
            "{{REPO_MAP}}": self._get_repo_map(),
            "{{CURRENT_TASK}}": self._build_scoped_context(task),
            "{{FEEDBACK}}": self._load_feedback(),
            "{{TEST_COMMAND}}": self._detection.get("test_command", "npm test"),
            "{{TASK_DESCRIPTION}}": task.get("description", ""),
            "{{RUN_DIR}}": str(self.run_dir),
        }

    def _load_feedback(self) -> str:
        feedback_path = self.run_dir / "feedback.md"
        if feedback_path.exists():
            return feedback_path.read_text()
        return ""

    def _write_sentinel(self) -> None:
        if self.project_dir and self.run_dir:
            sentinel = self.project_dir / ".astra-active-run"
            sentinel.write_text(str(self.run_dir))

    def _delete_sentinel(self) -> None:
        if self.project_dir:
            sentinel = self.project_dir / ".astra-active-run"
            if sentinel.exists():
                sentinel.unlink()

    def _cleanup(self) -> None:
        self._delete_sentinel()
        self._store.append({"type": "run_completed", "data": {}})
