"""Tests for lightweight repo map generation."""

from pathlib import Path

import pytest

from src.core.repo_map import generate_lightweight_map, generate_context_prime


@pytest.fixture
def project(tmp_path):
    """Create a minimal project structure."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "index.ts").write_text(
        "export function main() {}\nexport class App {}\n"
    )
    (tmp_path / "src" / "utils.ts").write_text(
        "export function helper() {}\nexport const VERSION = '1.0';\n"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "index.test.ts").write_text("test('works', () => {})\n")
    (tmp_path / "package.json").write_text('{"name": "test"}')
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "dep.js").write_text("module.exports = {}")
    return tmp_path


class TestLightweightMap:
    def test_lightweight_map_lists_files(self, project):
        result = generate_lightweight_map(project)
        assert "src/index.ts" in result
        assert "src/utils.ts" in result
        assert "tests/index.test.ts" in result

    def test_lightweight_map_extracts_exports(self, project):
        result = generate_lightweight_map(project)
        assert "main" in result
        assert "App" in result
        assert "helper" in result

    def test_lightweight_map_extracts_classes(self, project):
        result = generate_lightweight_map(project)
        assert "App" in result

    def test_lightweight_map_excludes_node_modules(self, project):
        result = generate_lightweight_map(project)
        assert "node_modules" not in result

    def test_lightweight_map_stays_under_token_budget(self, project):
        result = generate_lightweight_map(project, budget_tokens=500)
        # Rough token estimate: ~4 chars per token
        estimated_tokens = len(result) / 4
        assert estimated_tokens <= 600  # some slack for estimation

    def test_lightweight_map_empty_dir(self, tmp_path):
        result = generate_lightweight_map(tmp_path)
        assert isinstance(result, str)


class TestContextPrime:
    def test_context_prime_includes_detection_and_map(self, project):
        detection = {"stack": "typescript", "test_command": "npm test"}
        repo_map = generate_lightweight_map(project)
        result = generate_context_prime(detection, repo_map)
        assert "typescript" in result
        assert "npm test" in result
        assert "src/index.ts" in result

    def test_context_prime_with_insights(self, project):
        detection = {"stack": "python"}
        repo_map = generate_lightweight_map(project)
        insights = {"friction_patterns": [{"pattern": "wrong-approach", "count": 5}]}
        result = generate_context_prime(detection, repo_map, insights=insights)
        assert "wrong-approach" in result
