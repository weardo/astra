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
import os
import time
from pathlib import Path
from typing import Optional

from .circuit_breaker import CircuitBreaker, hash_error
from .completion import check_exit_conditions
from .discovery import format_for_prompt as format_discoveries
from .event_store import EventStore
from .planner import build_role_prompt, get_role_sequence, resolve_model
from .progress import parse_status_block
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
        # Evaluator state
        self._current_task_evaluators: list = []
        self._current_task_verdicts: list = []
        self._current_task_id_for_eval: Optional[str] = None
        # Circuit breaker (initialized when run_dir is set)
        self._circuit_breaker: Optional[CircuitBreaker] = None
        # Budget/time/iteration tracking
        self._start_time: float = 0.0
        self._iteration_count: int = 0
        # Checkpoint (per-session, not persisted)
        self._tasks_completed_this_session: int = 0
        self._headless: Optional[bool] = None  # Resolved lazily

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
        self._circuit_breaker = CircuitBreaker(
            self.run_dir, self._config.get("circuit_breaker", {}),
        )
        self._start_time = time.time()
        self._iteration_count = 0
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
            strategy=strategy,
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

        # Evaluator phase
        if role in ("test-runner", "code-reviewer", "browser-tester", "spec-reviewer"):
            return self._handle_evaluator_output(task_id, role, verdict, output)

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

        if gate == "on_circuit_break":
            if self._circuit_breaker:
                self._circuit_breaker.reset()
            return self._dispatch_next_task()

        if gate == "budget_warning":
            return self._dispatch_next_task()

        return {"action": "error", "message": f"Unknown gate: {gate}"}

    def resume(self, run_dir: Path) -> dict:
        """Resume a previous run from its event log."""
        self.run_dir = Path(run_dir)
        self._store = EventStore(self.run_dir)
        self._circuit_breaker = CircuitBreaker(
            self.run_dir, self._config.get("circuit_breaker", {}),
        )
        self._start_time = time.time()
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
        ext = ".json" if role in ("architect", "adversary", "refiner", "validator", "fixer", "verifier") else ".md"
        save_path = str(self.run_dir / f"{role}_output{ext}")

        # Write prompt to file for executor dispatch
        prompt_file = self.run_dir / f"prompt_{role}.md"
        prompt_file.write_text(prompt)

        return {
            "action": "dispatch_agent",
            "role": role,
            "model": model,
            "prompt": prompt[:200],
            "prompt_file": str(prompt_file),
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
                strategy=self._config.get("strategy", "feature"),
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

        # Write prompt to file for executor dispatch
        prompt_file = self.run_dir / f"prompt_generator_{task['id']}.md"
        prompt_file.write_text(prompt)

        return {
            "action": "dispatch_agent",
            "role": "generator",
            "model": model,
            "prompt": prompt[:200],
            "prompt_file": str(prompt_file),
            "save_output_to": str(self.run_dir / f"generator_{task['id']}.md"),
            "task_id": task["id"],
        }

    def _handle_generator_output(
        self, task_id: Optional[str], verdict: Optional[str], output: str
    ) -> dict:
        # Parse status block from output
        status = parse_status_block(output)
        if status:
            self._store.append({
                "type": "status_block_parsed",
                "data": status,
            })

        # Increment iteration count
        self._iteration_count += 1

        if task_id and verdict == "PASS":
            # Record progress in circuit breaker
            if self._circuit_breaker:
                self._circuit_breaker.record_iteration(
                    progress=True, output_length=len(output),
                )

            # Check if evaluators are configured
            evaluators = self._config.get("evaluators", [])
            if evaluators:
                self._current_task_evaluators = list(evaluators)
                self._current_task_verdicts = []
                self._current_task_id_for_eval = task_id
                return self._dispatch_next_evaluator()

            wp_path = self.run_dir / "work_plan.json"
            task = self._work_plan.get_task(task_id)
            self._work_plan.mark_task_done(task_id, wp_path)
            self._tasks_completed_this_session += 1
            self._store.append({
                "type": "task_completed",
                "data": {"task_id": task_id, "verdict": "PASS"},
            })
            # Scope drift detection
            if task:
                drift = self._detect_scope_drift_static(self.run_dir, task)
                if drift:
                    self._store.append({
                        "type": "scope_drift_detected",
                        "data": {"task_id": task_id, "undeclared_files": drift},
                    })
        elif task_id and verdict == "FAIL":
            # Record no-progress in circuit breaker
            if self._circuit_breaker:
                cb_state = self._circuit_breaker.record_iteration(
                    progress=False,
                    error_hash=hash_error(output) if output else None,
                    output_length=len(output),
                )
                if cb_state == CircuitBreaker.OPEN:
                    return self._present_hitl_gate("on_circuit_break")

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

        # Checkpoint check (per-session task count)
        checkpoint_threshold = self._config.get("checkpoint_every_n_tasks", 0)
        if checkpoint_threshold > 0 and self._tasks_completed_this_session >= checkpoint_threshold:
            return {
                "action": "checkpoint",
                "summary": self._work_plan.count_tasks() if self._work_plan else {},
            }

        # Check exit conditions (budget/time/iteration limits)
        exit_check = self._check_exit_conditions()
        if exit_check:
            return exit_check

        return self._dispatch_next_task()

    def _check_exit_conditions(self) -> Optional[dict]:
        """Check budget, time, and iteration limits."""
        elapsed = time.time() - self._start_time
        state_dict = {
            "iteration": self._iteration_count,
            "total_cost_usd": 0,  # Cost tracking not yet wired
        }
        result = check_exit_conditions(state_dict, self._config, elapsed)
        if result and result.get("should_exit"):
            return self._present_hitl_gate("budget_warning")

    # -------------------------------------------------------------------------
    # Evaluator loop
    # -------------------------------------------------------------------------

    def _dispatch_next_evaluator(self) -> dict:
        if not self._current_task_evaluators:
            return self._finalize_evaluators()

        role = self._current_task_evaluators.pop(0)
        model = resolve_model(role, self._config)

        # Build evaluator prompt from template if available, else minimal
        task = self._work_plan.get_task(self._current_task_id_for_eval)
        replacements = {
            "{{DETECTION_JSON}}": json.dumps(self._detection, indent=2),
            "{{CURRENT_TASK}}": json.dumps(task, indent=2) if task else "{}",
            "{{RUN_DIR}}": str(self.run_dir),
            "{{TEST_COMMAND}}": self._detection.get("test_command", "npm test"),
        }
        # Use role-specific template if it exists, fall back to generic evaluator
        template_role = role if (self._prompts_dir / f"{role}.md").exists() else "evaluator"
        replacements["{{EVALUATOR_ROLE}}"] = role
        prompt = build_role_prompt(
            template_role, self._prompts_dir, replacements,
            references_dir=self._references_dir,
        )

        prompt_file = self.run_dir / f"prompt_{role}_{self._current_task_id_for_eval}.md"
        prompt_file.write_text(prompt)

        return {
            "action": "dispatch_agent",
            "role": role,
            "model": model,
            "prompt": prompt[:200],
            "prompt_file": str(prompt_file),
            "save_output_to": str(self.run_dir / f"{role}_{self._current_task_id_for_eval}.md"),
            "task_id": self._current_task_id_for_eval,
        }

    def _handle_evaluator_output(
        self, task_id: Optional[str], role: str, verdict: Optional[str], output: str
    ) -> dict:
        self._current_task_verdicts.append({
            "agent": role,
            "verdict": verdict or "PASS",
            "details": output[:500],
        })

        # Early exit on FAIL — skip remaining evaluators
        if verdict == "FAIL":
            self._current_task_evaluators.clear()
            return self._finalize_evaluators()

        # More evaluators remaining
        if self._current_task_evaluators:
            return self._dispatch_next_evaluator()

        return self._finalize_evaluators()

    def _finalize_evaluators(self) -> dict:
        """Combine verdicts and either advance or retry."""
        task_id = self._current_task_id_for_eval
        combined = self.combine_verdicts(self._current_task_verdicts)

        if combined["verdict"] == "PASS":
            wp_path = self.run_dir / "work_plan.json"
            self._work_plan.mark_task_done(task_id, wp_path)
            self._tasks_completed_this_session += 1
            self._store.append({
                "type": "task_completed",
                "data": {"task_id": task_id, "verdict": "PASS"},
            })

            # Checkpoint check
            checkpoint_threshold = self._config.get("checkpoint_every_n_tasks", 0)
            if checkpoint_threshold > 0 and self._tasks_completed_this_session >= checkpoint_threshold:
                return {
                    "action": "checkpoint",
                    "summary": self._work_plan.count_tasks() if self._work_plan else {},
                }

            return self._dispatch_next_task()

        # FAIL — write feedback and retry
        feedback_path = self.run_dir / "feedback.md"
        feedback_lines = [f"# Evaluator Feedback for {task_id}\n"]
        for reason in combined["reasons"]:
            feedback_lines.append(f"- {reason}\n")
        feedback_path.write_text("\n".join(feedback_lines))

        self._store.append({
            "type": "task_retry",
            "data": {"task_id": task_id, "reason": "evaluator_fail"},
        })
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

    @property
    def _is_headless(self) -> bool:
        if self._headless is not None:
            return self._headless
        return bool(os.environ.get("CI") or os.environ.get("ASTRA_HEADLESS"))

    def _present_hitl_gate(self, gate: str) -> dict:
        if self._is_headless:
            logger.info("Headless mode: auto-continuing past gate %s", gate)
            return self.record_hitl(gate=gate, decision="continue")
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
                for ext in (".json", ".md"):
                    prev_path = self.run_dir / f"{prev_role}_output{ext}"
                    if prev_path.exists():
                        replacements[f"{{{{{prev_role.upper()}_OUTPUT}}}}"] = prev_path.read_text()
                        break
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
            "{{DISCOVERIES}}": format_discoveries(self.run_dir),
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
