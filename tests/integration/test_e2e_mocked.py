"""E2E tests with mocked Agent dispatch — tests the full orchestrator flow."""

import json
from pathlib import Path

import pytest

from src.core.orchestrator import Orchestrator

PROMPTS_DIR = Path(__file__).parent.parent.parent / "src" / "prompts"
REFERENCES_DIR = Path(__file__).parent.parent.parent / "references"
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _make_orch(tmp_path):
    config = {
        "strategy": "feature",
        "model_routing": {"planner": "opus", "generator": "sonnet", "evaluator": "haiku"},
        "pipeline_depth": {"light_max_tasks": 5, "full_min_tasks": 20},
        "hitl": {"post_plan": True},
        "max_cost_usd": 10.0,
    }
    return Orchestrator(
        data_dir=tmp_path / ".astra",
        config=config,
        prompts_dir=PROMPTS_DIR,
        references_dir=REFERENCES_DIR,
    )


class TestFullPlannerToGeneratorFlow:
    def test_planner_pipeline_with_mocked_agents(self, tmp_path):
        """Full flow: init → architect → validator → hitl → generator → complete."""
        orch = _make_orch(tmp_path)

        # Step 1: Init
        action = orch.init(prompt="Add a counter", detection={"stack": "typescript"})
        assert action["action"] == "dispatch_agent"
        assert action["role"] == "architect"

        # Step 2: Architect produces a small plan (light depth → skip adversary/refiner)
        plan = json.loads((FIXTURES_DIR / "sample_work_plan.json").read_text())
        action = orch.record(role="architect", output=json.dumps(plan))
        assert action["role"] == "validator"  # light depth: 2 tasks

        # Step 3: Validator approves
        action = orch.record(role="validator", output='{"valid": true, "issues": []}')
        assert action["action"] == "hitl_gate"
        assert action["gate"] == "post_plan"

        # Step 4: HITL continue
        action = orch.record_hitl(gate="post_plan", decision="continue")
        assert action["action"] == "dispatch_agent"
        assert action["role"] == "generator"
        assert action["task_id"] == "task-001"

        # Step 5: Generator completes task 1
        action = orch.record(role="generator", output="done", task_id="task-001", verdict="PASS")
        assert action["action"] == "dispatch_agent"
        assert action["role"] == "generator"

        # Step 6: Generator completes task 2
        action = orch.record(role="generator", output="done", task_id="task-002", verdict="PASS")
        assert action["action"] == "complete"

    def test_generator_loop_with_retry(self, tmp_path):
        """Generator fails once, retries, then passes."""
        orch = _make_orch(tmp_path)
        plan = json.loads((FIXTURES_DIR / "sample_work_plan.json").read_text())

        orch.init(prompt="test", detection={"stack": "typescript"})
        orch.record(role="architect", output=json.dumps(plan))
        orch.record(role="validator", output='{"valid": true}')
        orch.record_hitl(gate="post_plan", decision="continue")

        # Fail once
        action = orch.record(role="generator", output="error", task_id="task-001", verdict="FAIL")
        assert action["action"] == "dispatch_agent"
        assert action["role"] == "generator"  # retry

        # Pass on retry
        action = orch.record(role="generator", output="ok", task_id="task-001", verdict="PASS")
        assert action["action"] == "dispatch_agent"  # next task

    def test_resume_from_event_log(self, tmp_path):
        """Resume reconstructs state from events.jsonl."""
        orch = _make_orch(tmp_path)
        plan = json.loads((FIXTURES_DIR / "sample_work_plan.json").read_text())

        orch.init(prompt="test", detection={"stack": "typescript"})
        orch.record(role="architect", output=json.dumps(plan))
        orch.record(role="validator", output='{"valid": true}')
        orch.record_hitl(gate="post_plan", decision="continue")
        orch.record(role="generator", output="done", task_id="task-001", verdict="PASS")

        run_dir = orch.run_dir

        # New orchestrator resumes
        orch2 = _make_orch(tmp_path)
        action = orch2.resume(run_dir=run_dir)
        assert action is not None

    def test_plan_input_skips_planner(self, tmp_path):
        """--plan flag skips planner entirely."""
        orch = _make_orch(tmp_path)
        plan_path = FIXTURES_DIR / "sample_work_plan.json"

        action = orch.init(plan_path=str(plan_path), detection={"stack": "typescript"})
        assert action["action"] == "dispatch_agent"
        assert action["role"] == "generator"
        assert action["task_id"] == "task-001"
