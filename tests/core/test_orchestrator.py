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
        assert "prompt_file" in action
        prompt_content = Path(action["prompt_file"]).read_text()
        assert "Add user auth" in prompt_content
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

    def test_init_no_sentinel_file(self, orch, tmp_path):
        orch.project_dir = tmp_path / "project"
        orch.project_dir.mkdir()
        orch.init(prompt="test", detection={"stack": "python"})
        sentinel = orch.project_dir / ".astra-active-run"
        assert not sentinel.exists()


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
        prompt_content = Path(action["prompt_file"]).read_text()
        assert "t1" in prompt_content or "Create handler" in prompt_content

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

    def test_verdict_case_insensitive(self, orch):
        """Lowercase/mixed-case verdicts are normalized to uppercase."""
        self._setup_generator_phase(orch)
        action = orch.record(role="generator", output="done", task_id="t1", verdict="pass")
        # Should advance to t2, not loop on t1
        assert action["action"] == "dispatch_agent"
        assert action["role"] == "generator"
        # t1 should be done
        assert orch._work_plan.get_task("t1")["status"] == "done"

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


class TestEvaluatorDispatch:
    def _setup_with_evaluators(self, orch):
        """Get orchestrator to generator phase with evaluators configured."""
        orch._config["evaluators"] = ["test-runner", "code-reviewer"]
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
        return orch.record_hitl(gate="post_plan", decision="continue")

    def test_generator_pass_dispatches_test_runner(self, orch):
        self._setup_with_evaluators(orch)
        action = orch.record(role="generator", output="done", task_id="t1", verdict="PASS")
        assert action["action"] == "dispatch_agent"
        assert action["role"] == "test-runner"

    def test_all_evaluators_pass_advances(self, orch):
        self._setup_with_evaluators(orch)
        orch.record(role="generator", output="done", task_id="t1", verdict="PASS")
        orch.record(role="test-runner", output="10 passing", task_id="t1", verdict="PASS")
        action = orch.record(role="code-reviewer", output="no issues", task_id="t1", verdict="PASS")
        # All evaluators passed → advance to next task
        assert action["action"] == "dispatch_agent"
        assert action["role"] == "generator"

    def test_evaluator_fail_writes_feedback_and_retries(self, orch):
        self._setup_with_evaluators(orch)
        orch.record(role="generator", output="done", task_id="t1", verdict="PASS")
        action = orch.record(
            role="test-runner", output="2 failing: TypeError in handler.ts",
            task_id="t1", verdict="FAIL",
        )
        # First evaluator failed → skip remaining evaluators, write feedback, retry generator
        assert action["action"] == "dispatch_agent"
        assert action["role"] == "generator"
        feedback_path = orch.run_dir / "tasks" / "t1" / "feedback.md"
        assert feedback_path.exists()
        assert "test-runner" in feedback_path.read_text()


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


class TestParallelDispatch:
    def _make_parallel_plan(self):
        """Work plan with 3 independent tasks (no deps)."""
        return {"phases": [{"id": "p0", "name": "P", "epics": [{"id": "e1", "name": "E",
            "stories": [{"id": "s1", "name": "S", "tasks": [
                {"id": "t1", "description": "Add auth module", "acceptance_criteria": ["ac"],
                 "steps": [], "depends_on": [], "target_files": ["a.ts"],
                 "status": "pending", "attempts": 0, "blocked_reason": None},
                {"id": "t2", "description": "Add logging module", "acceptance_criteria": ["ac"],
                 "steps": [], "depends_on": [], "target_files": ["b.ts"],
                 "status": "pending", "attempts": 0, "blocked_reason": None},
                {"id": "t3", "description": "Add config module", "acceptance_criteria": ["ac"],
                 "steps": [], "depends_on": [], "target_files": ["c.ts"],
                 "status": "pending", "attempts": 0, "blocked_reason": None},
            ]}]}]}]}

    def test_parallel_config_respected(self, orch):
        """Parallel config is accessible."""
        orch._config["parallel"] = {"enabled": True, "max_workers": 3}
        assert orch._config["parallel"]["enabled"] is True
        assert orch._config["parallel"]["max_workers"] == 3

    def test_sequential_when_parallel_disabled(self, orch):
        """Default config has parallel disabled → sequential dispatch."""
        orch._config["parallel"] = {"enabled": False}
        orch.init(prompt="test", detection={"stack": "typescript"})
        orch.record(role="architect", output=json.dumps(self._make_parallel_plan()))
        orch.record(role="validator", output='{"valid": true}')
        action = orch.record_hitl(gate="post_plan", decision="continue")
        # Sequential: dispatches one task at a time
        assert action["action"] == "dispatch_agent"
        assert action["role"] == "generator"

    def test_batch_dispatch_when_parallel_enabled(self, orch):
        """Parallel enabled + multiple independent tasks → dispatch_batch."""
        orch._config["parallel"] = {"enabled": True, "max_workers": 3}
        orch.init(prompt="test", detection={"stack": "typescript"})
        orch.record(role="architect", output=json.dumps(self._make_parallel_plan()))
        orch.record(role="validator", output='{"valid": true}')
        action = orch.record_hitl(gate="post_plan", decision="continue")
        assert action["action"] == "dispatch_batch"
        assert len(action["agents"]) == 3
        task_ids = {a["task_id"] for a in action["agents"]}
        assert task_ids == {"t1", "t2", "t3"}

    def test_batch_respects_max_workers(self, orch):
        """Batch size is capped by max_workers."""
        orch._config["parallel"] = {"enabled": True, "max_workers": 2}
        orch.init(prompt="test", detection={"stack": "typescript"})
        orch.record(role="architect", output=json.dumps(self._make_parallel_plan()))
        orch.record(role="validator", output='{"valid": true}')
        action = orch.record_hitl(gate="post_plan", decision="continue")
        assert action["action"] == "dispatch_batch"
        assert len(action["agents"]) == 2

    def test_batch_agents_have_prompt_files(self, orch):
        """Each agent in a batch has a prompt_file on disk."""
        orch._config["parallel"] = {"enabled": True, "max_workers": 3}
        orch.init(prompt="test", detection={"stack": "typescript"})
        orch.record(role="architect", output=json.dumps(self._make_parallel_plan()))
        orch.record(role="validator", output='{"valid": true}')
        action = orch.record_hitl(gate="post_plan", decision="continue")
        for agent in action["agents"]:
            assert Path(agent["prompt_file"]).exists()

    def test_batch_falls_back_to_single_when_one_ready(self, orch):
        """Parallel enabled but only 1 task ready → dispatch_agent, not batch."""
        orch._config["parallel"] = {"enabled": True, "max_workers": 3}
        plan = {"phases": [{"id": "p0", "name": "P", "epics": [{"id": "e1", "name": "E",
            "stories": [{"id": "s1", "name": "S", "tasks": [
                {"id": "t1", "description": "Add base", "acceptance_criteria": ["ac"],
                 "steps": [], "depends_on": [], "target_files": ["a.ts"],
                 "status": "pending", "attempts": 0, "blocked_reason": None},
                {"id": "t2", "description": "Add extension", "acceptance_criteria": ["ac"],
                 "steps": [], "depends_on": ["t1"], "target_files": ["b.ts"],
                 "status": "pending", "attempts": 0, "blocked_reason": None},
            ]}]}]}]}
        orch.init(prompt="test", detection={"stack": "typescript"})
        orch.record(role="architect", output=json.dumps(plan))
        orch.record(role="validator", output='{"valid": true}')
        action = orch.record_hitl(gate="post_plan", decision="continue")
        # Only t1 is ready (t2 depends on t1), so single dispatch
        assert action["action"] == "dispatch_agent"
        assert action["task_id"] == "t1"

    def test_sequential_after_parallel_batch(self, orch):
        """After batch completes, orchestrator continues normally."""
        orch._config["parallel"] = {"enabled": True, "max_workers": 3}
        orch.init(prompt="test", detection={"stack": "typescript"})
        orch.record(role="architect", output=json.dumps(self._make_parallel_plan()))
        orch.record(role="validator", output='{"valid": true}')
        orch.record_hitl(gate="post_plan", decision="continue")
        # Record all 3 tasks as PASS
        orch.record(role="generator", output="done", task_id="t1", verdict="PASS")
        orch.record(role="generator", output="done", task_id="t2", verdict="PASS")
        action = orch.record(role="generator", output="done", task_id="t3", verdict="PASS")
        assert action["action"] == "complete"


class TestWorktreeIsolation:
    def _setup_and_dispatch(self, orch, task_description="Create auth handler"):
        """Get to generator dispatch with a given task description."""
        orch.init(prompt="test", detection={"stack": "typescript"})
        work_plan = {"phases": [{"id": "p0", "name": "P", "epics": [{"id": "e1", "name": "E",
            "stories": [{"id": "s1", "name": "S", "tasks": [
                {"id": "t1", "description": task_description, "acceptance_criteria": ["ac"],
                 "steps": [], "depends_on": [], "target_files": ["src/handler.ts"],
                 "status": "pending", "attempts": 0, "blocked_reason": None},
            ]}]}]}]}
        orch.record(role="architect", output=json.dumps(work_plan))
        orch.record(role="validator", output='{"valid": true}')
        return orch.record_hitl(gate="post_plan", decision="continue")

    def test_write_heavy_task_gets_worktree_isolation(self, orch):
        """Tasks that modify files get isolation: worktree."""
        action = self._setup_and_dispatch(orch, "Create auth handler")
        assert action["action"] == "dispatch_agent"
        assert action.get("isolation") == "worktree"

    def test_read_only_task_no_isolation(self, orch):
        """Tasks with read-only keywords don't get worktree isolation."""
        action = self._setup_and_dispatch(orch, "Review and validate the auth module")
        assert action["action"] == "dispatch_agent"
        assert "isolation" not in action

    def test_batch_agents_have_isolation(self, orch):
        """Batch dispatch also passes isolation hints per agent."""
        orch._config["parallel"] = {"enabled": True, "max_workers": 3}
        orch.init(prompt="test", detection={"stack": "typescript"})
        work_plan = {"phases": [{"id": "p0", "name": "P", "epics": [{"id": "e1", "name": "E",
            "stories": [{"id": "s1", "name": "S", "tasks": [
                {"id": "t1", "description": "Add auth module", "acceptance_criteria": ["ac"],
                 "steps": [], "depends_on": [], "target_files": ["a.ts"],
                 "status": "pending", "attempts": 0, "blocked_reason": None},
                {"id": "t2", "description": "Add logging module", "acceptance_criteria": ["ac"],
                 "steps": [], "depends_on": [], "target_files": ["b.ts"],
                 "status": "pending", "attempts": 0, "blocked_reason": None},
            ]}]}]}]}
        orch.record(role="architect", output=json.dumps(work_plan))
        orch.record(role="validator", output='{"valid": true}')
        action = orch.record_hitl(gate="post_plan", decision="continue")
        assert action["action"] == "dispatch_batch"
        for agent in action["agents"]:
            assert agent.get("isolation") == "worktree"


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

    def test_file_tree_injected_into_architect_prompt(self, orch, tmp_path):
        """Architect gets compact file tree (paths only, no definitions)."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "src").mkdir()
        (project_dir / "src" / "app.ts").write_text("export function start() {}\n")
        orch.project_dir = project_dir

        action = orch.init(prompt="test", detection={"stack": "typescript"})
        # Architect prompt should contain the file path
        prompt_content = Path(action["prompt_file"]).read_text()
        assert "app.ts" in prompt_content

    def test_generator_prompt_has_no_repo_map(self, orch, tmp_path):
        """Generator discovers files with tools — no repo map injected."""
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

        prompt_content = Path(action["prompt_file"]).read_text()
        # Generator should NOT have the repo map, but should have the task
        assert "app.ts" not in prompt_content
        assert "src/x.ts" in prompt_content  # from target_files in the task


class TestDynamicContext:
    def _setup_two_task_plan(self, orch):
        """Set up a plan where t2 depends on t1."""
        orch.init(prompt="test", detection={"stack": "typescript"})
        work_plan = {"phases": [{"id": "p0", "name": "P", "epics": [{"id": "e1", "name": "E",
            "stories": [{"id": "s1", "name": "S", "tasks": [
                {"id": "t1", "description": "Create auth handler", "acceptance_criteria": ["ac"],
                 "steps": [], "depends_on": [], "target_files": ["src/auth.ts"],
                 "status": "pending", "attempts": 0, "blocked_reason": None},
                {"id": "t2", "description": "Add auth tests", "acceptance_criteria": ["ac"],
                 "steps": [], "depends_on": ["t1"], "target_files": ["tests/auth.test.ts"],
                 "status": "pending", "attempts": 0, "blocked_reason": None},
            ]}]}]}]}
        orch.record(role="architect", output=json.dumps(work_plan))
        orch.record(role="validator", output='{"valid": true}')
        return orch.record_hitl(gate="post_plan", decision="continue")

    def test_context_files_from_completed_dependency(self, orch):
        """t2 gets t1's target_files as context after t1 completes."""
        self._setup_two_task_plan(orch)
        # Complete t1 with FILES_MODIFIED
        status = "---HARNESS_STATUS---\nSTATUS: COMPLETE\nFILES_MODIFIED: src/auth.ts, src/types.ts\n---END_HARNESS_STATUS---"
        action = orch.record(role="generator", output=status, task_id="t1", verdict="PASS")
        # t2's prompt should reference t1's modified files as context
        prompt_content = Path(action["prompt_file"]).read_text()
        assert "src/auth.ts" in prompt_content
        assert "src/types.ts" in prompt_content

    def test_no_context_files_for_root_task(self, orch):
        """Root task (no deps) gets no context_files."""
        self._setup_two_task_plan(orch)
        # t1 has no deps, so _compute_context_files returns empty
        task = orch._work_plan.get_task("t1")
        context = orch._compute_context_files(task)
        assert context == []

    def test_context_excludes_own_target_files(self, orch):
        """Context files don't include the task's own target_files."""
        self._setup_two_task_plan(orch)
        # Complete t1 — its target is src/auth.ts
        status = "---HARNESS_STATUS---\nSTATUS: COMPLETE\nFILES_MODIFIED: src/auth.ts\n---END_HARNESS_STATUS---"
        orch.record(role="generator", output=status, task_id="t1", verdict="PASS")
        # If t2 also targeted src/auth.ts, it should be excluded
        # But t2 targets tests/auth.test.ts, so src/auth.ts IS context
        task = orch._work_plan.get_task("t2")
        context = orch._compute_context_files(task)
        assert "src/auth.ts" in context
        assert "tests/auth.test.ts" not in context


class TestCircuitBreakerWiring:
    def _setup_and_get_to_generator(self, orch, num_tasks=1):
        orch.init(prompt="test", detection={"stack": "typescript"})
        tasks = [
            {"id": f"t{i}", "description": f"Task {i}", "acceptance_criteria": ["ac"],
             "steps": [], "depends_on": [], "target_files": [f"t{i}.ts"],
             "status": "pending", "attempts": 0, "blocked_reason": None}
            for i in range(1, num_tasks + 1)
        ]
        work_plan = {"phases": [{"id": "p0", "name": "P", "epics": [{"id": "e1", "name": "E",
            "stories": [{"id": "s1", "name": "S", "tasks": tasks}]}]}]}
        orch.record(role="architect", output=json.dumps(work_plan))
        orch.record(role="validator", output='{"valid": true}')
        orch.record_hitl(gate="post_plan", decision="continue")

    def test_repeated_failures_trigger_circuit_break(self, orch):
        """After max retries on a task, it gets blocked."""
        orch._config["circuit_breaker"] = {"no_progress_threshold": 10, "same_error_threshold": 10}
        self._setup_and_get_to_generator(orch)
        # Fail 3 times — should block the task
        orch.record(role="generator", output="fail", task_id="t1", verdict="FAIL")
        orch.record(role="generator", output="fail", task_id="t1", verdict="FAIL")
        action = orch.record(role="generator", output="fail", task_id="t1", verdict="FAIL")
        # After 3 failures, task is blocked, no more pending → complete
        assert action["action"] == "complete"

    def test_circuit_breaker_opens_returns_hitl_gate(self, orch):
        """CircuitBreaker opens after repeated no-progress iterations → HITL gate."""
        orch._config["circuit_breaker"] = {"no_progress_threshold": 2}
        self._setup_and_get_to_generator(orch, num_tasks=5)
        # Generator FAIL records no-progress in circuit breaker
        orch.record(role="generator", output="fail", task_id="t1", verdict="FAIL")
        action = orch.record(role="generator", output="fail", task_id="t1", verdict="FAIL")
        # Circuit breaker should open after 2 no-progress, returning HITL gate
        assert action["action"] == "hitl_gate"
        assert action["gate"] == "on_circuit_break"

    def test_on_circuit_break_continue_resets(self, orch):
        """Continuing from circuit break gate resets the breaker and continues."""
        orch._config["circuit_breaker"] = {"no_progress_threshold": 2}
        self._setup_and_get_to_generator(orch, num_tasks=5)
        orch.record(role="generator", output="fail", task_id="t1", verdict="FAIL")
        orch.record(role="generator", output="fail", task_id="t1", verdict="FAIL")
        # Now continue past the circuit break
        action = orch.record_hitl(gate="on_circuit_break", decision="continue")
        assert action["action"] == "dispatch_agent"


class TestBudgetTimeIterationChecks:
    def _setup_generator(self, orch, num_tasks=3):
        orch.init(prompt="test", detection={"stack": "typescript"})
        tasks = [
            {"id": f"t{i}", "description": f"Task {i}", "acceptance_criteria": ["ac"],
             "steps": [], "depends_on": [], "target_files": [f"t{i}.ts"],
             "status": "pending", "attempts": 0, "blocked_reason": None}
            for i in range(1, num_tasks + 1)
        ]
        work_plan = {"phases": [{"id": "p0", "name": "P", "epics": [{"id": "e1", "name": "E",
            "stories": [{"id": "s1", "name": "S", "tasks": tasks}]}]}]}
        orch.record(role="architect", output=json.dumps(work_plan))
        orch.record(role="validator", output='{"valid": true}')
        orch.record_hitl(gate="post_plan", decision="continue")

    def test_iteration_limit_triggers_hitl(self, orch):
        orch._config["max_iterations"] = 2
        self._setup_generator(orch)
        orch.record(role="generator", output="done", task_id="t1", verdict="PASS")
        action = orch.record(role="generator", output="done", task_id="t2", verdict="PASS")
        # After 2 iterations, should hit budget_warning gate
        assert action["action"] == "hitl_gate"
        assert action["gate"] == "budget_warning"

    def test_status_block_parsed(self, orch):
        self._setup_generator(orch)
        status = "---HARNESS_STATUS---\nSTATUS: COMPLETE\nFEATURES_COMPLETED_THIS_SESSION: 2\nFEATURES_REMAINING: 1\n---END_HARNESS_STATUS---"
        orch.record(role="generator", output=status, task_id="t1", verdict="PASS")
        # Check that status was parsed and stored in events
        events = orch._store.replay()
        status_events = [e for e in events if e.get("type") == "status_block_parsed"]
        assert len(status_events) == 1
        assert status_events[0]["data"]["FEATURES_COMPLETED_THIS_SESSION"] == 2

    def test_time_limit_check(self, orch):
        orch._config["max_duration_minutes"] = 1  # 1 minute limit
        self._setup_generator(orch)
        # Force start_time to be 2 minutes in the past (exceeds 1min limit)
        orch._start_time = time.time() - 120
        action = orch.record(role="generator", output="done", task_id="t1", verdict="PASS")
        assert action["action"] == "hitl_gate"
        assert action["gate"] == "budget_warning"


class TestCheckpoint:
    def test_checkpoint_config(self, orch):
        """Checkpoint threshold is configurable."""
        orch._config["checkpoint_every_n_tasks"] = 3
        assert orch._config.get("checkpoint_every_n_tasks") == 3

    def test_checkpoint_after_n_tasks(self, orch):
        """Checkpoint fires after completing N tasks in one session."""
        orch._config["checkpoint_every_n_tasks"] = 2
        orch.init(prompt="test", detection={"stack": "typescript"})
        tasks = [
            {"id": f"t{i}", "description": f"Task {i}", "acceptance_criteria": ["ac"],
             "steps": [], "depends_on": [], "target_files": [f"t{i}.ts"],
             "status": "pending", "attempts": 0, "blocked_reason": None}
            for i in range(1, 6)
        ]
        work_plan = {"phases": [{"id": "p0", "name": "P", "epics": [{"id": "e1", "name": "E",
            "stories": [{"id": "s1", "name": "S", "tasks": tasks}]}]}]}
        orch.record(role="architect", output=json.dumps(work_plan))
        orch.record(role="validator", output='{"valid": true}')
        orch.record_hitl(gate="post_plan", decision="continue")
        # Complete 2 tasks → should checkpoint
        orch.record(role="generator", output="done", task_id="t1", verdict="PASS")
        action = orch.record(role="generator", output="done", task_id="t2", verdict="PASS")
        assert action["action"] == "checkpoint"
        assert "summary" in action

    def test_resume_after_checkpoint_continues(self, orch):
        """After checkpoint, resume picks up where we left off."""
        orch._config["checkpoint_every_n_tasks"] = 2
        orch.init(prompt="test", detection={"stack": "typescript"})
        tasks = [
            {"id": f"t{i}", "description": f"Task {i}", "acceptance_criteria": ["ac"],
             "steps": [], "depends_on": [], "target_files": [f"t{i}.ts"],
             "status": "pending", "attempts": 0, "blocked_reason": None}
            for i in range(1, 6)
        ]
        work_plan = {"phases": [{"id": "p0", "name": "P", "epics": [{"id": "e1", "name": "E",
            "stories": [{"id": "s1", "name": "S", "tasks": tasks}]}]}]}
        orch.record(role="architect", output=json.dumps(work_plan))
        orch.record(role="validator", output='{"valid": true}')
        orch.record_hitl(gate="post_plan", decision="continue")
        orch.record(role="generator", output="done", task_id="t1", verdict="PASS")
        orch.record(role="generator", output="done", task_id="t2", verdict="PASS")
        # Checkpoint returned → resume
        run_dir = orch.run_dir
        orch2 = Orchestrator(
            data_dir=orch._data_dir, config=orch._config,
            prompts_dir=orch._prompts_dir, references_dir=orch._references_dir,
        )
        action = orch2.resume(run_dir=run_dir)
        # Should dispatch generator for next pending task
        assert action["action"] == "dispatch_agent"
        assert action["role"] == "generator"


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


class TestPromptFileDispatch:
    def test_planner_action_has_prompt_file(self, orch):
        action = orch.init(prompt="Add auth", detection={"stack": "typescript"})
        assert "prompt_file" in action
        assert action["prompt_file"].endswith(".md")

    def test_generator_action_has_prompt_file(self, orch):
        orch.init(prompt="test", detection={"stack": "typescript"})
        work_plan = {"phases": [{"id": "p0", "name": "P", "epics": [{"id": "e1", "name": "E",
            "stories": [{"id": "s1", "name": "S", "tasks": [
                {"id": "t1", "description": "Do X", "acceptance_criteria": ["ac"],
                 "steps": [], "depends_on": [], "target_files": ["src/x.ts"],
                 "status": "pending", "attempts": 0, "blocked_reason": None}
            ]}]}]}]}
        orch.record(role="architect", output=json.dumps(work_plan))
        orch.record(role="validator", output='{"valid": true}')
        action = orch.record_hitl(gate="post_plan", decision="continue")
        assert action["role"] == "generator"
        assert "prompt_file" in action
        assert "tasks/t1/prompt.md" in action["prompt_file"]

    def test_prompt_file_exists_on_disk(self, orch):
        action = orch.init(prompt="Add auth", detection={"stack": "typescript"})
        prompt_file = Path(action["prompt_file"])
        assert prompt_file.exists()
        content = prompt_file.read_text()
        assert len(content) > 0


class TestSpecCompliance:
    def test_bugfix_strategy_sequence(self, orch):
        """Bugfix strategy produces investigator → bugfix-adversary → fixer → verifier."""
        orch._config["strategy"] = "bugfix"
        action = orch.init(prompt="Fix crash on login", detection={"stack": "typescript"})
        assert action["role"] == "investigator"

    def test_per_role_model_override(self, orch):
        """Per-role model override in config takes precedence."""
        orch._config["role_models"] = {"architect": "haiku"}
        action = orch.init(prompt="test", detection={"stack": "typescript"})
        assert action["role"] == "architect"
        assert action["model"] == "haiku"

    def test_headless_skips_hitl(self, orch, monkeypatch):
        """In headless mode, HITL gates are skipped."""
        monkeypatch.setenv("ASTRA_HEADLESS", "1")
        orch.init(prompt="test", detection={"stack": "typescript"})
        work_plan = {"phases": [{"id": "p0", "name": "P", "epics": [{"id": "e1", "name": "E",
            "stories": [{"id": "s1", "name": "S", "tasks": [
                {"id": "t1", "description": "Do X", "acceptance_criteria": ["ac"],
                 "steps": [], "depends_on": [], "target_files": ["src/x.ts"],
                 "status": "pending", "attempts": 0, "blocked_reason": None}
            ]}]}]}]}
        orch.record(role="architect", output=json.dumps(work_plan))
        action = orch.record(role="validator", output='{"valid": true}')
        # Should skip post_plan HITL gate and go straight to generator
        assert action["action"] == "dispatch_agent"
        assert action["role"] == "generator"


class TestOrchestratorCLI:
    def test_no_sentinel_file_on_init(self, orch, tmp_path):
        orch.project_dir = tmp_path / "project"
        orch.project_dir.mkdir()
        orch.init(prompt="test", detection={"stack": "go"})
        sentinel = orch.project_dir / ".astra-active-run"
        assert not sentinel.exists()
