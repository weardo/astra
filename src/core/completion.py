"""
Completion Detection — Shared by Mode A + Mode B
==================================================

Determines whether the harness should continue or allow exit.
Used by both the SDK orchestrator (Mode A) and Stop hook (Mode B).

Adapted from harness-dev: uses atomic_read/atomic_write directly instead
of the removed StateManager class.
"""

import subprocess
from pathlib import Path
from typing import Optional

from .state import atomic_read, atomic_write


# ---------------------------------------------------------------------------
# File helpers (replace StateManager)
# ---------------------------------------------------------------------------

def _load_feature_list(state_dir: Path) -> list:
    """Load feature list from state_dir/feature_list.json."""
    data = atomic_read(state_dir / "feature_list.json")
    if data is None:
        return []
    if isinstance(data, list):
        return data
    return data.get("features", [])


def _save_feature_list(state_dir: Path, features: list) -> None:
    """Save feature list atomically."""
    atomic_write(state_dir / "feature_list.json", features)


def _count_features(state_dir: Path) -> dict:
    """Count feature statuses from feature_list.json."""
    features = _load_feature_list(state_dir)
    total = len(features)
    passing = sum(1 for f in features if f.get("passes"))
    blocked = sum(1 for f in features if f.get("blocked"))
    remaining = total - passing - blocked
    return {
        "total": total,
        "passing": passing,
        "blocked": blocked,
        "remaining": remaining,
    }


def _load_exit_signals(state_dir: Path) -> dict:
    """Load exit signals rolling window from state_dir/exit_signals.json."""
    data = atomic_read(state_dir / "exit_signals.json")
    if data is None:
        data = {
            "completion_signals": [],
            "blocked_signals": [],
            "error_signals": [],
        }
    return data


def _save_exit_signals(state_dir: Path, signals: dict) -> None:
    """Save exit signals atomically."""
    atomic_write(state_dir / "exit_signals.json", signals)


def _record_exit_signal(state_dir: Path, signal_type: str, iteration: int) -> None:
    """Record an exit signal, maintaining rolling window of 5."""
    signals = _load_exit_signals(state_dir)
    key = f"{signal_type}_signals"
    if key not in signals:
        signals[key] = []
    signals[key].append(iteration)
    signals[key] = signals[key][-5:]  # Keep last 5
    _save_exit_signals(state_dir, signals)


def _load_state(state_dir: Path) -> dict:
    """Load orchestrator state from state_dir/state.json."""
    data = atomic_read(state_dir / "state.json")
    if data is None:
        data = {"iteration": 0, "evaluator_sessions": 0}
    return data


def _save_state(state_dir: Path, state: dict) -> None:
    """Save orchestrator state atomically."""
    atomic_write(state_dir / "state.json", state)


def _update_state(state_dir: Path, **updates) -> dict:
    """Load, update fields, save atomically. Returns updated state."""
    state = _load_state(state_dir)
    state.update(updates)
    _save_state(state_dir, state)
    return state


# ---------------------------------------------------------------------------
# GOAL.md gate logic
# ---------------------------------------------------------------------------

def _parse_goal_md(goal_md_path: Path) -> Optional[dict]:
    """Parse GOAL.md for hard_gates and soft_gates.

    Expected format in GOAL.md YAML frontmatter or body:
        hard_gates:
          - "all tests pass"
          - "no lint errors"
        soft_gates:
          - "docs updated"

    Returns dict with 'hard_gates' and 'soft_gates' lists,
    or None if GOAL.md doesn't exist.
    """
    if not goal_md_path.exists():
        return None

    content = goal_md_path.read_text()

    hard_gates = []
    soft_gates = []

    import re

    # Parse hard_gates block
    hard_match = re.search(
        r"hard_gates:\s*\n((?:\s+-\s*.+\n?)+)", content
    )
    if hard_match:
        for item in re.findall(r'-\s*"?([^"\n]+)"?', hard_match.group(1)):
            hard_gates.append(item.strip())

    # Parse soft_gates block
    soft_match = re.search(
        r"soft_gates:\s*\n((?:\s+-\s*.+\n?)+)", content
    )
    if soft_match:
        for item in re.findall(r'-\s*"?([^"\n]+)"?', soft_match.group(1)):
            soft_gates.append(item.strip())

    return {"hard_gates": hard_gates, "soft_gates": soft_gates}


def check_goal_gates(
    state_dir: Path,
    gate_results: Optional[dict] = None,
    config: Optional[dict] = None,
) -> dict:
    """Check GOAL.md gates against provided gate results.

    Args:
        state_dir: run state directory
        gate_results: dict mapping gate name -> bool (True = met)
        config: optional config dict; if config.get('require_goal_md') is True,
                missing GOAL.md is an error
    Returns:
        {passed: bool, warnings: list[str], errors: list[str]}
    """
    config = config or {}
    gate_results = gate_results or {}
    warnings = []
    errors = []

    # GOAL.md lives at the project root — 3 levels up from state_dir
    # e.g. state_dir = <project>/.astra/runs/<run-name>
    # Try a few candidate locations
    goal_md_path = _find_goal_md(state_dir)

    if goal_md_path is None:
        if config.get("require_goal_md", False):
            return {
                "passed": False,
                "warnings": [],
                "errors": ["GOAL.md not found but require_goal_md is true"],
            }
        # No GOAL.md and not required — pass
        return {"passed": True, "warnings": [], "errors": []}

    parsed = _parse_goal_md(goal_md_path)
    if parsed is None:
        if config.get("require_goal_md", False):
            return {
                "passed": False,
                "warnings": [],
                "errors": ["GOAL.md not found but require_goal_md is true"],
            }
        return {"passed": True, "warnings": [], "errors": []}

    # Check hard gates — all must be met
    for gate in parsed.get("hard_gates", []):
        if not gate_results.get(gate, False):
            errors.append(f"Hard gate not met: {gate}")

    # Check soft gates — warn but don't block
    for gate in parsed.get("soft_gates", []):
        if not gate_results.get(gate, False):
            warnings.append(f"Soft gate not met: {gate}")

    passed = len(errors) == 0
    return {"passed": passed, "warnings": warnings, "errors": errors}


def _find_goal_md(state_dir: Path) -> Optional[Path]:
    """Locate GOAL.md relative to state_dir.

    Searches: state_dir itself, parent, grandparent, great-grandparent.
    """
    state_dir = Path(state_dir)
    candidate = state_dir
    for _ in range(4):
        goal_path = candidate / "GOAL.md"
        if goal_path.exists():
            return goal_path
        candidate = candidate.parent
    return None


# ---------------------------------------------------------------------------
# Main completion check
# ---------------------------------------------------------------------------

def check_completion(
    state_dir: Path,
    test_command: Optional[str] = None,
    gate_results: Optional[dict] = None,
    config: Optional[dict] = None,
) -> dict:
    """Check whether all completion criteria are met.

    Returns {complete: bool, reason: str, progress: bool, warnings: list}.
    Used by both Mode A orchestrator and Mode B Stop hook.
    """
    state_dir = Path(state_dir)

    # Check 1: Feature list — all features must be passing or blocked
    counts = _count_features(state_dir)
    if counts["total"] == 0:
        return {
            "complete": False,
            "reason": "No features in feature_list.json yet (planner hasn't run)",
            "progress": False,
            "warnings": [],
        }

    if counts["remaining"] > 0:
        return {
            "complete": False,
            "reason": f"{counts['remaining']} features remaining ({counts['passing']}/{counts['total']} passing, {counts['blocked']} blocked)",
            "progress": counts["passing"] > 0,
            "warnings": [],
        }

    # Check 2: Test suite — must pass (if configured)
    if test_command:
        test_result = run_test_suite(test_command, state_dir.parent.parent.parent)
        if not test_result["passed"]:
            return {
                "complete": False,
                "reason": f"Test suite failing: {test_result['output'][:200]}",
                "progress": True,  # Features are done but tests fail
                "warnings": [],
            }

    # Check 3: Rolling window — need >= 2 completion signals in last 5
    signals = _load_exit_signals(state_dir)
    completion_count = len(signals.get("completion_signals", []))
    if completion_count < 2:
        return {
            "complete": False,
            "reason": f"Need >= 2 completion signals in rolling window (have {completion_count})",
            "progress": True,
            "warnings": [],
        }

    # Check 4: GOAL.md gates
    gate_check = check_goal_gates(state_dir, gate_results=gate_results, config=config)
    if not gate_check["passed"]:
        return {
            "complete": False,
            "reason": f"GOAL.md gates not met: {'; '.join(gate_check['errors'])}",
            "progress": True,
            "warnings": gate_check["warnings"],
        }

    # All checks passed
    return {
        "complete": True,
        "reason": f"All {counts['total']} features complete ({counts['passing']} passing, {counts['blocked']} blocked), tests passing, {completion_count} completion signals",
        "progress": True,
        "warnings": gate_check.get("warnings", []),
    }


def check_exit_conditions(
    state: dict,
    config: dict,
    elapsed_seconds: float = 0,
) -> Optional[dict]:
    """Check budget/time/iteration limits.

    Returns {should_exit: True, reason: str} if any limit hit, else None.
    """
    # Budget limit
    max_cost = config.get("max_cost_usd", 0)
    if max_cost > 0 and state.get("total_cost_usd", 0) >= max_cost:
        return {
            "should_exit": True,
            "reason": f"Budget exceeded: ${state['total_cost_usd']:.2f} >= ${max_cost:.2f}",
        }

    # Time limit
    max_duration = config.get("max_duration_minutes", 0) * 60
    if max_duration > 0 and elapsed_seconds >= max_duration:
        minutes = int(elapsed_seconds / 60)
        return {
            "should_exit": True,
            "reason": f"Duration exceeded: {minutes}m >= {config['max_duration_minutes']}m",
        }

    # Iteration limit
    max_iter = config.get("max_iterations", 0)
    current_iter = state.get("iteration", 0)
    if max_iter > 0 and current_iter >= max_iter:
        return {
            "should_exit": True,
            "reason": f"Iteration limit: {current_iter} >= {max_iter}",
        }

    return None


def check_suspicion(
    state_dir: Path,
    config: dict,
    cb_total_opens: int = 0,
    elapsed_seconds: float = 0,
) -> dict:
    """Check for suspiciously clean runs that may indicate evaluation theatre.

    Returns {suspicious: bool, reasons: list[str]}.
    Reads feature list and state from files in state_dir.
    """
    suspicion_config = config.get("suspicion", {})

    # If suspicion checking is disabled, return clean immediately
    if not suspicion_config.get("enabled", True):
        return {"suspicious": False, "reasons": []}

    min_avg_feature_seconds = suspicion_config.get("min_avg_feature_seconds", 30)

    # Load feature list and state from files
    features = _load_feature_list(state_dir)
    state = _load_state(state_dir)

    total_features = len(features)
    total_retries = sum(f.get("retries", 0) for f in features)
    features_passing = sum(1 for f in features if f.get("passes"))
    evaluator_sessions = state.get("evaluator_sessions", 0)

    reasons = []

    # Check 1: zero retries AND zero circuit-breaker opens across all features
    if total_features > 0 and total_retries == 0 and cb_total_opens == 0:
        reasons.append(
            f"Suspiciously high first-attempt pass rate: 0 retries and 0 circuit-breaker opens across {total_features} features"
        )

    # Check 2: fewer evaluator sessions than total features
    if total_features > 0 and evaluator_sessions < total_features:
        reasons.append(
            f"Insufficient evaluator sessions: {evaluator_sessions} evaluator sessions for {total_features} features"
        )

    # Check 3: average time per feature below minimum threshold
    if features_passing > 0:
        avg_feature_seconds = elapsed_seconds / max(features_passing, 1)
        if avg_feature_seconds < min_avg_feature_seconds:
            reasons.append(
                f"Suspiciously fast average feature time: {avg_feature_seconds:.1f}s per feature < {min_avg_feature_seconds}s minimum"
            )

    return {
        "suspicious": len(reasons) > 0,
        "reasons": reasons,
    }


def run_test_suite(command: str, cwd: Path) -> dict:
    """Run the test suite command and return results."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout for test suite
        )
        return {
            "passed": result.returncode == 0,
            "output": result.stdout + result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "passed": False,
            "output": "Test suite timed out after 300 seconds",
            "returncode": -1,
        }
    except FileNotFoundError:
        return {
            "passed": True,  # No test command found = skip
            "output": "Test command not found, skipping",
            "returncode": 0,
        }
