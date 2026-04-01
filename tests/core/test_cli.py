"""Tests for orchestrator CLI entry point (__main__.py)."""

import json
import subprocess
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent.parent
PYTHON = str(PLUGIN_ROOT / ".venv" / "bin" / "python")


def run_cli(*args, cwd=None):
    """Run the orchestrator CLI and return parsed JSON output."""
    result = subprocess.run(
        [PYTHON, "-m", "src.core", *args],
        capture_output=True,
        text=True,
        cwd=str(cwd or PLUGIN_ROOT),
        timeout=10,
    )
    return result


class TestCLIInit:
    def test_init_returns_json(self, tmp_path):
        result = run_cli(
            "init",
            "--data-dir", str(tmp_path / ".astra"),
            "--prompt", "Add user auth",
            "--detection", '{"stack": "typescript", "test_command": "npm test"}',
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        action = json.loads(result.stdout)
        assert action["action"] == "dispatch_agent"
        assert action["role"] == "architect"

    def test_init_with_plan_skips_planner(self, tmp_path):
        plan = {
            "phases": [{"id": "p0", "name": "P", "epics": [{"id": "e1", "name": "E",
                "stories": [{"id": "s1", "name": "S", "tasks": [
                    {"id": "t1", "description": "X", "acceptance_criteria": ["ac"],
                     "steps": [], "depends_on": [], "target_files": ["x.ts"],
                     "status": "pending", "attempts": 0, "blocked_reason": None}
                ]}]}]}]
        }
        plan_path = tmp_path / "work_plan.json"
        plan_path.write_text(json.dumps(plan))

        result = run_cli(
            "init",
            "--data-dir", str(tmp_path / ".astra"),
            "--plan", str(plan_path),
            "--detection", '{"stack": "typescript"}',
        )
        assert result.returncode == 0
        action = json.loads(result.stdout)
        assert action["role"] == "generator"

    def test_init_returns_run_dir(self, tmp_path):
        result = run_cli(
            "init",
            "--data-dir", str(tmp_path / ".astra"),
            "--prompt", "test",
            "--detection", '{"stack": "python"}',
        )
        action = json.loads(result.stdout)
        assert "run_dir" in action
        run_dir = Path(action["run_dir"])
        assert run_dir.exists()

    def test_init_creates_state_file(self, tmp_path):
        result = run_cli(
            "init",
            "--data-dir", str(tmp_path / ".astra"),
            "--prompt", "test",
            "--detection", '{"stack": "python"}',
        )
        action = json.loads(result.stdout)
        run_dir = Path(action["run_dir"])
        state_file = run_dir / ".orchestrator_state.json"
        assert state_file.exists()

    def test_init_does_not_create_current_symlink(self, tmp_path):
        run_cli(
            "init",
            "--data-dir", str(tmp_path / ".astra"),
            "--prompt", "test",
            "--detection", '{"stack": "python"}',
        )
        assert not (tmp_path / ".astra" / "runs" / "current").exists()


class TestCLIRecord:
    def _init_and_get_run_dir(self, tmp_path):
        """Init and return run_dir path."""
        result = run_cli(
            "init",
            "--data-dir", str(tmp_path / ".astra"),
            "--prompt", "Build a todo app",
            "--detection", '{"stack": "typescript", "test_command": "npm test"}',
        )
        action = json.loads(result.stdout)
        return action["run_dir"]

    def test_record_returns_next_action(self, tmp_path):
        run_dir = self._init_and_get_run_dir(tmp_path)
        work_plan = {"phases": [{"id": "p0", "name": "P", "epics": [{"id": "e1", "name": "E",
            "stories": [{"id": "s1", "name": "S", "tasks": [
                {"id": f"t{i}", "description": f"Task {i}", "acceptance_criteria": ["ac"],
                 "steps": [], "depends_on": [], "target_files": [f"src/t{i}.ts"],
                 "status": "pending", "attempts": 0, "blocked_reason": None}
                for i in range(8)
            ]}]}]}]}

        result = run_cli(
            "record",
            "--data-dir", str(tmp_path / ".astra"),
            "--run-dir", run_dir,
            "--role", "architect",
            "--output", json.dumps(work_plan),
        )
        assert result.returncode == 0
        action = json.loads(result.stdout)
        assert action["action"] == "dispatch_agent"

    def test_record_with_task_verdict(self, tmp_path):
        run_dir = self._init_and_get_run_dir(tmp_path)
        work_plan = {"phases": [{"id": "p0", "name": "P", "epics": [{"id": "e1", "name": "E",
            "stories": [{"id": "s1", "name": "S", "tasks": [
                {"id": "t1", "description": "X", "acceptance_criteria": ["ac"],
                 "steps": [], "depends_on": [], "target_files": ["x.ts"],
                 "status": "pending", "attempts": 0, "blocked_reason": None}
            ]}]}]}]}
        run_cli("record", "--data-dir", str(tmp_path / ".astra"),
                "--run-dir", run_dir,
                "--role", "architect", "--output", json.dumps(work_plan))
        run_cli("record", "--data-dir", str(tmp_path / ".astra"),
                "--run-dir", run_dir,
                "--role", "validator", "--output", '{"valid": true}')
        run_cli("record-hitl", "--data-dir", str(tmp_path / ".astra"),
                "--run-dir", run_dir,
                "--gate", "post_plan", "--decision", "continue")

        result = run_cli(
            "record",
            "--data-dir", str(tmp_path / ".astra"),
            "--run-dir", run_dir,
            "--role", "generator",
            "--output", "done",
            "--task-id", "t1",
            "--verdict", "PASS",
        )
        assert result.returncode == 0
        action = json.loads(result.stdout)
        assert action["action"] == "complete"


class TestCLIRecordHitl:
    def test_record_hitl_continue(self, tmp_path):
        result = run_cli("init", "--data-dir", str(tmp_path / ".astra"),
                "--prompt", "test", "--detection", '{"stack": "python"}')
        run_dir = json.loads(result.stdout)["run_dir"]

        work_plan = {"phases": [{"id": "p0", "name": "P", "epics": [{"id": "e1", "name": "E",
            "stories": [{"id": "s1", "name": "S", "tasks": [
                {"id": "t1", "description": "X", "acceptance_criteria": ["ac"],
                 "steps": [], "depends_on": [], "target_files": ["x.py"],
                 "status": "pending", "attempts": 0, "blocked_reason": None}
            ]}]}]}]}
        run_cli("record", "--data-dir", str(tmp_path / ".astra"),
                "--run-dir", run_dir,
                "--role", "architect", "--output", json.dumps(work_plan))
        run_cli("record", "--data-dir", str(tmp_path / ".astra"),
                "--run-dir", run_dir,
                "--role", "validator", "--output", '{"valid": true}')

        result = run_cli(
            "record-hitl",
            "--data-dir", str(tmp_path / ".astra"),
            "--run-dir", run_dir,
            "--gate", "post_plan",
            "--decision", "continue",
        )
        assert result.returncode == 0
        action = json.loads(result.stdout)
        assert action["action"] == "dispatch_agent"
        assert action["role"] == "generator"

    def test_record_hitl_abort(self, tmp_path):
        result = run_cli("init", "--data-dir", str(tmp_path / ".astra"),
                "--prompt", "test", "--detection", '{"stack": "go"}')
        run_dir = json.loads(result.stdout)["run_dir"]

        work_plan = {"phases": [{"id": "p0", "name": "P", "epics": [{"id": "e1", "name": "E",
            "stories": [{"id": "s1", "name": "S", "tasks": [
                {"id": "t1", "description": "X", "acceptance_criteria": ["ac"],
                 "steps": [], "depends_on": [], "target_files": ["main.go"],
                 "status": "pending", "attempts": 0, "blocked_reason": None}
            ]}]}]}]}
        run_cli("record", "--data-dir", str(tmp_path / ".astra"),
                "--run-dir", run_dir,
                "--role", "architect", "--output", json.dumps(work_plan))
        run_cli("record", "--data-dir", str(tmp_path / ".astra"),
                "--run-dir", run_dir,
                "--role", "validator", "--output", '{"valid": true}')

        result = run_cli(
            "record-hitl",
            "--data-dir", str(tmp_path / ".astra"),
            "--run-dir", run_dir,
            "--gate", "post_plan",
            "--decision", "abort",
        )
        assert result.returncode == 0
        action = json.loads(result.stdout)
        assert action["action"] == "complete"


class TestCLIErrors:
    def test_unknown_command(self):
        result = run_cli("nonexistent")
        assert result.returncode != 0

    def test_missing_required_args(self):
        result = run_cli("init")
        assert result.returncode != 0
