"""Tests for bootstrap assets: scripts, references, agent-templates, examples."""

import subprocess
from pathlib import Path

import pytest

# Root of the astra-plugin package
PLUGIN_ROOT = Path(__file__).resolve().parents[2]

SCRIPTS_DIR = PLUGIN_ROOT / "src" / "scripts"
REFERENCES_DIR = PLUGIN_ROOT / "references"
AGENT_TEMPLATES_DIR = PLUGIN_ROOT / "agent-templates"
EXAMPLES_DIR = PLUGIN_ROOT / "examples"

EXPECTED_REFERENCES = [
    "agents-catalog.md",
    "agents-md-spec.md",
    "claude-md-rules.md",
    "goal-md-pattern.md",
    "hooks-catalog.md",
    "mcp-catalog.md",
    "rulesync-guide.md",
    "skills-catalog.md",
]

EXPECTED_AGENT_TEMPLATES = [
    "browser-tester.md",
    "ci-checker.md",
    "code-reviewer.md",
    "go-specialist.md",
    "python-specialist.md",
    "researcher.md",
    "spec-reviewer.md",
    "test-runner.md",
    "typescript-specialist.md",
]

EXPECTED_EXAMPLES = [
    "agents-md-example.md",
    "claude-md-go.md",
    "claude-md-python.md",
    "claude-md-typescript.md",
    "goal-md-example.md",
    "mcp-python.json",
    "mcp-typescript.json",
]


class TestScriptSyntax:
    def test_detect_sh_syntax_valid(self):
        result = subprocess.run(
            ["bash", "-n", str(SCRIPTS_DIR / "detect.sh")],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"detect.sh syntax error: {result.stderr}"

    def test_read_insights_sh_syntax_valid(self):
        result = subprocess.run(
            ["bash", "-n", str(SCRIPTS_DIR / "read-insights.sh")],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"read-insights.sh syntax error: {result.stderr}"


class TestReferenceFiles:
    @pytest.mark.parametrize("filename", EXPECTED_REFERENCES)
    def test_reference_file_exists(self, filename):
        path = REFERENCES_DIR / filename
        assert path.exists(), f"Missing reference file: {filename}"

    def test_all_reference_files_exist(self):
        for filename in EXPECTED_REFERENCES:
            assert (REFERENCES_DIR / filename).exists(), f"Missing: {filename}"
        assert len(EXPECTED_REFERENCES) == 8


class TestAgentTemplates:
    @pytest.mark.parametrize("filename", EXPECTED_AGENT_TEMPLATES)
    def test_agent_template_exists(self, filename):
        path = AGENT_TEMPLATES_DIR / filename
        assert path.exists(), f"Missing agent template: {filename}"

    def test_all_agent_templates_exist(self):
        for filename in EXPECTED_AGENT_TEMPLATES:
            assert (AGENT_TEMPLATES_DIR / filename).exists(), f"Missing: {filename}"
        assert len(EXPECTED_AGENT_TEMPLATES) == 9

    @pytest.mark.parametrize("filename", EXPECTED_AGENT_TEMPLATES)
    def test_agent_templates_have_frontmatter(self, filename):
        path = AGENT_TEMPLATES_DIR / filename
        content = path.read_text()
        assert content.startswith("---"), (
            f"{filename} does not start with YAML frontmatter delimiter '---'"
        )


class TestExampleFiles:
    @pytest.mark.parametrize("filename", EXPECTED_EXAMPLES)
    def test_example_file_exists(self, filename):
        path = EXAMPLES_DIR / filename
        assert path.exists(), f"Missing example file: {filename}"

    def test_all_example_files_exist(self):
        for filename in EXPECTED_EXAMPLES:
            assert (EXAMPLES_DIR / filename).exists(), f"Missing: {filename}"
        assert len(EXPECTED_EXAMPLES) == 7
