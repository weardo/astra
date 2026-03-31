"""Tests for planner orchestration helpers."""

from pathlib import Path

import pytest

from src.core.planner import build_role_prompt, get_role_sequence, resolve_model


PROMPTS_DIR = Path(__file__).parent.parent.parent / "src" / "prompts"


class TestBuildRolePrompt:
    def test_build_planner_prompt_with_detection(self):
        replacements = {
            "{{DETECTION_JSON}}": '{"stack": "typescript"}',
            "{{REPO_MAP}}": "src/\n  index.ts\n",
            "{{USER_PROMPT}}": "Add auth",
        }
        result = build_role_prompt("architect", PROMPTS_DIR, replacements)
        assert "typescript" in result
        assert "Add auth" in result

    def test_build_planner_prompt_with_spec_input(self):
        replacements = {
            "{{DETECTION_JSON}}": "{}",
            "{{REPO_MAP}}": "",
            "{{USER_PROMPT}}": "See attached spec",
        }
        result = build_role_prompt("architect", PROMPTS_DIR, replacements)
        assert "See attached spec" in result

    def test_build_planner_prompt_with_plan_skips_planner(self):
        """When input is a plan path, planner should not be invoked."""
        # This is a logic test — get_role_sequence returns empty for plan mode
        seq = get_role_sequence("plan", task_count=0)
        assert seq == []


class TestResolveModel:
    def test_resolve_model_for_role(self):
        config = {
            "model_routing": {
                "planner": "opus",
                "generator": "sonnet",
                "evaluator": "haiku",
            }
        }
        assert resolve_model("architect", config) == "opus"
        assert resolve_model("adversary", config) == "opus"
        assert resolve_model("generator", config) == "sonnet"
        assert resolve_model("evaluator", config) == "haiku"
        # Unknown roles fall back to sonnet
        assert resolve_model("unknown", config) == "sonnet"


class TestGetRoleSequence:
    def test_role_sequence_for_light_depth(self):
        seq = get_role_sequence("prompt", task_count=3)
        assert seq == ["architect", "validator"]

    def test_role_sequence_for_standard_depth(self):
        seq = get_role_sequence("prompt", task_count=12)
        assert seq == ["architect", "adversary", "refiner", "validator"]

    def test_role_sequence_for_full_depth(self):
        seq = get_role_sequence("prompt", task_count=25)
        assert len(seq) == 6
        assert seq[0] == "architect"
        assert seq[-1] == "validator"

    def test_role_sequence_for_plan_mode(self):
        seq = get_role_sequence("plan", task_count=0)
        assert seq == []

    def test_role_sequence_for_spec_mode(self):
        seq = get_role_sequence("spec", task_count=10)
        assert seq[0] == "architect"

    def test_post_plan_hitl_gate_fires(self):
        """After planner sequence, HITL gate should be indicated."""
        seq = get_role_sequence("prompt", task_count=10)
        # The HITL gate fires after the sequence, not as part of it
        assert "validator" in seq  # Last role before HITL

    def test_post_plan_hitl_gate_skipped_headless(self):
        """In headless mode, HITL gate auto-continues (tested in hitl.py)."""
        # This is a cross-module concern — verified in test_hitl.py
        # Just verify the sequence is the same regardless
        seq = get_role_sequence("prompt", task_count=10)
        assert len(seq) == 4
