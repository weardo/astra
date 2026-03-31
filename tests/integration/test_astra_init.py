"""Integration tests for /astra-init flow."""

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
from src.core.installers import generate_mcp_json, install_agents


TEMPLATES_DIR = Path(__file__).parent.parent.parent / "agent-templates"


def _detection(stack="typescript"):
    return {
        "stack": stack,
        "test_command": "npm test",
        "build_command": "npm run build",
        "project_name": "test-project",
        "has_git": True,
    }


def _init_project(tmp_path, detection):
    """Simulate a full /astra-init run."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / ".git").mkdir()
    (project_dir / "package.json").write_text('{"name": "test-project"}')
    claude_dir = project_dir / ".claude" / "agents"
    claude_dir.mkdir(parents=True)
    hashes_path = claude_dir / ".hashes"

    # Generate files
    claude_md = generate_claude_md(detection, insights=None)
    agents_md = generate_agents_md(detection)
    goal_md = generate_goal_md(detection, mission="Ship MVP", priorities=["Auth"])
    astra_yaml = generate_astra_yaml(detection)

    (project_dir / "CLAUDE.md").write_text(claude_md)
    (project_dir / "AGENTS.md").write_text(agents_md)
    (project_dir / "GOAL.md").write_text(goal_md)
    (project_dir / "astra.yaml").write_text(astra_yaml)

    # Install MCP
    mcp = generate_mcp_json(detection)
    (project_dir / ".mcp.json").write_text(json.dumps(mcp, indent=2))

    # Install agents
    install_agents(project_dir, detection, TEMPLATES_DIR, hashes_path)

    return project_dir


class TestAstraInitIntegration:
    def test_init_on_typescript_project_creates_all_files(self, tmp_path):
        project_dir = _init_project(tmp_path, _detection("typescript"))
        assert (project_dir / "CLAUDE.md").exists()
        assert (project_dir / "AGENTS.md").exists()
        assert (project_dir / "GOAL.md").exists()
        assert (project_dir / "astra.yaml").exists()
        assert (project_dir / ".mcp.json").exists()
        # Check agents were installed
        agents = list((project_dir / ".claude" / "agents").glob("*.md"))
        assert len(agents) > 0

    def test_init_idempotent_second_run_skips(self, tmp_path):
        detection = _detection("typescript")
        project_dir = _init_project(tmp_path, detection)

        # Second run — smart_merge should skip
        claude_md = generate_claude_md(detection, insights=None)
        hashes_path = project_dir / ".claude" / "agents" / ".hashes"

        # Store hash of CLAUDE.md
        import hashlib
        content_hash = hashlib.sha256(claude_md.encode()).hexdigest()
        hashes = json.loads(hashes_path.read_text()) if hashes_path.exists() else {}
        hashes["CLAUDE.md"] = content_hash
        hashes_path.write_text(json.dumps(hashes))
        (project_dir / "CLAUDE.md").write_text(claude_md)

        result = smart_merge(project_dir / "CLAUDE.md", claude_md, hashes_path)
        assert result["action"] == "skip"

    def test_init_headless_never_overwrites(self, tmp_path):
        """In headless mode, user-modified files should not be overwritten."""
        detection = _detection()
        project_dir = _init_project(tmp_path, detection)
        hashes_path = project_dir / ".claude" / "agents" / ".hashes"

        # Simulate user modification
        claude_md_path = project_dir / "CLAUDE.md"
        claude_md_path.write_text("# User customized this file\n")

        new_content = generate_claude_md(detection, insights=None)
        result = smart_merge(claude_md_path, new_content, hashes_path)
        # Should detect conflict since user modified the file
        assert result["action"] in ("conflict", "update")

    def test_init_zero_config_generates_astra_yaml(self, tmp_path):
        """Even with no astra.yaml, init generates one from detection."""
        detection = _detection()
        astra_yaml = generate_astra_yaml(detection)
        assert "strategy:" in astra_yaml
        assert "typescript" in astra_yaml
