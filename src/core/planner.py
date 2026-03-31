"""
Planner Orchestration Helpers
==============================

Build prompts for planner roles, determine adaptive depth,
and resolve model routing.
"""

from pathlib import Path
from typing import Optional


# Role-to-agent-type mapping for model routing
ROLE_AGENT_TYPE = {
    "architect": "planner",
    "adversary": "planner",
    "refiner": "planner",
    "validator": "planner",
    "investigator": "planner",
    "bugfix-adversary": "planner",
    "fixer": "planner",
    "verifier": "planner",
    "generator": "generator",
    "evaluator": "evaluator",
}

# Default thresholds for adaptive depth
DEFAULT_THRESHOLDS = {
    "light_max_tasks": 5,
    "full_min_tasks": 20,
}

# Reference files to auto-inject per role
ROLE_INJECTIONS = {
    "generator": [
        "generator-recovery-protocol.md",
        "failure-modes.md",
    ],
}


def build_role_prompt(
    role: str,
    prompts_dir: Path,
    replacements: dict,
    references_dir: Optional[Path] = None,
    append_sections: Optional[list] = None,
) -> str:
    """Load a prompt template, apply placeholders, and append reference sections.

    Args:
        role: Role name (e.g., "architect", "adversary")
        prompts_dir: Directory containing prompt .md files
        replacements: Dict of {{PLACEHOLDER}} -> value
        references_dir: Directory containing reference .md files for injection
        append_sections: List of reference filenames to append (e.g., ["failure-modes.md"])
            If None, uses ROLE_INJECTIONS defaults for the role.

    Returns:
        The prompt string with placeholders replaced and references appended.
    """
    prompts_dir = Path(prompts_dir)
    prompt_path = prompts_dir / f"{role}.md"

    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {prompt_path}")

    content = prompt_path.read_text()

    # Append reference sections BEFORE replacement so placeholders in references get resolved
    sections = append_sections if append_sections is not None else ROLE_INJECTIONS.get(role, [])
    if sections and references_dir:
        references_dir = Path(references_dir)
        for section_file in sections:
            section_path = references_dir / section_file
            if section_path.exists():
                content += f"\n\n---\n\n{section_path.read_text()}"

    # Apply replacements to entire content (base prompt + appended references)
    for placeholder, value in replacements.items():
        content = content.replace(placeholder, value)

    return content


def get_role_sequence(
    input_mode: str,
    task_count: int = 0,
    thresholds: Optional[dict] = None,
    strategy: str = "feature",
) -> list:
    """Determine the planner role sequence based on input mode and task count.

    Args:
        input_mode: "prompt", "spec", or "plan"
        task_count: Number of tasks (for adaptive depth)
        thresholds: Override depth thresholds
        strategy: "feature" (default) or "bugfix"

    Returns:
        List of role names to execute in order.
    """
    if input_mode == "plan":
        return []

    if strategy == "bugfix":
        return ["investigator", "bugfix-adversary", "fixer", "verifier"]

    thresholds = thresholds or DEFAULT_THRESHOLDS
    light_max = thresholds.get("light_max_tasks", 5)
    full_min = thresholds.get("full_min_tasks", 20)

    if task_count <= light_max:
        return ["architect", "validator"]
    elif task_count >= full_min:
        return ["architect", "adversary", "refiner", "adversary", "refiner", "validator"]
    else:
        return ["architect", "adversary", "refiner", "validator"]


def resolve_model(role: str, config: dict) -> str:
    """Resolve the model to use for a given role.

    Checks role_models first for per-role override,
    then maps role to agent type (planner/generator/evaluator)
    and looks up the model in config.model_routing.
    """
    # Per-role override takes precedence
    role_models = config.get("role_models", {})
    if role in role_models:
        return role_models[role]

    agent_type = ROLE_AGENT_TYPE.get(role, "generator")
    routing = config.get("model_routing", {})
    return routing.get(agent_type, "sonnet")
