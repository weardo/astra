"""Tests for HITL (Human-In-The-Loop) gate utility."""

import json

import pytest

from src.core.hitl import hitl_gate
from src.core.event_store import EventStore


class TestHitlGate:
    def test_hitl_gate_returns_continue(self, tmp_run_dir):
        """Simulate a continue response."""
        store = EventStore(tmp_run_dir)
        result = hitl_gate(
            gate_name="post_plan",
            context={"task_count": 5},
            event_store=store,
            headless=False,
            _simulate_response="continue",
        )
        assert result["action"] == "continue"

    def test_hitl_gate_returns_abort(self, tmp_run_dir):
        """Simulate an abort response."""
        store = EventStore(tmp_run_dir)
        result = hitl_gate(
            gate_name="post_plan",
            context={"task_count": 5},
            event_store=store,
            headless=False,
            _simulate_response="abort",
        )
        assert result["action"] == "abort"

    def test_hitl_gate_returns_modify_with_instructions(self, tmp_run_dir):
        """Simulate a modify response with instructions."""
        store = EventStore(tmp_run_dir)
        result = hitl_gate(
            gate_name="post_plan",
            context={"task_count": 5},
            event_store=store,
            headless=False,
            _simulate_response="modify:Split task 3 into two subtasks",
        )
        assert result["action"] == "modify"
        assert result["instructions"] == "Split task 3 into two subtasks"

    def test_hitl_gate_headless_auto_continues(self, tmp_run_dir):
        """In headless mode, gate always returns continue without prompting."""
        store = EventStore(tmp_run_dir)
        result = hitl_gate(
            gate_name="post_plan",
            context={"task_count": 5},
            event_store=store,
            headless=True,
        )
        assert result["action"] == "continue"

    def test_hitl_gate_appends_event(self, tmp_run_dir):
        """Gate decision is logged as an event."""
        store = EventStore(tmp_run_dir)
        hitl_gate(
            gate_name="post_plan",
            context={"task_count": 5},
            event_store=store,
            headless=True,
        )
        events = store.replay()
        hitl_events = [e for e in events if e["type"] == "hitl_gate"]
        assert len(hitl_events) == 1
        assert hitl_events[0]["data"]["gate_name"] == "post_plan"
        assert hitl_events[0]["data"]["action"] == "continue"
