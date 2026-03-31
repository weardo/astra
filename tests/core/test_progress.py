"""Tests for progress.py -- multi-source progress detection."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.progress import (
    parse_status_block,
    detect_feature_progress,
    detect_output_decline,
    detect_meaningful_changes,
    assess_progress,
    extract_error_from_output,
)


SAMPLE_STATUS_BLOCK = """
Some agent output text here...

---HARNESS_STATUS---
STATUS: IN_PROGRESS
FEATURES_COMPLETED_THIS_SESSION: 2
FEATURES_REMAINING: 18
FILES_MODIFIED: src/auth.py, src/auth.test.py, init.sh
TESTS_STATUS: 12/30 passing
EXIT_SIGNAL: false
RECOMMENDATION: Continue with feature 005 (user profile)
---END_HARNESS_STATUS---
"""

COMPLETE_STATUS_BLOCK = """
All done!

---HARNESS_STATUS---
STATUS: COMPLETE
FEATURES_COMPLETED_THIS_SESSION: 1
FEATURES_REMAINING: 0
FILES_MODIFIED: src/final.py
TESTS_STATUS: 30/30 passing
EXIT_SIGNAL: true
RECOMMENDATION: All features implemented
---END_HARNESS_STATUS---
"""


class TestParseStatusBlock:
    def test_parses_all_fields(self):
        result = parse_status_block(SAMPLE_STATUS_BLOCK)
        assert result is not None
        assert result["STATUS"] == "IN_PROGRESS"
        assert result["FEATURES_COMPLETED_THIS_SESSION"] == 2
        assert result["FEATURES_REMAINING"] == 18
        assert result["FILES_MODIFIED"] == ["src/auth.py", "src/auth.test.py", "init.sh"]
        assert result["TESTS_STATUS"] == "12/30 passing"
        assert result["EXIT_SIGNAL"] is False
        assert result["RECOMMENDATION"] == "Continue with feature 005 (user profile)"

    def test_parses_complete_block(self):
        result = parse_status_block(COMPLETE_STATUS_BLOCK)
        assert result["STATUS"] == "COMPLETE"
        assert result["EXIT_SIGNAL"] is True
        assert result["FEATURES_REMAINING"] == 0

    def test_returns_none_for_no_block(self):
        assert parse_status_block("Just some regular output") is None

    def test_returns_none_for_empty(self):
        assert parse_status_block("") is None

    def test_partial_block(self):
        partial = """
---HARNESS_STATUS---
STATUS: ERROR
EXIT_SIGNAL: false
---END_HARNESS_STATUS---
"""
        result = parse_status_block(partial)
        assert result["STATUS"] == "ERROR"
        assert result["EXIT_SIGNAL"] is False
        assert "FEATURES_COMPLETED_THIS_SESSION" not in result


class TestDetectFeatureProgress:
    def test_new_passing_detected(self):
        current = {"total": 20, "passing": 5, "blocked": 0, "remaining": 15}
        previous = {"total": 20, "passing": 3, "blocked": 0, "remaining": 17}
        assert detect_feature_progress(current, previous) is True

    def test_no_change_detected(self):
        current = {"total": 20, "passing": 5, "blocked": 0, "remaining": 15}
        previous = {"total": 20, "passing": 5, "blocked": 0, "remaining": 15}
        assert detect_feature_progress(current, previous) is False

    def test_first_iteration(self):
        current = {"total": 20, "passing": 2, "blocked": 0, "remaining": 18}
        assert detect_feature_progress(current, None) is True

    def test_first_iteration_no_passing(self):
        current = {"total": 20, "passing": 0, "blocked": 0, "remaining": 20}
        assert detect_feature_progress(current, None) is False


class TestDetectOutputDecline:
    def test_decline_detected(self):
        assert detect_output_decline(300, 1000, threshold=0.7) is True

    def test_no_decline(self):
        assert detect_output_decline(800, 1000, threshold=0.7) is False

    def test_zero_peak(self):
        assert detect_output_decline(100, 0, threshold=0.7) is False

    def test_exactly_at_threshold(self):
        assert detect_output_decline(700, 1000, threshold=0.7) is False

    def test_just_below_threshold(self):
        assert detect_output_decline(699, 1000, threshold=0.7) is True


class TestAssessProgress:
    def test_progress_from_status_block(self):
        result = assess_progress(SAMPLE_STATUS_BLOCK)
        assert result.has_progress is True
        assert result.features_completed == 2
        assert result.status == "IN_PROGRESS"
        assert result.exit_signal is False

    def test_progress_from_features(self):
        current = {"passing": 5}
        previous = {"passing": 3}
        result = assess_progress(
            "no status block",
            current_feature_counts=current,
            previous_feature_counts=previous,
        )
        assert result.has_progress is True
        assert "features" in result.reasons[0]

    def test_no_progress(self):
        result = assess_progress(
            "nothing happened",
            current_feature_counts={"passing": 3},
            previous_feature_counts={"passing": 3},
        )
        assert result.has_progress is False

    def test_complete_signal(self):
        result = assess_progress(COMPLETE_STATUS_BLOCK)
        assert result.exit_signal is True
        assert result.status == "COMPLETE"

    def test_output_decline_warning(self):
        result = assess_progress("short", peak_output_length=10000)
        assert result.error_text != ""


class TestExtractError:
    def test_error_line(self):
        text = "starting...\nError: cannot find module 'express'\nmore text"
        err = extract_error_from_output(text)
        assert "cannot find module" in err

    def test_traceback(self):
        text = "Traceback (most recent call last):\n  File 'test.py'\nTypeError: bad"
        err = extract_error_from_output(text)
        assert err != ""  # Extracts some error info
        assert "bad" in err

    def test_no_error(self):
        text = "Everything went fine"
        err = extract_error_from_output(text)
        assert err == ""


def _mock_git(changed: list[str], staged: list[str] | None = None):
    """Return a side_effect for subprocess.run that fakes git diff output."""
    staged = staged or []
    outputs = ["\n".join(changed), "\n".join(staged)]
    call_count = [0]

    def _run(*args, **kwargs):
        idx = min(call_count[0], len(outputs) - 1)
        call_count[0] += 1
        result = subprocess.CompletedProcess(args, 0)
        result.stdout = outputs[idx]
        result.stderr = ""
        return result

    return _run


class TestDetectGitProgressNoise:
    """Verify noise_files filtering in detect_meaningful_changes -- both filter modes."""

    PROJECT = Path("/project")
    STATE_DIR = Path("/project/.astra/runs/run-001-feature")

    # -- with state_dir (exact-path mode) --

    def test_state_only_diff_with_state_dir_reports_no_progress(self):
        """A diff containing only run-scoped state files must yield no changes."""
        changed = [
            ".astra/runs/run-001-feature/state.json",
            ".astra/runs/run-001-feature/circuit_breaker.json",
        ]
        with patch("subprocess.run", side_effect=_mock_git(changed)):
            result = detect_meaningful_changes(self.PROJECT, state_dir=self.STATE_DIR)
        assert result == []

    def test_source_change_with_state_dir_reports_progress(self):
        """A diff with a source file must be returned even when state_dir is set."""
        changed = [
            ".astra/runs/run-001-feature/state.json",
            "src/core/runs.py",
        ]
        with patch("subprocess.run", side_effect=_mock_git(changed)):
            result = detect_meaningful_changes(self.PROJECT, state_dir=self.STATE_DIR)
        assert result == ["src/core/runs.py"]

    def test_different_run_state_file_not_filtered_with_state_dir(self):
        """State files from a *different* run are not noise when state_dir is explicit."""
        changed = [".astra/runs/run-002-other/state.json"]
        with patch("subprocess.run", side_effect=_mock_git(changed)):
            result = detect_meaningful_changes(self.PROJECT, state_dir=self.STATE_DIR)
        # run-002 state is NOT in run-001's noise set -- counts as meaningful
        assert ".astra/runs/run-002-other/state.json" in result

    def test_progress_txt_filtered_regardless_of_state_dir(self):
        """claude-progress.txt is always noise regardless of mode."""
        changed = ["claude-progress.txt", "src/app.py"]
        with patch("subprocess.run", side_effect=_mock_git(changed)):
            result = detect_meaningful_changes(self.PROJECT, state_dir=self.STATE_DIR)
        assert result == ["src/app.py"]

    # -- without state_dir (glob-pattern mode) --

    def test_state_only_diff_without_state_dir_reports_no_progress(self):
        """Run-scoped state files under any run directory must be filtered by pattern."""
        changed = [
            ".astra/runs/run-042-bugfix/state.json",
            ".astra/runs/run-042-bugfix/exit_signals.json",
        ]
        with patch("subprocess.run", side_effect=_mock_git(changed)):
            result = detect_meaningful_changes(self.PROJECT)
        assert result == []

    def test_source_change_without_state_dir_reports_progress(self):
        """Source file changes must survive the glob-pattern filter."""
        changed = [
            ".astra/runs/run-001-feature/state.json",
            "src/core/progress.py",
        ]
        with patch("subprocess.run", side_effect=_mock_git(changed)):
            result = detect_meaningful_changes(self.PROJECT)
        assert result == ["src/core/progress.py"]

    def test_old_astra_state_path_not_filtered_without_state_dir(self):
        """Legacy .astra/state/ paths are no longer silently dropped."""
        changed = [".astra/state/state.json"]
        with patch("subprocess.run", side_effect=_mock_git(changed)):
            result = detect_meaningful_changes(self.PROJECT)
        # Old path no longer matches the new patterns -- surface it as a change
        assert ".astra/state/state.json" in result

    # -- assess_progress integration --

    def test_assess_progress_passes_state_dir_to_git_check(self):
        """assess_progress with state_dir=... filters the active run's state files."""
        changed = [".astra/runs/run-001-feature/state.json"]
        with patch("subprocess.run", side_effect=_mock_git(changed)):
            result = assess_progress(
                "no status block",
                project_dir=self.PROJECT,
                state_dir=self.STATE_DIR,
            )
        assert result.has_progress is False
        assert result.files_modified == []
