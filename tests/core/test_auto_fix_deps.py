"""Tests for auto_fix_deps.py — standalone module for fixing work plan conflicts."""

import json
from pathlib import Path

import pytest

from src.core.auto_fix_deps import fix_work_plan


def _write_plan(tmp_path, tasks_by_phase):
    """Write a work_plan.json and return its path."""
    phases = []
    for i, tasks in enumerate(tasks_by_phase):
        phases.append({
            "id": f"phase-{i}",
            "name": f"Phase {i}",
            "epics": [{
                "id": f"epic-{i}",
                "name": f"Epic {i}",
                "stories": [{
                    "id": f"story-{i}",
                    "name": f"Story {i}",
                    "tasks": tasks,
                }],
            }],
        })
    path = tmp_path / "work_plan.json"
    path.write_text(json.dumps({"phases": phases}))
    return path


def _task(tid, target_files=None, depends_on=None):
    return {
        "id": tid,
        "description": f"Task {tid}",
        "acceptance_criteria": [],
        "steps": [],
        "depends_on": depends_on or [],
        "status": "pending",
        "attempts": 0,
        "target_files": target_files or [],
    }


class TestFixWorkPlan:
    def test_build_file_to_tasks_map(self, tmp_path):
        """Two tasks with same file should be detected."""
        path = _write_plan(tmp_path, [[
            _task("t1", target_files=["src/a.ts"]),
            _task("t2", target_files=["src/a.ts"]),
        ]])
        result = fix_work_plan(path)
        assert result["conflicts_found"] >= 1

    def test_fix_consecutive_pair(self, tmp_path):
        """Second task gets depends_on the first when sharing a file."""
        path = _write_plan(tmp_path, [[
            _task("t1", target_files=["src/a.ts"]),
            _task("t2", target_files=["src/a.ts"]),
        ]])
        result = fix_work_plan(path)
        assert result["deps_added"] == 1
        # Verify written to disk
        data = json.loads(path.read_text())
        t2 = data["phases"][0]["epics"][0]["stories"][0]["tasks"][1]
        assert "t1" in t2["depends_on"]

    def test_skip_already_chained(self, tmp_path):
        """No dep added if already present."""
        path = _write_plan(tmp_path, [[
            _task("t1", target_files=["src/a.ts"]),
            _task("t2", target_files=["src/a.ts"], depends_on=["t1"]),
        ]])
        result = fix_work_plan(path)
        assert result["deps_added"] == 0

    def test_cycle_detection_and_skip(self, tmp_path):
        """If fixing would create a cycle, skip."""
        path = _write_plan(tmp_path, [[
            _task("t1", target_files=["src/shared.ts"], depends_on=["t2"]),
            _task("t2", target_files=["src/shared.ts"]),
        ]])
        result = fix_work_plan(path)
        assert result["deps_added"] == 0

    def test_returns_conflict_and_dep_counts(self, tmp_path):
        """Return dict has both counts."""
        path = _write_plan(tmp_path, [[
            _task("t1", target_files=["src/a.ts", "src/b.ts"]),
            _task("t2", target_files=["src/a.ts"]),
            _task("t3", target_files=["src/b.ts"]),
        ]])
        result = fix_work_plan(path)
        assert "conflicts_found" in result
        assert "deps_added" in result
        assert result["conflicts_found"] == 2  # a.ts and b.ts
        assert result["deps_added"] == 2

    def test_empty_target_files_no_crash(self, tmp_path):
        """Tasks with empty target_files don't cause errors."""
        path = _write_plan(tmp_path, [[
            _task("t1"),
            _task("t2"),
        ]])
        result = fix_work_plan(path)
        assert result["conflicts_found"] == 0
        assert result["deps_added"] == 0

    def test_saves_changes_to_disk(self, tmp_path):
        """Changes are persisted to the file."""
        path = _write_plan(tmp_path, [[
            _task("t1", target_files=["src/x.ts"]),
            _task("t2", target_files=["src/x.ts"]),
        ]])
        fix_work_plan(path)
        # Re-read from disk
        data = json.loads(path.read_text())
        t2 = data["phases"][0]["epics"][0]["stories"][0]["tasks"][1]
        assert "t1" in t2["depends_on"]
