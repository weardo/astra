"""Tests for agent .md files — frontmatter validation."""

import re
from pathlib import Path

import pytest
import yaml

AGENTS_DIR = Path(__file__).parent.parent.parent / "agents"


def _parse_frontmatter(path):
    """Parse YAML frontmatter from a .md file."""
    content = path.read_text()
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return None
    return yaml.safe_load(match.group(1))


class TestAgentFrontmatter:
    def test_all_agents_have_valid_frontmatter(self):
        for agent_file in AGENTS_DIR.glob("*.md"):
            fm = _parse_frontmatter(agent_file)
            assert fm is not None, f"{agent_file.name} missing frontmatter"
            assert "name" in fm, f"{agent_file.name} missing name"
            assert "description" in fm, f"{agent_file.name} missing description"
            assert "tools" in fm, f"{agent_file.name} missing tools"
            assert "model" in fm, f"{agent_file.name} missing model"

    def test_generator_agent_has_no_agent_tool(self):
        fm = _parse_frontmatter(AGENTS_DIR / "generator.md")
        tools = fm["tools"]
        if isinstance(tools, str):
            tools = [t.strip() for t in tools.split(",")]
        assert "Agent" not in tools

    def test_code_reviewer_agent_uses_haiku(self):
        fm = _parse_frontmatter(AGENTS_DIR / "code-reviewer.md")
        assert fm["model"] == "haiku"

    def test_browser_tester_has_worktree_isolation(self):
        fm = _parse_frontmatter(AGENTS_DIR / "browser-tester.md")
        assert fm.get("isolation") == "worktree"

    def test_agent_model_is_valid(self):
        valid_models = {"opus", "sonnet", "haiku"}
        for agent_file in AGENTS_DIR.glob("*.md"):
            fm = _parse_frontmatter(agent_file)
            assert fm["model"] in valid_models, (
                f"{agent_file.name} has invalid model: {fm['model']}"
            )
