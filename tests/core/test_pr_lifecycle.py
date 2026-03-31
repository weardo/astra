"""Tests for PR lifecycle helpers."""

import pytest

from src.core.pr_lifecycle import (
    build_branch_name,
    build_pr_description,
    check_merge_ready,
    parse_ci_status,
)


class TestBranchCreation:
    def test_create_branch_from_task(self):
        name = build_branch_name({"id": "task-001", "description": "Add auth endpoint"})
        assert "task-001" in name
        assert "auth" in name.lower() or "add" in name.lower()

    def test_branch_name_sanitized(self):
        name = build_branch_name({"id": "task-002", "description": "Fix the bug (urgent!)"})
        assert " " not in name
        assert "(" not in name
        assert "!" not in name


class TestPRDescription:
    def test_create_pr_with_description(self):
        task = {
            "id": "task-001",
            "description": "Add user authentication",
            "acceptance_criteria": ["JWT tokens issued", "Login endpoint works"],
            "target_files": ["src/auth.ts", "tests/auth.test.ts"],
        }
        desc = build_pr_description(task)
        assert "authentication" in desc.lower()
        assert "task-001" in desc


class TestCIMonitoring:
    def test_parse_ci_pass(self):
        result = parse_ci_status("success")
        assert result["passed"] is True

    def test_parse_ci_failure(self):
        result = parse_ci_status("failure")
        assert result["passed"] is False

    def test_parse_ci_pending(self):
        result = parse_ci_status("pending")
        assert result["passed"] is False
        assert result.get("pending") is True


class TestMergeReadiness:
    def test_pr_disabled_in_config_skips(self):
        config = {"pr": {"enabled": False}}
        result = check_merge_ready(config, ci_passed=True, approved=True)
        assert result["ready"] is False
        assert "disabled" in result["reason"].lower()

    def test_merge_ready_when_ci_pass_and_approved(self):
        config = {"pr": {"enabled": True, "auto_merge": True}}
        result = check_merge_ready(config, ci_passed=True, approved=True)
        assert result["ready"] is True

    def test_merge_blocked_without_ci(self):
        config = {"pr": {"enabled": True, "auto_merge": True}}
        result = check_merge_ready(config, ci_passed=False, approved=True)
        assert result["ready"] is False

    def test_merge_blocked_without_approval(self):
        config = {"pr": {"enabled": True, "auto_merge": True}}
        result = check_merge_ready(config, ci_passed=True, approved=False)
        assert result["ready"] is False

    def test_auto_merge_disabled_needs_manual(self):
        config = {"pr": {"enabled": True, "auto_merge": False}}
        result = check_merge_ready(config, ci_passed=True, approved=True)
        assert result["ready"] is False
        assert "manual" in result["reason"].lower()
