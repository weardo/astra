import json
import os
import tempfile
import time

import pytest


@pytest.fixture
def tmp_run_dir(tmp_path):
    """Creates a temp directory simulating a run directory with events.jsonl."""
    run_dir = tmp_path / "runs" / "run-001"
    run_dir.mkdir(parents=True)
    (run_dir / "events.jsonl").touch()
    return run_dir


@pytest.fixture
def tmp_project_dir(tmp_path):
    """Creates a temp directory simulating a project with .astra-active-run sentinel."""
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True)
    return project_dir


@pytest.fixture
def sample_work_plan():
    """Returns a dict representing a work plan with target_files."""
    return {
        "features": [
            {
                "id": "feat-1",
                "title": "Add hello endpoint",
                "tasks": [
                    {
                        "id": "task-1",
                        "title": "Create route handler",
                        "target_files": ["src/routes/hello.ts", "src/routes/index.ts"],
                        "depends_on": [],
                    },
                    {
                        "id": "task-2",
                        "title": "Add tests",
                        "target_files": ["tests/hello.test.ts"],
                        "depends_on": ["task-1"],
                    },
                ],
            }
        ]
    }


@pytest.fixture
def sample_events():
    """Returns a list of common event dicts for testing."""
    base_ts = time.time()
    return [
        {
            "type": "run_started",
            "timestamp": base_ts,
            "data": {"run_id": "run-001", "prompt": "Add hello endpoint"},
        },
        {
            "type": "planner_completed",
            "timestamp": base_ts + 10,
            "data": {"role": "architect", "task_count": 2},
        },
        {
            "type": "task_started",
            "timestamp": base_ts + 20,
            "data": {"task_id": "task-1", "title": "Create route handler"},
        },
        {
            "type": "task_completed",
            "timestamp": base_ts + 60,
            "data": {"task_id": "task-1", "verdict": "PASS"},
        },
        {
            "type": "task_started",
            "timestamp": base_ts + 70,
            "data": {"task_id": "task-2", "title": "Add tests"},
        },
        {
            "type": "task_completed",
            "timestamp": base_ts + 120,
            "data": {"task_id": "task-2", "verdict": "PASS"},
        },
    ]
