import json
import time

import pytest

from src.core.event_store import EventStore


class TestEventStoreAppend:
    def test_append_creates_jsonl_file(self, tmp_run_dir):
        store = EventStore(tmp_run_dir)
        store.append({"type": "run_started", "data": {"run_id": "run-001"}})

        events_file = tmp_run_dir / "events.jsonl"
        assert events_file.exists()
        lines = events_file.read_text().strip().split("\n")
        assert len(lines) == 1
        event = json.loads(lines[0])
        assert event["type"] == "run_started"
        assert "timestamp" in event

    def test_append_multiple_events(self, tmp_run_dir):
        store = EventStore(tmp_run_dir)
        store.append({"type": "run_started", "data": {}})
        store.append({"type": "task_started", "data": {"task_id": "t1"}})
        store.append({"type": "task_completed", "data": {"task_id": "t1"}})

        events_file = tmp_run_dir / "events.jsonl"
        lines = events_file.read_text().strip().split("\n")
        assert len(lines) == 3


class TestEventStoreReplay:
    def test_replay_returns_ordered_events(self, tmp_run_dir, sample_events):
        store = EventStore(tmp_run_dir)
        for event in sample_events:
            store.append(event)

        replayed = store.replay()
        assert len(replayed) == len(sample_events)
        timestamps = [e["timestamp"] for e in replayed]
        assert timestamps == sorted(timestamps)

    def test_events_since_timestamp(self, tmp_run_dir, sample_events):
        store = EventStore(tmp_run_dir)
        for event in sample_events:
            store.append(event)

        cutoff = sample_events[2]["timestamp"]
        recent = store.events_since(cutoff)
        assert len(recent) == 4  # events at index 2,3,4,5
        assert all(e["timestamp"] >= cutoff for e in recent)


class TestEventStoreMaterialize:
    def test_materialize_state_from_events(self, tmp_run_dir, sample_events):
        store = EventStore(tmp_run_dir)
        for event in sample_events:
            store.append(event)

        state = store.materialize_state()
        assert state["run_id"] == "run-001"
        assert state["phase"] == "generator"  # planner done, tasks running
        assert len(state["completed_tasks"]) == 2

    def test_materialize_tracks_completed_tasks(self, tmp_run_dir):
        store = EventStore(tmp_run_dir)
        base_ts = time.time()
        store.append({"type": "run_started", "timestamp": base_ts, "data": {"run_id": "r1"}})
        store.append({"type": "task_completed", "timestamp": base_ts + 1, "data": {"task_id": "t1", "verdict": "PASS"}})
        store.append({"type": "task_completed", "timestamp": base_ts + 2, "data": {"task_id": "t2", "verdict": "PASS"}})

        state = store.materialize_state()
        assert state["completed_tasks"] == ["t1", "t2"]

    def test_materialize_computes_current_feature_id(self, tmp_run_dir):
        store = EventStore(tmp_run_dir)
        base_ts = time.time()
        store.append({"type": "run_started", "timestamp": base_ts, "data": {"run_id": "r1"}})
        store.append({"type": "feature_started", "timestamp": base_ts + 1, "data": {"feature_id": "feat-2"}})

        state = store.materialize_state()
        assert state["current_feature_id"] == "feat-2"

    def test_empty_log_returns_empty_state(self, tmp_run_dir):
        store = EventStore(tmp_run_dir)
        state = store.materialize_state()
        assert state["run_id"] is None
        assert state["phase"] == "init"
        assert state["completed_tasks"] == []
        assert state["current_feature_id"] is None
