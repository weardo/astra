"""Tests for config file generation (CLAUDE.md, AGENTS.md, GOAL.md, astra.yaml)."""

import hashlib
import json
from pathlib import Path

import pytest

from src.core.generators import (
    generate_claude_md,
    generate_agents_md,
    generate_goal_md,
    generate_astra_yaml,
    smart_merge,
)


def _detection(stack="typescript", test_cmd="npm test", build_cmd="npm run build"):
    return {
        "stack": stack,
        "test_command": test_cmd,
        "build_command": build_cmd,
        "project_name": "test-project",
        "has_git": True,
    }


class TestGenerateClaudeMd:
    def test_generate_claude_md_typescript(self):
        result = generate_claude_md(_detection("typescript"), insights=None)
        assert "typescript" in result.lower() or "TypeScript" in result
        assert "npm test" in result

    def test_generate_claude_md_python(self):
        result = generate_claude_md(
            _detection("python", "pytest", "python -m build"), insights=None
        )
        assert "python" in result.lower() or "Python" in result
        assert "pytest" in result

    def test_generate_claude_md_respects_200_line_limit(self):
        result = generate_claude_md(_detection(), insights=None)
        line_count = len(result.strip().split("\n"))
        assert line_count <= 200, f"CLAUDE.md is {line_count} lines, must be <= 200"


class TestGenerateAgentsMd:
    def test_generate_agents_md_techspokes_format(self):
        result = generate_agents_md(_detection())
        assert "test-project" in result or "## " in result

    def test_generate_agents_md_respects_100_line_limit(self):
        result = generate_agents_md(_detection())
        line_count = len(result.strip().split("\n"))
        assert line_count <= 100, f"AGENTS.md is {line_count} lines, must be <= 100"


class TestGenerateGoalMd:
    def test_generate_goal_md_with_detected_metrics(self):
        result = generate_goal_md(
            _detection(),
            mission="Ship the MVP",
            priorities=["Auth system", "Dashboard"],
        )
        assert "Ship the MVP" in result
        assert "Auth system" in result


class TestGenerateAstraYaml:
    def test_generate_astra_yaml_defaults_from_detection(self):
        result = generate_astra_yaml(_detection())
        assert "strategy:" in result
        assert "model_routing:" in result

    def test_friction_rules_injected_when_threshold_met(self):
        insights = {
            "friction_patterns": [
                {"pattern": "wrong-approach", "count": 5, "rule": "Always check existing patterns first"},
            ],
            "friction_threshold": 3,
        }
        result = generate_claude_md(_detection(), insights=insights)
        assert "Always check existing patterns first" in result


class TestSmartMerge:
    def test_smart_merge_skip_when_hash_matches(self, tmp_path):
        content = "# CLAUDE.md\nTest content\n"
        file_path = tmp_path / "CLAUDE.md"
        hashes_path = tmp_path / ".hashes"

        # Write file and compute hash
        file_path.write_text(content)
        file_hash = hashlib.sha256(content.encode()).hexdigest()
        hashes_path.write_text(json.dumps({"CLAUDE.md": file_hash}))

        result = smart_merge(file_path, content, hashes_path)
        assert result["action"] == "skip"

    def test_smart_merge_shows_diff_when_hash_differs(self, tmp_path):
        old_content = "# CLAUDE.md\nOld content\n"
        new_content = "# CLAUDE.md\nNew content\n"
        file_path = tmp_path / "CLAUDE.md"
        hashes_path = tmp_path / ".hashes"

        # Write file with old content and store its hash
        file_path.write_text(old_content)
        old_hash = hashlib.sha256(old_content.encode()).hexdigest()
        hashes_path.write_text(json.dumps({"CLAUDE.md": old_hash}))

        # Now new_content differs from old_content, and old_content matches stored hash
        # → file was NOT modified by user → safe to update
        result = smart_merge(file_path, new_content, hashes_path)
        assert result["action"] == "update"

    def test_smart_merge_create_when_file_missing(self, tmp_path):
        file_path = tmp_path / "CLAUDE.md"
        hashes_path = tmp_path / ".hashes"
        content = "# CLAUDE.md\nNew content\n"

        result = smart_merge(file_path, content, hashes_path)
        assert result["action"] == "create"
