"""Tests for repo map generation (grep fallback + tree-sitter)."""

from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.repo_map import (
    generate_lightweight_map,
    generate_context_prime,
    generate_treesitter_map,
    generate_repo_map,
    _get_ts_language,
    _extract_definitions,
    _build_import_graph,
    _score_by_references,
    _write_cache,
    _read_cache,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


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


@pytest.fixture
def ts_project():
    """Return path to the TypeScript fixture project."""
    return FIXTURES_DIR / "ts-project"


@pytest.fixture
def py_project():
    """Return path to the Python fixture project."""
    return FIXTURES_DIR / "py-project"


# ---------------------------------------------------------------------------
# Existing tests: TestLightweightMap, TestContextPrime
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Tree-sitter tests
# ---------------------------------------------------------------------------

class TestTreeSitterMap:
    def test_treesitter_extracts_typescript_functions(self, ts_project):
        """Parse ts-project/src/index.ts, verify main, App, Config extracted."""
        fpath = ts_project / "src" / "index.ts"
        language = _get_ts_language(".ts")
        assert language is not None, "TypeScript grammar not installed"

        defs = _extract_definitions(fpath, language)
        names = [d["name"] for d in defs]
        assert "main" in names
        assert "App" in names
        assert "Config" in names

    def test_treesitter_extracts_python_classes(self, py_project):
        """Parse py-project/main.py, verify run and Engine extracted."""
        fpath = py_project / "main.py"
        language = _get_ts_language(".py")
        assert language is not None, "Python grammar not installed"

        defs = _extract_definitions(fpath, language)
        names = [d["name"] for d in defs]
        assert "run" in names
        assert "Engine" in names

    def test_import_graph_built_from_ts_imports(self, ts_project):
        """utils.ts imports from index.ts -> graph shows dependency."""
        ts_project = ts_project.resolve()
        index_path = ts_project / "src" / "index.ts"
        utils_path = ts_project / "src" / "utils.ts"

        lang = _get_ts_language(".ts")
        assert lang is not None

        file_defs = {
            str(index_path): _extract_definitions(index_path, lang),
            str(utils_path): _extract_definitions(utils_path, lang),
        }

        graph = _build_import_graph(ts_project, file_defs)
        # utils.ts should import index.ts
        assert str(utils_path) in graph
        assert str(index_path) in graph[str(utils_path)]

    def test_scoring_ranks_most_referenced_first(self, ts_project):
        """index.ts imported by utils.ts -> index.ts ranked higher."""
        ts_project = ts_project.resolve()
        index_path = ts_project / "src" / "index.ts"
        utils_path = ts_project / "src" / "utils.ts"

        lang = _get_ts_language(".ts")
        assert lang is not None

        file_defs = {
            str(index_path): _extract_definitions(index_path, lang),
            str(utils_path): _extract_definitions(utils_path, lang),
        }

        graph = _build_import_graph(ts_project, file_defs)
        scored = _score_by_references(file_defs, graph)

        # index.ts should be first (more references)
        assert scored[0]["file"] == str(index_path)
        assert scored[0]["score"] >= 1

    def test_treesitter_map_respects_token_budget(self, ts_project):
        """Output stays under budget."""
        result = generate_treesitter_map(ts_project, budget_tokens=50)
        # 50 tokens * 4 chars = 200 chars max
        assert len(result) <= 250  # some slack for last entry

    def test_fallback_to_grep_when_no_grammar(self, tmp_path):
        """.rs file -> falls back; tree-sitter map returns empty, repo_map falls back."""
        (tmp_path / "lib.rs").write_text("pub fn hello() {}\npub struct World {}\n")

        # Tree-sitter map should return empty (no Rust grammar)
        result = generate_treesitter_map(tmp_path, budget_tokens=500)
        assert result == ""

        # generate_repo_map should fall back to lightweight
        result = generate_repo_map(tmp_path, budget_tokens=500)
        assert isinstance(result, str)

    def test_generate_repo_map_uses_treesitter(self, ts_project, tmp_path):
        """When grammars available, tree-sitter path used."""
        # Use tmp_path as project_dir to avoid cache from ts_project
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "index.ts").write_text(
            "export function main() {}\nexport class App {}\n"
        )

        result = generate_repo_map(tmp_path, budget_tokens=2000)
        # Tree-sitter output format: "file (N refs):" or "file:"
        assert "func main" in result or "class App" in result

    def test_cache_hit_returns_cached_map(self, tmp_path):
        """Second call with same project returns cached result."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.ts").write_text("export function start() {}\n")

        # First call generates and caches
        result1 = generate_repo_map(tmp_path, budget_tokens=2000)
        assert result1

        # Verify cache exists
        cache_path = tmp_path / ".astra" / "repo_map_cache.md"
        assert cache_path.exists()

        # Second call should hit cache
        result2 = _read_cache(tmp_path)
        assert result2 is not None
        assert result2 == result1

    def test_get_ts_language_returns_none_for_unknown(self):
        """Unknown extension returns None."""
        assert _get_ts_language(".rs") is None
        assert _get_ts_language(".java") is None
        assert _get_ts_language(".zig") is None

    def test_get_ts_language_returns_language_for_known(self):
        """Known extensions return Language objects."""
        assert _get_ts_language(".ts") is not None
        assert _get_ts_language(".tsx") is not None
        assert _get_ts_language(".py") is not None
        assert _get_ts_language(".go") is not None
        assert _get_ts_language(".js") is not None

    def test_extract_definitions_includes_kind(self, ts_project):
        """Definitions include correct kind labels."""
        fpath = ts_project / "src" / "index.ts"
        language = _get_ts_language(".ts")
        defs = _extract_definitions(fpath, language)

        kinds_by_name = {d["name"]: d["kind"] for d in defs}
        assert kinds_by_name["main"] == "func"
        assert kinds_by_name["App"] == "class"
        assert kinds_by_name["Config"] == "interface"

    def test_python_import_graph(self, py_project):
        """Python import graph resolves from-imports."""
        py_project = py_project.resolve()
        main_path = py_project / "main.py"
        utils_path = py_project / "utils.py"

        lang = _get_ts_language(".py")
        assert lang is not None

        file_defs = {
            str(main_path): _extract_definitions(main_path, lang),
            str(utils_path): _extract_definitions(utils_path, lang),
        }

        graph = _build_import_graph(py_project, file_defs)
        # utils.py imports from main.py
        assert str(utils_path) in graph
        assert str(main_path) in graph[str(utils_path)]
