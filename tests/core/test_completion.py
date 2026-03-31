"""Tests for completion.py -- shared completion logic.

Adapted from harness-dev: uses file helpers instead of StateManager.
"""

import tempfile
from pathlib import Path

import pytest

from src.core.completion import (
    check_completion,
    check_exit_conditions,
    check_suspicion,
    check_goal_gates,
    _save_feature_list,
    _record_exit_signal,
    _update_state,
)
from src.core.state import atomic_write


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def state_dir(tmp_dir):
    sd = tmp_dir / "runs" / "001-feature-20260101-0000"
    sd.mkdir(parents=True)
    return sd


class TestCheckCompletion:
    def test_no_features_yet(self, state_dir):
        result = check_completion(state_dir)
        assert result["complete"] is False
        assert "No features" in result["reason"]

    def test_features_remaining(self, state_dir):
        _save_feature_list(state_dir, [
            {"id": "001", "passes": True, "blocked": False},
            {"id": "002", "passes": False, "blocked": False},
            {"id": "003", "passes": False, "blocked": False},
        ])
        result = check_completion(state_dir)
        assert result["complete"] is False
        assert "2 features remaining" in result["reason"]
        assert result["progress"] is True  # 1 passing = progress

    def test_all_passing_but_no_signals(self, state_dir):
        _save_feature_list(state_dir, [
            {"id": "001", "passes": True, "blocked": False},
            {"id": "002", "passes": True, "blocked": False},
        ])
        result = check_completion(state_dir)
        assert result["complete"] is False
        assert "completion signals" in result["reason"]

    def test_all_passing_with_signals(self, state_dir):
        _save_feature_list(state_dir, [
            {"id": "001", "passes": True, "blocked": False},
            {"id": "002", "passes": True, "blocked": False},
        ])
        _record_exit_signal(state_dir, "completion", 5)
        _record_exit_signal(state_dir, "completion", 6)
        result = check_completion(state_dir)
        assert result["complete"] is True

    def test_all_blocked_counts_as_complete(self, state_dir):
        _save_feature_list(state_dir, [
            {"id": "001", "passes": True, "blocked": False},
            {"id": "002", "passes": False, "blocked": True},
        ])
        _record_exit_signal(state_dir, "completion", 5)
        _record_exit_signal(state_dir, "completion", 6)
        # remaining = 0 (1 passing + 1 blocked)
        result = check_completion(state_dir)
        assert result["complete"] is True

    def test_no_progress_when_zero_passing(self, state_dir):
        _save_feature_list(state_dir, [
            {"id": "001", "passes": False, "blocked": False},
        ])
        result = check_completion(state_dir)
        assert result["progress"] is False


class TestCheckExitConditions:
    def test_budget_exceeded(self):
        state = {"total_cost_usd": 55.0, "iteration": 5}
        config = {"max_cost_usd": 50.0}
        result = check_exit_conditions(state, config)
        assert result is not None
        assert result["should_exit"] is True
        assert "Budget" in result["reason"]

    def test_budget_not_exceeded(self):
        state = {"total_cost_usd": 30.0, "iteration": 5}
        config = {"max_cost_usd": 50.0}
        result = check_exit_conditions(state, config)
        assert result is None

    def test_time_exceeded(self):
        state = {"total_cost_usd": 0, "iteration": 5}
        config = {"max_duration_minutes": 60}
        result = check_exit_conditions(state, config, elapsed_seconds=3700)
        assert result is not None
        assert "Duration" in result["reason"]

    def test_time_not_exceeded(self):
        state = {"total_cost_usd": 0, "iteration": 5}
        config = {"max_duration_minutes": 60}
        result = check_exit_conditions(state, config, elapsed_seconds=1800)
        assert result is None

    def test_iterations_exceeded(self):
        state = {"total_cost_usd": 0, "iteration": 50}
        config = {"max_iterations": 50}
        result = check_exit_conditions(state, config)
        assert result is not None
        assert "Iteration" in result["reason"]

    def test_no_limits_set(self):
        state = {"total_cost_usd": 999, "iteration": 999}
        config = {}
        result = check_exit_conditions(state, config, elapsed_seconds=999999)
        assert result is None

    def test_zero_limits_mean_unlimited(self):
        state = {"total_cost_usd": 999, "iteration": 999}
        config = {"max_cost_usd": 0, "max_iterations": 0, "max_duration_minutes": 0}
        result = check_exit_conditions(state, config, elapsed_seconds=999999)
        assert result is None


class TestCheckSuspicion:
    @pytest.fixture
    def susp_dir(self):
        with tempfile.TemporaryDirectory() as d:
            sd = Path(d) / "state"
            sd.mkdir(parents=True)
            yield sd

    def _make_features(self, state_dir, count, passing=True, retries=0):
        """Helper: create `count` features all passing with given retries."""
        features = [
            {
                "id": str(i + 1).zfill(3),
                "passes": passing,
                "blocked": False,
                "retries": retries,
            }
            for i in range(count)
        ]
        _save_feature_list(state_dir, features)
        return features

    def test_suspicious_clean_run(self, susp_dir):
        """Zero retries + zero CB opens across all features -> suspicious."""
        self._make_features(susp_dir, 3, passing=True, retries=0)
        _update_state(susp_dir, evaluator_sessions=3)

        result = check_suspicion(susp_dir, config={}, cb_total_opens=0, elapsed_seconds=300)

        assert result["suspicious"] is True
        assert any("first-attempt pass rate" in r for r in result["reasons"])

    def test_not_suspicious_with_retries(self, susp_dir):
        """At least one retry present + sufficient evaluator sessions -> not suspicious."""
        features = [
            {"id": "001", "passes": True, "blocked": False, "retries": 2},
            {"id": "002", "passes": True, "blocked": False, "retries": 0},
            {"id": "003", "passes": True, "blocked": False, "retries": 0},
        ]
        _save_feature_list(susp_dir, features)
        _update_state(susp_dir, evaluator_sessions=3)

        # cb_total_opens=0, but retries=2 prevents check 1 from triggering
        # elapsed_seconds=300 -> 300/3=100s per feature > 30s min -> check 3 ok
        result = check_suspicion(susp_dir, config={}, cb_total_opens=0, elapsed_seconds=300)

        assert result["suspicious"] is False
        assert result["reasons"] == []

    def test_suspicious_evaluator_count(self, susp_dir):
        """Fewer evaluator sessions than total features -> suspicious."""
        self._make_features(susp_dir, 5, passing=True, retries=0)
        # evaluator_sessions=2 < total_features=5 -> check 2 triggers
        _update_state(susp_dir, evaluator_sessions=2)

        # Use cb_total_opens=1 to suppress check 1, elapsed=2000 to suppress check 3
        result = check_suspicion(susp_dir, config={}, cb_total_opens=1, elapsed_seconds=2000)

        assert result["suspicious"] is True
        assert any("evaluator sessions" in r for r in result["reasons"])

    def test_suspicious_fast_features(self, susp_dir):
        """Average time per feature below min threshold -> suspicious."""
        features = [
            {"id": "001", "passes": True, "blocked": False, "retries": 1},
            {"id": "002", "passes": True, "blocked": False, "retries": 0},
            {"id": "003", "passes": True, "blocked": False, "retries": 0},
        ]
        _save_feature_list(susp_dir, features)
        # evaluator_sessions=3 to avoid check 2
        _update_state(susp_dir, evaluator_sessions=3)

        # 3 passing features, 15s total -> 5s avg < 30s default min -> check 3 triggers
        result = check_suspicion(susp_dir, config={}, cb_total_opens=0, elapsed_seconds=15)

        assert result["suspicious"] is True
        assert any("fast average feature time" in r for r in result["reasons"])

    def test_disabled(self, susp_dir):
        """When suspicion.enabled=False, always returns clean regardless of state."""
        self._make_features(susp_dir, 5, passing=True, retries=0)
        _update_state(susp_dir, evaluator_sessions=0)

        config = {"suspicion": {"enabled": False}}
        result = check_suspicion(susp_dir, config=config, cb_total_opens=0, elapsed_seconds=1)

        assert result["suspicious"] is False
        assert result["reasons"] == []

    def test_custom_thresholds(self, susp_dir):
        """Custom min_avg_feature_seconds threshold controls check 3."""
        features = [
            {"id": "001", "passes": True, "blocked": False, "retries": 1},
        ]
        _save_feature_list(susp_dir, features)
        _update_state(susp_dir, evaluator_sessions=1)

        # 50s for 1 feature -> avg=50s
        # Default threshold (30s): 50 >= 30 -> NOT suspicious on check 3
        default_result = check_suspicion(susp_dir, config={}, cb_total_opens=0, elapsed_seconds=50)
        assert not any("fast average feature time" in r for r in default_result["reasons"])

        # Custom threshold (60s): 50 < 60 -> suspicious on check 3
        custom_config = {"suspicion": {"min_avg_feature_seconds": 60}}
        custom_result = check_suspicion(susp_dir, config=custom_config, cb_total_opens=0, elapsed_seconds=50)
        assert any("fast average feature time" in r for r in custom_result["reasons"])


# ---------------------------------------------------------------------------
# GOAL.md gate tests
# ---------------------------------------------------------------------------

class TestGoalMdGates:
    @pytest.fixture
    def goal_dir(self):
        """Create a state dir with features, signals, and GOAL.md ready for completion."""
        with tempfile.TemporaryDirectory() as d:
            state_dir = Path(d) / "runs" / "001-feature"
            state_dir.mkdir(parents=True)

            # Set up features as all passing
            _save_feature_list(state_dir, [
                {"id": "001", "passes": True, "blocked": False},
                {"id": "002", "passes": True, "blocked": False},
            ])
            # Set up completion signals
            _record_exit_signal(state_dir, "completion", 5)
            _record_exit_signal(state_dir, "completion", 6)

            yield state_dir

    def _write_goal_md(self, state_dir: Path, content: str) -> Path:
        """Write GOAL.md in the state_dir so _find_goal_md can find it."""
        goal_path = state_dir / "GOAL.md"
        goal_path.write_text(content)
        return goal_path

    def test_goal_md_hard_gate_blocks_completion(self, goal_dir):
        """If GOAL.md has hard_gates that aren't met, completion returns False."""
        self._write_goal_md(goal_dir, """# Project Goal
hard_gates:
  - "all tests pass"
  - "no lint errors"
""")
        # gate_results: only "all tests pass" is met, "no lint errors" is not
        result = check_completion(
            goal_dir,
            gate_results={"all tests pass": True, "no lint errors": False},
        )
        assert result["complete"] is False
        assert "Hard gate not met" in result["reason"]
        assert "no lint errors" in result["reason"]

    def test_goal_md_soft_gate_warns_but_passes(self, goal_dir):
        """If GOAL.md has soft_gates that aren't met, completion returns True with warning."""
        self._write_goal_md(goal_dir, """# Project Goal
soft_gates:
  - "docs updated"
""")
        # soft gate not met -- should still pass but with warnings
        result = check_completion(
            goal_dir,
            gate_results={"docs updated": False},
        )
        assert result["complete"] is True
        assert len(result["warnings"]) > 0
        assert any("docs updated" in w for w in result["warnings"])

    def test_missing_goal_md_with_require_true_errors(self, goal_dir):
        """If config says require_goal_md: true but GOAL.md doesn't exist, error."""
        # Don't create GOAL.md -- it should be missing
        # We need a state_dir where GOAL.md is NOT findable
        with tempfile.TemporaryDirectory() as isolated:
            iso_dir = Path(isolated) / "runs" / "001-feature"
            iso_dir.mkdir(parents=True)

            _save_feature_list(iso_dir, [
                {"id": "001", "passes": True, "blocked": False},
            ])
            _record_exit_signal(iso_dir, "completion", 5)
            _record_exit_signal(iso_dir, "completion", 6)

            result = check_completion(
                iso_dir,
                config={"require_goal_md": True},
            )
            assert result["complete"] is False
            assert "GOAL.md not found" in result["reason"]
