"""Tests for hook shell scripts via subprocess with piped JSON input."""

import json
import os
import subprocess
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).parent.parent.parent / "src" / "hooks"
ASSETS_DIR = Path(__file__).parent.parent.parent / "src" / "assets"


def run_hook(script_path, stdin_json, env_extras=None):
    """Run a hook script with JSON piped to stdin."""
    env = os.environ.copy()
    env["PROJECT_DIR"] = env.get("PROJECT_DIR", "/tmp/nonexistent")
    if env_extras:
        env.update(env_extras)

    result = subprocess.run(
        ["bash", str(script_path)],
        input=json.dumps(stdin_json),
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    return result


class TestAutoFixDepsSh:
    def test_noop_without_sentinel(self, tmp_path):
        """Exits 0 when no .astra-active-run sentinel file exists."""
        result = run_hook(
            HOOKS_DIR / "auto_fix_deps.sh",
            {"file_path": "/some/work_plan.json"},
            env_extras={"PROJECT_DIR": str(tmp_path)},
        )
        assert result.returncode == 0

    def test_noop_for_non_workplan_file(self, tmp_path):
        """Exits 0 when the modified file is not a work_plan."""
        run_dir = tmp_path / "runs" / "001"
        run_dir.mkdir(parents=True)
        sentinel = tmp_path / ".astra-active-run"
        sentinel.write_text(str(run_dir))

        result = run_hook(
            HOOKS_DIR / "auto_fix_deps.sh",
            {"file_path": "/some/other/file.py"},
            env_extras={"PROJECT_DIR": str(tmp_path)},
        )
        assert result.returncode == 0

    def test_runs_python_for_workplan(self, tmp_path):
        """Attempts to run auto_fix_deps.py when file is a work_plan (exit 0 even if missing)."""
        run_dir = tmp_path / "runs" / "001"
        run_dir.mkdir(parents=True)
        sentinel = tmp_path / ".astra-active-run"
        sentinel.write_text(str(run_dir))

        result = run_hook(
            HOOKS_DIR / "auto_fix_deps.sh",
            {"file_path": str(tmp_path / "work_plan.json")},
            env_extras={"PROJECT_DIR": str(tmp_path)},
        )
        # Should exit 0 even if python script fails (|| true in script)
        assert result.returncode == 0


class TestTrackFilesTouchedSh:
    def test_appends_path(self, tmp_path):
        """Appends file_path to files_touched.txt in run dir."""
        run_dir = tmp_path / "runs" / "001"
        run_dir.mkdir(parents=True)
        sentinel = tmp_path / ".astra-active-run"
        sentinel.write_text(str(run_dir))

        result = run_hook(
            HOOKS_DIR / "track_files_touched.sh",
            {"file_path": "/project/src/index.ts"},
            env_extras={"PROJECT_DIR": str(tmp_path)},
        )
        assert result.returncode == 0

        touched_file = run_dir / "files_touched.txt"
        assert touched_file.exists()
        content = touched_file.read_text()
        assert "/project/src/index.ts" in content


class TestWarnScopeDriftSh:
    def test_warns_undeclared(self, tmp_path):
        """Writes warning to stderr when file is not in target_files."""
        run_dir = tmp_path / "runs" / "001"
        run_dir.mkdir(parents=True)
        sentinel = tmp_path / ".astra-active-run"
        sentinel.write_text(str(run_dir))

        # Write current_task.json with specific target_files
        task = {"id": "t1", "target_files": ["src/expected.ts"]}
        (run_dir / "current_task.json").write_text(json.dumps(task))

        result = run_hook(
            HOOKS_DIR / "warn_scope_drift.sh",
            {"file_path": "/project/src/unexpected.ts"},
            env_extras={"PROJECT_DIR": str(tmp_path)},
        )
        assert result.returncode == 0
        assert "scope-drift" in result.stderr.lower() or "WARNING" in result.stderr

    def test_silent_for_declared(self, tmp_path):
        """No warning when file matches target_files."""
        run_dir = tmp_path / "runs" / "001"
        run_dir.mkdir(parents=True)
        sentinel = tmp_path / ".astra-active-run"
        sentinel.write_text(str(run_dir))

        task = {"id": "t1", "target_files": ["src/expected.ts"]}
        (run_dir / "current_task.json").write_text(json.dumps(task))

        result = run_hook(
            HOOKS_DIR / "warn_scope_drift.sh",
            {"file_path": "/project/src/expected.ts"},
            env_extras={"PROJECT_DIR": str(tmp_path)},
        )
        assert result.returncode == 0
        assert "scope-drift" not in result.stderr.lower()
