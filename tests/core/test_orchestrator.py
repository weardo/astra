"""Tests for CLI-driven orchestrator (next/record pattern)."""

import json
import time
from pathlib import Path

import pytest

from src.core.orchestrator import Orchestrator


@pytest.fixture
def orch(tmp_path):
    """Orchestrator with a fresh data dir and default config."""
    data_dir = tmp_path / ".astra"
    data_dir.mkdir()
    prompts_dir = Path(__file__).parent.parent.parent / "src" / "prompts"
    references_dir = Path(__file__).parent.parent.parent / "references"
    config = {
        "strategy": "feature",
        "model_routing": {"planner": "opus", "generator": "sonnet", "evaluator": "haiku"},
        "pipeline_depth": {"light_max_tasks": 5, "full_min_tasks": 20},
        "hitl": {"post_plan": True, "on_circuit_break": True, "budget_warning": True},
        "max_cost_usd": 10.0,
    }
    return Orchestrator(
        data_dir=data_dir,
        config=config,
        prompts_dir=prompts_dir,
        references_dir=references_dir,
    )


class TestOrchestratorInit:
    def test_init_creates_run_and_returns_first_action(self, orch):
        action = orch.init(prompt="Add user auth", detection={"stack": "typescript"})
        assert action["action"] == "dispatch_agent"
        assert action["role"] == "architect"
        assert action["model"] == "opus"
        assert "Add user auth" in action["prompt"]
        assert "save_output_to" in action

    def test_init_with_plan_skips_planner(self, orch, tmp_path):
        plan_path = tmp_path / "work_plan.json"
        plan_path.write_text(json.dumps({
            "phases": [{"id": "phase-0", "name": "P0", "epics": [{"id": "e1", "name": "E1",
                "stories": [{"id": "s1", "name": "S1", "tasks": [
                    {"id": "t1", "description": "Do X", "acceptance_criteria": ["x"],
                     "steps": [], "depends_on": [], "target_files": ["src/x.ts"],
                     "status": "pending", "attempts": 0, "blocked_reason": None}
                ]}]}]}]
        }))
        action = orch.init(plan_path=str(plan_path), detection={"stack": "typescript"})
        # Should skip planner, go straight to generator
        assert action["action"] == "dispatch_agent"
        assert action["role"] == "generator"

    def test_init_creates_run_dir(self, orch):
        orch.init(prompt="test", detection={"stack": "python"})
        assert orch.run_dir is not None
        assert orch.run_dir.exists()

    def test_init_writes_sentinel(self, orch, tmp_path):
        # Set project_dir so sentinel can be written
        orch.project_dir = tmp_path / "project"
        orch.project_dir.mkdir()
        orch.init(prompt="test", detection={"stack": "python"})
        sentinel = orch.project_dir / ".astra-active-run"
        assert sentinel.exists()


class TestOrchestratorPlannerSequence:
    def test_record_architect_returns_adversary(self, orch):
        orch.init(prompt="Build a todo app", detection={"stack": "typescript"})
        # Simulate architect output with a work plan containing >5 tasks
        work_plan = {"phases": [{"id": "p0", "name": "P", "epics": [{"id": "e1", "name": "E",
            "stories": [{"id": "s1", "name": "S", "tasks": [
                {"id": f"t{i}", "description": f"Task {i}", "acceptance_criteria": ["ac"],
                 "steps": [], "depends_on": [], "target_files": [f"src/t{i}.ts"],
                 "status": "pending", "attempts": 0, "blocked_reason": None}
                for i in range(10)
            ]}]}]}]}
        action = orch.record(role="architect", output=json.dumps(work_plan))
        assert action["action"] == "dispatch_agent"
        assert action["role"] == "adversary"

    def test_light_depth_skips_adversary_refiner(self, orch):
        orch.init(prompt="Small fix", detection={"stack": "python"})
        # Work plan with 3 tasks → light depth → architect → validator
        work_plan = {"phases": [{"id": "p0", "name": "P", "epics": [{"id": "e1", "name": "E",
            "stories": [{"id": "s1", "name": "S", "tasks": [
                {"id": f"t{i}", "description": f"Task {i}", "acceptance_criteria": ["ac"],
                 "steps": [], "depends_on": [], "target_files": [f"src/t{i}.py"],
                 "status": "pending", "attempts": 0, "blocked_reason": None}
                for i in range(3)
            ]}]}]}]}
        action = orch.record(role="architect", output=json.dumps(work_plan))
        # Should skip adversary/refiner, go to validator
        assert action["role"] == "validator"

    def test_planner_complete_returns_hitl_gate(self, orch):
        orch.init(prompt="test", detection={"stack": "typescript"})
        # Simulate small plan → architect → validator
        work_plan = {"phases": [{"id": "p0", "name": "P", "epics": [{"id": "e1", "name": "E",
            "stories": [{"id": "s1", "name": "S", "tasks": [
                {"id": "t1", "description": "Do X", "acceptance_criteria": ["ac"],
                 "steps": [], "depends_on": [], "target_files": ["src/x.ts"],
                 "status": "pending", "attempts": 0, "blocked_reason": None}
            ]}]}]}]}
        orch.record(role="architect", output=json.dumps(work_plan))
        action = orch.record(role="validator", output='{"valid": true, "issues": []}')
        assert action["action"] == "hitl_gate"
        assert action["gate"] == "post_plan"


class TestOrchestratorGeneratorLoop:
    def _setup_generator_phase(self, orch):
        """Get orchestrator to generator phase with a 2-task plan."""
        orch.init(prompt="test", detection={"stack": "typescript"})
        work_plan = {"phases": [{"id": "p0", "name": "P", "epics": [{"id": "e1", "name": "E",
            "stories": [{"id": "s1", "name": "S", "tasks": [
                {"id": "t1", "description": "Create handler", "acceptance_criteria": ["ac"],
                 "steps": [], "depends_on": [], "target_files": ["src/handler.ts"],
                 "status": "pending", "attempts": 0, "blocked_reason": None},
                {"id": "t2", "description": "Add tests", "acceptance_criteria": ["ac"],
                 "steps": [], "depends_on": ["t1"], "target_files": ["tests/handler.test.ts"],
                 "status": "pending", "attempts": 0, "blocked_reason": None},
            ]}]}]}]}
        orch.record(role="architect", output=json.dumps(work_plan))
        orch.record(role="validator", output='{"valid": true}')
        # Pass HITL gate
        return orch.record_hitl(gate="post_plan", decision="continue")

    def test_hitl_continue_dispatches_first_task(self, orch):
        action = self._setup_generator_phase(orch)
        assert action["action"] == "dispatch_agent"
        assert action["role"] == "generator"
        assert "t1" in action["prompt"] or "Create handler" in action["prompt"]

    def test_generator_pass_advances_to_next_task(self, orch):
        self._setup_generator_phase(orch)
        status = "---HARNESS_STATUS---\nSTATUS: COMPLETE\nFEATURES_COMPLETED_THIS_SESSION: 1\n---END_HARNESS_STATUS---"
        action = orch.record(role="generator", output=status, task_id="t1", verdict="PASS")
        assert action["action"] == "dispatch_agent"
        assert action["role"] == "generator"
        # Should be task t2 now

    def test_all_tasks_complete_returns_complete(self, orch):
        self._setup_generator_phase(orch)
        orch.record(role="generator", output="done", task_id="t1", verdict="PASS")
        action = orch.record(role="generator", output="done", task_id="t2", verdict="PASS")
        assert action["action"] == "complete"

    def test_generator_fail_retries(self, orch):
        self._setup_generator_phase(orch)
        action = orch.record(role="generator", output="failed", task_id="t1", verdict="FAIL")
        assert action["action"] == "dispatch_agent"
        assert action["role"] == "generator"
        # Same task, retry

    def test_hitl_abort_returns_complete(self, orch):
        orch.init(prompt="test", detection={"stack": "typescript"})
        work_plan = {"phases": [{"id": "p0", "name": "P", "epics": [{"id": "e1", "name": "E",
            "stories": [{"id": "s1", "name": "S", "tasks": [
                {"id": "t1", "description": "X", "acceptance_criteria": ["ac"],
                 "steps": [], "depends_on": [], "target_files": ["x.ts"],
                 "status": "pending", "attempts": 0, "blocked_reason": None}
            ]}]}]}]}
        orch.record(role="architect", output=json.dumps(work_plan))
        orch.record(role="validator", output='{"valid": true}')
        action = orch.record_hitl(gate="post_plan", decision="abort")
        assert action["action"] == "complete"
        assert "abort" in action.get("reason", "").lower()


class TestCombineVerdicts:
    def test_combine_verdicts_all_pass(self):
        verdicts = [
            {"agent": "test-runner", "verdict": "PASS", "details": "10 passing"},
            {"agent": "code-reviewer", "verdict": "PASS", "details": "No issues"},
        ]
        result = Orchestrator.combine_verdicts(verdicts)
        assert result["verdict"] == "PASS"
        assert result["reasons"] == []

    def test_combine_verdicts_one_fail(self):
        verdicts = [
            {"agent": "test-runner", "verdict": "PASS", "details": "10 passing"},
            {"agent": "code-reviewer", "verdict": "FAIL", "details": "Security issue"},
        ]
        result = Orchestrator.combine_verdicts(verdicts)
        assert result["verdict"] == "FAIL"
        assert len(result["reasons"]) == 1
        assert "Security issue" in result["reasons"][0]

    def test_combine_verdicts_multiple_fail(self):
        verdicts = [
            {"agent": "test-runner", "verdict": "FAIL", "details": "2 failing"},
            {"agent": "code-reviewer", "verdict": "FAIL", "details": "Missing error handling"},
        ]
        result = Orchestrator.combine_verdicts(verdicts)
        assert result["verdict"] == "FAIL"
        assert len(result["reasons"]) == 2

    def test_combine_verdicts_empty_list(self):
        result = Orchestrator.combine_verdicts([])
        assert result["verdict"] == "PASS"


class TestScopedContext:
    def test_scoped_context_includes_task_and_deps(self, orch):
        """Scoped context includes the task and its dependency chain."""
        orch.init(prompt="test", detection={"stack": "typescript"})
        work_plan = {"phases": [{"id": "p0", "name": "P", "epics": [{"id": "e1", "name": "E",
            "stories": [{"id": "s1", "name": "S", "tasks": [
                {"id": "t1", "description": "Create handler", "acceptance_criteria": ["ac"],
                 "steps": [], "depends_on": [], "target_files": ["src/handler.ts"],
                 "status": "done", "attempts": 0, "blocked_reason": None},
                {"id": "t2", "description": "Add tests", "acceptance_criteria": ["ac"],
                 "steps": [], "depends_on": ["t1"], "target_files": ["tests/handler.test.ts"],
                 "status": "pending", "attempts": 0, "blocked_reason": None},
            ]}]}]}]}
        orch.record(role="architect", output=json.dumps(work_plan))
        orch.record(role="validator", output='{"valid": true}')
        orch.record_hitl(gate="post_plan", decision="continue")

        # t1 is done, so next task is t2 which depends on t1
        # The scoped context should include both t2 and t1
        task = orch._work_plan.get_task("t2")
        scoped = orch._build_scoped_context(task)
        assert "t1" in scoped
        assert "t2" in scoped
        assert "Create handler" in scoped

    def test_repo_map_injected_into_prompt(self, orch, tmp_path):
        """Repo map appears in the generated prompt."""
        # Create a project dir with a source file
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "src").mkdir()
        (project_dir / "src" / "app.ts").write_text("export function start() {}\n")
        orch.project_dir = project_dir

        orch.init(prompt="test", detection={"stack": "typescript"})
        work_plan = {"phases": [{"id": "p0", "name": "P", "epics": [{"id": "e1", "name": "E",
            "stories": [{"id": "s1", "name": "S", "tasks": [
                {"id": "t1", "description": "X", "acceptance_criteria": ["ac"],
                 "steps": [], "depends_on": [], "target_files": ["src/x.ts"],
                 "status": "pending", "attempts": 0, "blocked_reason": None}
            ]}]}]}]}
        orch.record(role="architect", output=json.dumps(work_plan))
        orch.record(role="validator", output='{"valid": true}')
        action = orch.record_hitl(gate="post_plan", decision="continue")

        # The generator prompt should contain the repo map with app.ts
        assert "app.ts" in action["prompt"]


class TestCircuitBreakerWiring:
    def _setup_and_get_to_generator(self, orch):
        orch.init(prompt="test", detection={"stack": "typescript"})
        work_plan = {"phases": [{"id": "p0", "name": "P", "epics": [{"id": "e1", "name": "E",
            "stories": [{"id": "s1", "name": "S", "tasks": [
                {"id": "t1", "description": "X", "acceptance_criteria": ["ac"],
                 "steps": [], "depends_on": [], "target_files": ["x.ts"],
                 "status": "pending", "attempts": 0, "blocked_reason": None}
            ]}]}]}]}
        orch.record(role="architect", output=json.dumps(work_plan))
        orch.record(role="validator", output='{"valid": true}')
        orch.record_hitl(gate="post_plan", decision="continue")

    def test_repeated_failures_trigger_circuit_break(self, orch):
        """After max retries on a task, it gets blocked."""
        self._setup_and_get_to_generator(orch)
        # Fail 3 times — should block the task
        orch.record(role="generator", output="fail", task_id="t1", verdict="FAIL")
        orch.record(role="generator", output="fail", task_id="t1", verdict="FAIL")
        action = orch.record(role="generator", output="fail", task_id="t1", verdict="FAIL")
        # After 3 failures, task is blocked, no more pending → complete
        assert action["action"] == "complete"


class TestCheckpoint:
    def test_checkpoint_config(self, orch):
        """Checkpoint threshold is configurable."""
        orch._config["checkpoint_every_n_tasks"] = 3
        assert orch._config.get("checkpoint_every_n_tasks") == 3


class TestScopeDrift:
    def test_scope_drift_detection(self, tmp_path):
        """Scope drift is detected when files_touched.txt has undeclared files."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        # Current task targets src/a.ts
        task = {"id": "t1", "target_files": ["src/a.ts"]}
        (run_dir / "current_task.json").write_text(json.dumps(task))
        # But src/b.ts was also touched
        (run_dir / "files_touched.txt").write_text("src/a.ts\nsrc/b.ts\n")

        from src.core.orchestrator import Orchestrator
        drift = Orchestrator._detect_scope_drift_static(run_dir, task)
        assert "src/b.ts" in drift

    def test_scope_drift_clean(self, tmp_path):
        """No drift when all touched files are declared."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        task = {"id": "t1", "target_files": ["src/a.ts", "src/b.ts"]}
        (run_dir / "files_touched.txt").write_text("src/a.ts\nsrc/b.ts\n")

        from src.core.orchestrator import Orchestrator
        drift = Orchestrator._detect_scope_drift_static(run_dir, task)
        assert drift == []


class TestOrchestratorStateRecovery:
    def test_resume_reconstructs_state(self, orch):
        """After init + some progress, a new Orchestrator can resume."""
        orch.init(prompt="test", detection={"stack": "python"})
        run_dir = orch.run_dir

        # Create new orchestrator pointing at same run
        orch2 = Orchestrator(
            data_dir=orch._data_dir,
            config=orch._config,
            prompts_dir=orch._prompts_dir,
            references_dir=orch._references_dir,
        )
        action = orch2.resume(run_dir=run_dir)
        # Should know we're in planner phase, waiting for architect output
        assert action is not None


class TestOrchestratorCLI:
    def test_sentinel_file_written(self, orch, tmp_path):
        orch.project_dir = tmp_path / "project"
        orch.project_dir.mkdir()
        orch.init(prompt="test", detection={"stack": "go"})
        sentinel = orch.project_dir / ".astra-active-run"
        assert sentinel.exists()
        assert str(orch.run_dir) in sentinel.read_text()

    def test_sentinel_file_deleted_on_completion(self, orch, tmp_path):
        orch.project_dir = tmp_path / "project"
        orch.project_dir.mkdir()
        orch.init(prompt="test", detection={"stack": "typescript"})
        # Small plan → architect → validator → hitl → complete
        work_plan = {"phases": [{"id": "p0", "name": "P", "epics": [{"id": "e1", "name": "E",
            "stories": [{"id": "s1", "name": "S", "tasks": [
                {"id": "t1", "description": "X", "acceptance_criteria": ["ac"],
                 "steps": [], "depends_on": [], "target_files": ["x.ts"],
                 "status": "pending", "attempts": 0, "blocked_reason": None}
            ]}]}]}]}
        orch.record(role="architect", output=json.dumps(work_plan))
        orch.record(role="validator", output='{"valid": true}')
        orch.record_hitl(gate="post_plan", decision="continue")
        orch.record(role="generator", output="done", task_id="t1", verdict="PASS")
        sentinel = orch.project_dir / ".astra-active-run"
        assert not sentinel.exists()
