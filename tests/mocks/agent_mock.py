"""Canned Agent tool outputs for testing orchestrator dispatch logic."""

import json


def mock_generator_result(
    status="COMPLETE",
    features_completed=1,
    features_remaining=0,
    files_modified=None,
    tests_status="10 passing, 0 failing",
) -> str:
    """Return a canned generator output with HARNESS_STATUS block."""
    files = ", ".join(files_modified or ["src/handler.ts"])
    return f"""Implementation complete.

---HARNESS_STATUS---
STATUS: {status}
FEATURES_COMPLETED_THIS_SESSION: {features_completed}
FEATURES_REMAINING: {features_remaining}
FILES_MODIFIED: {files}
TESTS_STATUS: {tests_status}
EXIT_SIGNAL: {"true" if features_remaining == 0 else "false"}
RECOMMENDATION: Continue to next task
---END_HARNESS_STATUS---"""


def mock_reviewer_result(verdict="PASS", issues=None) -> str:
    """Return a canned code-reviewer output."""
    return json.dumps({
        "verdict": verdict,
        "issues": issues or [],
    })


def mock_test_result(passed=10, failed=0, output="All tests pass") -> str:
    """Return a canned test-runner output."""
    return json.dumps({
        "verdict": "PASS" if failed == 0 else "FAIL",
        "passed": passed,
        "failed": failed,
        "output": output,
    })


def mock_evaluator_verdicts(all_pass=True) -> list:
    """Return a list of canned evaluator verdicts."""
    if all_pass:
        return [
            {"agent": "test-runner", "verdict": "PASS", "details": "10 passing"},
            {"agent": "code-reviewer", "verdict": "PASS", "details": "No issues"},
        ]
    return [
        {"agent": "test-runner", "verdict": "PASS", "details": "10 passing"},
        {"agent": "code-reviewer", "verdict": "FAIL", "details": "Security issue in auth.ts"},
    ]
