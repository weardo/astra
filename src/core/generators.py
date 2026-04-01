"""
Config File Generators
=======================

Generate CLAUDE.md, AGENTS.md, GOAL.md, and astra.yaml from
project detection results and user insights.
"""

import hashlib
import json
from pathlib import Path
from typing import Optional

import yaml


def generate_claude_md(detection: dict, insights: Optional[dict] = None) -> str:
    """Generate a CLAUDE.md file from detection results.

    Args:
        detection: Dict with stack, test_command, build_command, project_name, etc.
        insights: Optional friction patterns from user session history.

    Returns:
        CLAUDE.md content string, <=200 lines.
    """
    stack = detection.get("stack", "unknown")
    if isinstance(stack, list):
        stack = stack[0] if stack else "unknown"
    project_name = detection.get("project_name", "Project")
    test_cmd = detection.get("test_command", "")
    build_cmd = detection.get("build_command", "")

    stack_label = {
        "typescript": "TypeScript/Node",
        "python": "Python",
        "go": "Go",
    }.get(stack, stack.title())

    lines = [
        f"# {project_name} — {stack_label}",
        "",
        "## Build & Test",
        "",
        "```bash",
    ]

    if build_cmd:
        lines.append(build_cmd)
    if test_cmd:
        lines.append(test_cmd)

    lines += [
        "```",
        "",
        "## AI Workflow (MANDATORY)",
        "",
        "Follow: Explore → Plan → Implement → Commit",
        "",
        "### Context Window Management",
        "1. Compact at 30% remaining — run `/compact` proactively",
        "2. Session boundaries = git commits",
        "3. NEVER run past 90% context",
        "",
        "### Development Rules",
        "- Read before writing — understand existing code first",
        "- Follow existing patterns — grep before inventing",
        "- TDD — write failing test, then implementation",
        "- Max 3-5 files per session",
        "- Fast feedback loops — run tests after each change (<30s)",
        "- No placeholder code, no TODO without tickets",
        "",
        "### Bug Fix Policy",
        "Every bug fix MUST include a test that fails before the fix and passes after.",
        "",
    ]

    # Inject friction rules from insights
    if insights and insights.get("friction_patterns"):
        threshold = insights.get("friction_threshold", 3)
        relevant = [
            p for p in insights["friction_patterns"]
            if p.get("count", 0) >= threshold
        ]
        if relevant:
            lines.append("### Learned Rules (from session history)")
            lines.append("")
            for p in relevant:
                rule = p.get("rule", "")
                if rule:
                    lines.append(f"- {rule}")
            lines.append("")

    # Stack-specific rules
    if stack == "typescript":
        lines += [
            "### TypeScript Conventions",
            "- Use strict TypeScript — no `any` unless unavoidable",
            "- Prefer `const` over `let`",
            "- Use Vitest for tests",
            "",
        ]
    elif stack == "python":
        lines += [
            "### Python Conventions",
            "- Use type hints on all function signatures",
            "- Use pytest for tests",
            "- Follow PEP 8",
            "",
        ]
    elif stack == "go":
        lines += [
            "### Go Conventions",
            "- Use `go test ./...` for tests",
            "- Follow standard Go project layout",
            "- Use `gofmt` for formatting",
            "",
        ]

    content = "\n".join(lines)
    # Enforce 200-line limit
    result_lines = content.split("\n")
    if len(result_lines) > 200:
        result_lines = result_lines[:200]
    return "\n".join(result_lines)


def generate_agents_md(detection: dict) -> str:
    """Generate an AGENTS.md file from detection results.

    Returns:
        AGENTS.md content string, <=100 lines.
    """
    project_name = detection.get("project_name", "Project")
    stack = detection.get("stack", "unknown")
    if isinstance(stack, list):
        stack = stack[0] if stack else "unknown"
    test_cmd = detection.get("test_command", "")
    build_cmd = detection.get("build_command", "")

    lines = [
        f"# {project_name}",
        "",
        f"**Stack:** {stack}",
        "",
        "## Build & Test",
        "",
        "```bash",
    ]
    if build_cmd:
        lines.append(build_cmd)
    if test_cmd:
        lines.append(test_cmd)
    lines += [
        "```",
        "",
        "## Conventions",
        "",
        "- Follow existing code patterns",
        "- Write tests for new functionality",
        "- Keep commits atomic and well-described",
        "",
    ]

    content = "\n".join(lines)
    result_lines = content.split("\n")
    if len(result_lines) > 100:
        result_lines = result_lines[:100]
    return "\n".join(result_lines)


def generate_goal_md(
    detection: dict,
    mission: str = "",
    priorities: Optional[list] = None,
) -> str:
    """Generate a GOAL.md with mission, priorities, and detected metrics."""
    project_name = detection.get("project_name", "Project")
    test_cmd = detection.get("test_command", "")

    lines = [
        f"# {project_name} — Goal",
        "",
        f"## Mission",
        "",
        mission or "Ship a working product.",
        "",
        "## Current Priorities",
        "",
    ]

    for i, p in enumerate(priorities or [], 1):
        lines.append(f"{i}. {p}")

    lines += [
        "",
        "## Success Criteria",
        "",
        "- [ ] All tests pass",
        "- [ ] No critical bugs",
        "- [ ] Core features implemented",
        "",
    ]

    if test_cmd:
        lines += [
            "## Metrics",
            "",
            f"- Test command: `{test_cmd}`",
            "",
        ]

    return "\n".join(lines)


def generate_astra_yaml(detection: dict) -> str:
    """Generate an astra.yaml config from detection results."""
    stack = detection.get("stack", "unknown")
    if isinstance(stack, list):
        stack = stack[0] if stack else "unknown"
    test_cmd = detection.get("test_command", "")

    config = {
        "strategy": "feature",
        "model_routing": {
            "planner": "opus",
            "generator": "sonnet",
            "evaluator": "haiku",
        },
        "max_cost_usd": 10.0,
        "max_duration_minutes": 120,
        "detection": {
            "stack": stack,
            "test_command": test_cmd,
        },
        "parallel": {
            "enabled": False,
            "max_workers": 3,
        },
        "pr": {
            "enabled": False,
            "auto_merge": False,
        },
    }

    return yaml.dump(config, default_flow_style=False, sort_keys=False)


def smart_merge(
    existing_path: Path,
    new_content: str,
    hashes_path: Path,
) -> dict:
    """Decide whether to create, update, or skip a generated file.

    Uses SHA256 hash tracking to detect user modifications:
    - File doesn't exist → create
    - File exists, hash matches stored → content unchanged by user
      - If new content == existing → skip (no update needed)
      - If new content != existing → update (safe, user didn't touch it)
    - File exists, hash doesn't match stored → user modified → show diff

    Returns: {action: "create"|"update"|"skip"|"conflict", diff: str}
    """
    existing_path = Path(existing_path)
    hashes_path = Path(hashes_path)
    filename = existing_path.name

    if not existing_path.exists():
        return {"action": "create", "diff": ""}

    existing_content = existing_path.read_text()
    new_hash = hashlib.sha256(new_content.encode()).hexdigest()
    existing_hash = hashlib.sha256(existing_content.encode()).hexdigest()

    # Load stored hashes
    stored_hashes = {}
    if hashes_path.exists():
        try:
            stored_hashes = json.loads(hashes_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    stored_hash = stored_hashes.get(filename)

    if new_hash == existing_hash:
        return {"action": "skip", "diff": ""}

    if stored_hash == existing_hash:
        # File unmodified by user → safe to update
        return {"action": "update", "diff": ""}

    # User modified the file → conflict
    return {"action": "conflict", "diff": f"File {filename} was modified by user"}
