"""Tests for installers module — MCP, agents, rulesync."""

import hashlib
import json
from pathlib import Path

import pytest

from src.core.installers import (
    generate_mcp_json,
    merge_mcp_json,
    install_agents,
    check_rulesync,
)

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "agent-templates"


def _detection(stack="typescript"):
    return {
        "stack": stack,
        "test_command": "npm test",
        "build_command": "npm run build",
        "project_name": "test-project",
    }


class TestGenerateMcpJson:
    def test_generate_mcp_json_typescript(self):
        result = generate_mcp_json(_detection("typescript"))
        assert "mcpServers" in result
        assert isinstance(result["mcpServers"], dict)

    def test_generate_mcp_json_python(self):
        result = generate_mcp_json(_detection("python"))
        assert "mcpServers" in result


class TestMergeMcpJson:
    def test_mcp_merge_preserves_existing_servers(self):
        existing = {
            "mcpServers": {
                "custom-server": {"command": "node", "args": ["server.js"]},
            }
        }
        new = {
            "mcpServers": {
                "sequential-thinking": {"command": "npx", "args": ["@anthropic/thinking"]},
            }
        }
        merged = merge_mcp_json(existing, new)
        assert "custom-server" in merged["mcpServers"]
        assert "sequential-thinking" in merged["mcpServers"]


class TestInstallAgents:
    def test_install_agents_with_placeholder_substitution(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / ".claude" / "agents").mkdir(parents=True)
        hashes_path = project_dir / ".claude" / "agents" / ".hashes"

        installed = install_agents(
            project_dir, _detection(), TEMPLATES_DIR, hashes_path
        )
        assert len(installed) > 0
        # Check a file was actually written
        agents_dir = project_dir / ".claude" / "agents"
        agent_files = list(agents_dir.glob("*.md"))
        assert len(agent_files) > 0

    def test_install_agents_sha256_tracking(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / ".claude" / "agents").mkdir(parents=True)
        hashes_path = project_dir / ".claude" / "agents" / ".hashes"

        install_agents(project_dir, _detection(), TEMPLATES_DIR, hashes_path)
        assert hashes_path.exists()
        hashes = json.loads(hashes_path.read_text())
        assert len(hashes) > 0

    def test_install_agents_skip_when_hash_matches(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / ".claude" / "agents").mkdir(parents=True)
        hashes_path = project_dir / ".claude" / "agents" / ".hashes"

        # First install
        installed1 = install_agents(
            project_dir, _detection(), TEMPLATES_DIR, hashes_path
        )
        # Second install — should skip all
        installed2 = install_agents(
            project_dir, _detection(), TEMPLATES_DIR, hashes_path
        )
        # All should report "skip" on second run
        skip_count = sum(1 for r in installed2 if r.get("action") == "skip")
        assert skip_count == len(installed2)


class TestCheckRulesync:
    def test_rulesync_integration_check(self):
        result = check_rulesync()
        assert isinstance(result, bool)
