"""
Auto-Fix File Conflicts in Work Plans
=======================================

Standalone module that reads a work_plan.json, detects tasks sharing
target_files, and adds depends_on edges to chain them sequentially.

Called by the auto_fix_deps.sh hook after the planner writes work_plan.json.
"""

from pathlib import Path

from .work_plan import WorkPlan


def fix_work_plan(path) -> dict:
    """Load work plan, fix file conflicts, save, return stats.

    Returns: {conflicts_found: int, deps_added: int}
    """
    path = Path(path)
    wp = WorkPlan.load(path)
    result = wp.auto_fix_conflicts()
    if result["deps_added"] > 0:
        wp.save(path)
    return result


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m src.core.auto_fix_deps <work_plan.json>", file=sys.stderr)
        sys.exit(1)
    result = fix_work_plan(sys.argv[1])
    print(f"Conflicts found: {result['conflicts_found']}, deps added: {result['deps_added']}")
