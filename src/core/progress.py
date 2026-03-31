"""
Progress Detection — Multi-Source
==================================

Detects progress from: structured status block, git diff, feature list changes,
and output length trends. Based on ralph-claude-code patterns.
"""

import fnmatch
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ProgressResult:
    """Result of progress assessment."""
    has_progress: bool
    features_completed: int = 0
    files_modified: list = field(default_factory=list)
    tests_status: str = ""
    exit_signal: bool = False
    status: str = "UNKNOWN"
    recommendation: str = ""
    output_length: int = 0
    error_text: str = ""
    reasons: list = field(default_factory=list)


def parse_status_block(output_text: str) -> Optional[dict]:
    """Parse the ---HARNESS_STATUS--- block from generator output.

    Returns dict of parsed fields, or None if block not found.
    """
    pattern = r"---HARNESS_STATUS---(.*?)---END_HARNESS_STATUS---"
    match = re.search(pattern, output_text, re.DOTALL)
    if not match:
        return None

    block = match.group(1).strip()
    result = {}

    field_patterns = {
        "STATUS": r"STATUS:\s*(.+)",
        "FEATURES_COMPLETED_THIS_SESSION": r"FEATURES_COMPLETED_THIS_SESSION:\s*(\d+)",
        "FEATURES_REMAINING": r"FEATURES_REMAINING:\s*(\d+)",
        "FILES_MODIFIED": r"FILES_MODIFIED:\s*(.+)",
        "TESTS_STATUS": r"TESTS_STATUS:\s*(.+)",
        "EXIT_SIGNAL": r"EXIT_SIGNAL:\s*(.+)",
        "RECOMMENDATION": r"RECOMMENDATION:\s*(.+)",
    }

    for key, pat in field_patterns.items():
        m = re.search(pat, block)
        if m:
            value = m.group(1).strip()
            if key == "FEATURES_COMPLETED_THIS_SESSION":
                result[key] = int(value)
            elif key == "FEATURES_REMAINING":
                result[key] = int(value)
            elif key == "EXIT_SIGNAL":
                result[key] = value.lower() == "true"
            elif key == "FILES_MODIFIED":
                result[key] = [f.strip() for f in value.split(",") if f.strip()]
            else:
                result[key] = value

    return result


_NOISE_RUN_PATTERNS = [
    ".astra/runs/*/state.json",
    ".astra/runs/*/circuit_breaker.json",
    ".astra/runs/*/exit_signals.json",
]


def _is_noise_file(filepath: str, noise_files: Optional[set] = None) -> bool:
    """Return True if filepath is a known noise/state file.

    Uses exact-set matching when noise_files is provided, otherwise falls back
    to glob-pattern matching against .astra/runs/* state file patterns.
    """
    if filepath == "claude-progress.txt":
        return True
    if noise_files is not None:
        return filepath in noise_files
    return any(fnmatch.fnmatch(filepath, pat) for pat in _NOISE_RUN_PATTERNS)


def detect_meaningful_changes(
    project_dir: Path,
    state_dir: Optional[Path] = None,
) -> list[str]:
    """Check git for meaningful file changes since last commit.

    Returns list of changed file paths, excluding state/noise files.

    When state_dir is provided, noise files are resolved as exact relative paths
    from that run directory. When omitted, glob patterns match any run's state
    files under .astra/runs/.
    """
    try:
        # Check uncommitted changes
        result = subprocess.run(
            ["git", "diff", "--name-only"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        changed = [f for f in result.stdout.strip().split("\n") if f]

        # Also check staged changes
        result2 = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        staged = [f for f in result2.stdout.strip().split("\n") if f]

        all_changed = list(set(changed + staged))

        # Build run-scoped noise set when state_dir is known
        if state_dir is not None:
            run_rel = state_dir.relative_to(project_dir)
            noise_files = {
                str(run_rel / f)
                for f in ["state.json", "circuit_breaker.json", "exit_signals.json"]
            }
        else:
            noise_files = None

        return [f for f in all_changed if not _is_noise_file(f, noise_files)]

    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def detect_feature_progress(
    current_counts: dict, previous_counts: Optional[dict]
) -> bool:
    """Compare feature counts to detect new completions.

    current_counts and previous_counts are dicts with keys:
    total, passing, blocked, remaining
    """
    if previous_counts is None:
        return current_counts.get("passing", 0) > 0

    return current_counts.get("passing", 0) > previous_counts.get("passing", 0)


def detect_output_decline(
    current_length: int, peak_length: int, threshold: float = 0.7
) -> bool:
    """Check if output has declined significantly from peak.

    Returns True if output is less than threshold * peak.
    """
    if peak_length <= 0:
        return False
    return current_length < peak_length * threshold


def assess_progress(
    output_text: str,
    project_dir: Optional[Path] = None,
    state_dir: Optional[Path] = None,
    current_feature_counts: Optional[dict] = None,
    previous_feature_counts: Optional[dict] = None,
    peak_output_length: int = 0,
) -> ProgressResult:
    """Assess progress from multiple sources.

    Returns a ProgressResult combining all signals.

    state_dir, when provided, scopes the noise-file filter to the active run's
    state files rather than relying on glob patterns.
    """
    result = ProgressResult(
        has_progress=False,
        output_length=len(output_text),
    )
    reasons = []

    # Source 1: Structured status block
    status_block = parse_status_block(output_text)
    if status_block:
        result.status = status_block.get("STATUS", "UNKNOWN")
        result.exit_signal = status_block.get("EXIT_SIGNAL", False)
        result.recommendation = status_block.get("RECOMMENDATION", "")
        result.tests_status = status_block.get("TESTS_STATUS", "")

        completed = status_block.get("FEATURES_COMPLETED_THIS_SESSION", 0)
        result.features_completed = completed
        if completed > 0:
            reasons.append(f"status_block: {completed} features completed")

        files = status_block.get("FILES_MODIFIED", [])
        result.files_modified = files

    # Source 2: Git diff
    if project_dir:
        git_changes = detect_meaningful_changes(project_dir, state_dir=state_dir)
        if git_changes:
            result.files_modified = list(set(result.files_modified + git_changes))
            reasons.append(f"git: {len(git_changes)} files changed")

    # Source 3: Feature list comparison
    if current_feature_counts:
        if detect_feature_progress(current_feature_counts, previous_feature_counts):
            new_passing = (
                current_feature_counts.get("passing", 0)
                - (previous_feature_counts.get("passing", 0) if previous_feature_counts else 0)
            )
            reasons.append(f"features: {new_passing} new passing")

    # Source 4: Output decline (negative signal)
    if detect_output_decline(len(output_text), peak_output_length):
        result.error_text = "Output length declining significantly"

    # Determine overall progress
    result.has_progress = len(reasons) > 0
    result.reasons = reasons
    return result


def extract_error_from_output(output_text: str) -> str:
    """Extract the most likely error message from agent output."""
    # Look for common error patterns
    patterns = [
        r"(?:Error|ERROR|error):\s*(.+)",
        r"(?:FAIL|FAILED|Traceback).*?(?:\n.*?){0,5}",
        r"(?:AssertionError|TypeError|ValueError|RuntimeError):\s*(.+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, output_text)
        if m:
            return m.group(0)[:500]  # Cap at 500 chars
    return ""
