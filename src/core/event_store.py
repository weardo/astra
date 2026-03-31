"""Event-sourced state management for astra runs.

Stores all run events as an append-only JSONL log. State is reconstructed
by replaying events through materialize_state().
"""

import json
import os
import time
from pathlib import Path


class EventStore:
    """Append-only event log with state materialization."""

    def __init__(self, run_dir):
        self.run_dir = Path(run_dir)
        self.events_path = self.run_dir / "events.jsonl"

    def append(self, event):
        """Append an event to the log. Adds timestamp if not present."""
        if "timestamp" not in event:
            event["timestamp"] = time.time()
        self.run_dir.mkdir(parents=True, exist_ok=True)
        with open(self.events_path, "a") as f:
            f.write(json.dumps(event) + "\n")

    def replay(self):
        """Return all events in chronological order."""
        if not self.events_path.exists():
            return []
        events = []
        with open(self.events_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        events.sort(key=lambda e: e.get("timestamp", 0))
        return events

    def events_since(self, timestamp):
        """Return events at or after the given timestamp."""
        return [e for e in self.replay() if e.get("timestamp", 0) >= timestamp]

    def materialize_state(self):
        """Replay all events and compute current state."""
        state = {
            "run_id": None,
            "phase": "init",
            "completed_tasks": [],
            "current_feature_id": None,
            "current_task_id": None,
        }

        for event in self.replay():
            etype = event.get("type")
            data = event.get("data", {})

            if etype == "run_started":
                state["run_id"] = data.get("run_id")

            elif etype == "planner_completed":
                state["phase"] = "generator"

            elif etype == "feature_started":
                state["current_feature_id"] = data.get("feature_id")

            elif etype == "task_started":
                state["current_task_id"] = data.get("task_id")

            elif etype == "task_completed":
                task_id = data.get("task_id")
                if task_id and task_id not in state["completed_tasks"]:
                    state["completed_tasks"].append(task_id)
                state["current_task_id"] = None

            elif etype == "run_completed":
                state["phase"] = "complete"

        return state
