"""
Configuration Loading and Validation
======================================

Loads astra.yaml, validates fields, applies defaults, and merges
detection results into the config.
"""

from pathlib import Path
from typing import Optional

import yaml


VALID_STRATEGIES = {"feature", "bugfix"}

DEFAULTS = {
    "strategy": "feature",
    "model_routing": {
        "planner": "opus",
        "generator": "sonnet",
        "evaluator": "haiku",
    },
    "max_cost_usd": 10.0,
    "max_duration_minutes": 120,
    "max_iterations": 50,
    "parallel": {
        "enabled": False,
        "max_workers": 3,
    },
    "pr": {
        "enabled": False,
        "granularity": "feature",
        "auto_merge": False,
    },
    "pipeline_depth": {
        "light_max_tasks": 5,
        "full_min_tasks": 20,
    },
    "hitl": {
        "post_plan": True,
        "pre_merge": True,
        "on_circuit_break": True,
        "budget_warning": True,
    },
    "detection": {},
}


def load_config(path: Path) -> dict:
    """Load astra.yaml config, returning defaults if file missing."""
    path = Path(path)
    config = dict(DEFAULTS)

    if path.exists():
        try:
            with open(path) as f:
                user_config = yaml.safe_load(f) or {}
            _deep_merge(config, user_config)
        except (yaml.YAMLError, OSError):
            pass

    return config


def validate_config(config: dict) -> dict:
    """Validate config fields. Returns {valid: bool, errors: list[str]}."""
    errors = []

    strategy = config.get("strategy")
    if strategy and strategy not in VALID_STRATEGIES:
        errors.append(f"Unsupported strategy: '{strategy}'. Must be one of: {VALID_STRATEGIES}")

    max_cost = config.get("max_cost_usd")
    if max_cost is not None and not isinstance(max_cost, (int, float)):
        errors.append("max_cost_usd must be a number")

    return {"valid": len(errors) == 0, "errors": errors}


def merge_detection_defaults(config: dict, detection: dict) -> dict:
    """Merge detection results into config.detection."""
    config = dict(config)
    config["detection"] = dict(config.get("detection", {}))
    config["detection"].update(detection)
    return config


def _deep_merge(base: dict, override: dict) -> None:
    """Merge override into base in-place, recursing into nested dicts."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
