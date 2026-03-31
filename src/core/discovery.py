"""
Discovery Relay — Cross-Worker Findings
=========================================

When parallel workers discover useful context (shared configs,
patterns, gotchas), they append it here. Subsequent workers
get these discoveries injected into their prompts.
"""

import json
from pathlib import Path

DISCOVERIES_FILE = "discoveries.jsonl"


def append_discovery(run_dir, worker_id: int, finding: str) -> None:
    """Append a discovery from a worker."""
    run_dir = Path(run_dir)
    entry = {"worker_id": worker_id, "finding": finding}
    with open(run_dir / DISCOVERIES_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


def read_discoveries(run_dir) -> list:
    """Read all discoveries from the run."""
    run_dir = Path(run_dir)
    path = run_dir / DISCOVERIES_FILE
    if not path.exists():
        return []
    discoveries = []
    for line in path.read_text().strip().split("\n"):
        if line.strip():
            discoveries.append(json.loads(line))
    return discoveries


def format_for_prompt(run_dir) -> str:
    """Format discoveries for injection into a generator prompt."""
    discoveries = read_discoveries(run_dir)
    if not discoveries:
        return ""
    lines = ["## Discoveries from other workers", ""]
    for d in discoveries:
        lines.append(f"- Worker {d['worker_id']}: {d['finding']}")
    return "\n".join(lines)
