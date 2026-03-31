"""Tests for config loading and validation."""

import pytest
import yaml
from pathlib import Path

from src.core.config import load_config, validate_config, merge_detection_defaults


class TestLoadConfig:
    def test_load_valid_yaml(self, tmp_path):
        config_path = tmp_path / "astra.yaml"
        config_path.write_text(yaml.dump({
            "strategy": "feature",
            "model_routing": {"planner": "opus", "generator": "sonnet"},
            "max_cost_usd": 5.0,
        }))
        config = load_config(config_path)
        assert config["strategy"] == "feature"
        assert config["model_routing"]["planner"] == "opus"

    def test_load_missing_file_returns_defaults(self, tmp_path):
        config = load_config(tmp_path / "nonexistent.yaml")
        assert config is not None
        assert "strategy" in config
        assert "model_routing" in config

    def test_validate_unsupported_strategy_errors(self):
        config = {"strategy": "invalid_strategy"}
        result = validate_config(config)
        assert not result["valid"]
        assert any("strategy" in e.lower() for e in result["errors"])

    def test_validate_missing_required_fields_uses_defaults(self):
        config = {}
        result = validate_config(config)
        assert result["valid"]

    def test_merge_detection_defaults_into_config(self):
        config = {"strategy": "feature"}
        detection = {
            "stack": "typescript",
            "test_command": "npm test",
            "build_command": "npm run build",
        }
        merged = merge_detection_defaults(config, detection)
        assert merged["strategy"] == "feature"
        assert merged["detection"]["stack"] == "typescript"
        assert merged["detection"]["test_command"] == "npm test"

    def test_model_routing_resolution(self):
        config = load_config(Path("/nonexistent"))
        assert "planner" in config["model_routing"]
        assert "generator" in config["model_routing"]
        assert "evaluator" in config["model_routing"]

    def test_pipeline_depth_thresholds(self):
        config = load_config(Path("/nonexistent"))
        assert "pipeline_depth" in config
        thresholds = config["pipeline_depth"]
        assert "light_max_tasks" in thresholds
        assert "full_min_tasks" in thresholds
        assert thresholds["light_max_tasks"] < thresholds["full_min_tasks"]
