"""
Repo Map
=========

Tree-sitter based repo map with import graph scoring.
Falls back to grep-based extraction when grammars are unavailable.
"""

import hashlib
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Directories to always skip
SKIP_DIRS = {
    "node_modules", ".git", ".venv", "__pycache__", ".pytest_cache",
    "dist", "build", "out", ".next", ".nuxt", ".cache", "vendor", ".astra",
}

# File extensions to include
INCLUDE_EXTENSIONS = {
    ".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".rs",
    ".java", ".kt", ".rb", ".php", ".vue", ".svelte",
}

# Patterns to extract from source files (grep fallback)
EXPORT_PATTERNS = [
    re.compile(r"export\s+(?:default\s+)?(?:function|class|const|let|var|interface|type|enum)\s+(\w+)"),
    re.compile(r"export\s*\{\s*([^}]+)\s*\}"),
    re.compile(r"^def\s+(\w+)\s*\(", re.MULTILINE),
    re.compile(r"^class\s+(\w+)", re.MULTILINE),
    re.compile(r"^func\s+(\w+)", re.MULTILINE),
]

# Node types we extract definitions from, per language family
_TS_DEF_TYPES = {
    "function_declaration", "class_declaration",
    "interface_declaration", "type_alias_declaration",
}
_PY_DEF_TYPES = {"function_definition", "class_definition"}
_GO_DEF_TYPES = {"function_declaration", "type_declaration"}

# Kind labels for output
_NODE_KIND_MAP = {
    "function_declaration": "func",
    "class_declaration": "class",
    "interface_declaration": "interface",
    "type_alias_declaration": "type",
    "function_definition": "func",
    "class_definition": "class",
    "type_declaration": "type",
}


# ---------------------------------------------------------------------------
# Tree-sitter language loading
# ---------------------------------------------------------------------------

def _get_ts_language(ext: str):
    """Map file extension to a tree-sitter Language object.

    Returns None if the grammar is not installed or the extension is unknown.
    """
    try:
        import tree_sitter
    except ImportError:
        return None

    ext = ext.lower()

    if ext in (".ts",):
        try:
            import tree_sitter_typescript
            return tree_sitter.Language(tree_sitter_typescript.language_typescript())
        except ImportError:
            return None

    if ext in (".tsx",):
        try:
            import tree_sitter_typescript
            return tree_sitter.Language(tree_sitter_typescript.language_tsx())
        except ImportError:
            return None

    if ext in (".js", ".jsx"):
        try:
            import tree_sitter_typescript
            # TypeScript grammar parses JS fine
            return tree_sitter.Language(tree_sitter_typescript.language_typescript())
        except ImportError:
            return None

    if ext == ".py":
        try:
            import tree_sitter_python
            return tree_sitter.Language(tree_sitter_python.language())
        except ImportError:
            return None

    if ext == ".go":
        try:
            import tree_sitter_go
            return tree_sitter.Language(tree_sitter_go.language())
        except ImportError:
            return None

    return None


def _lang_family(ext: str) -> str:
    """Return the language family string for a file extension."""
    ext = ext.lower()
    if ext in (".ts", ".tsx", ".js", ".jsx"):
        return "typescript"
    if ext == ".py":
        return "python"
    if ext == ".go":
        return "go"
    return "unknown"


# ---------------------------------------------------------------------------
# Tree-sitter definition extraction
# ---------------------------------------------------------------------------

def _extract_definitions(filepath: Path, language) -> list:
    """Parse a file with tree-sitter, walk the AST, and extract definitions.

    Returns a list of dicts: {name, kind, line, file}.
    """
    import tree_sitter

    try:
        source = filepath.read_bytes()
    except (OSError, PermissionError):
        return []

    parser = tree_sitter.Parser(language)
    tree = parser.parse(source)
    root = tree.root_node

    ext = filepath.suffix.lower()
    family = _lang_family(ext)
    defs = []

    for child in root.children:
        extracted = _extract_from_node(child, family, str(filepath))
        defs.extend(extracted)

    return defs


def _extract_from_node(node, family: str, filepath: str) -> list:
    """Extract definition info from a single AST node."""
    results = []

    if family == "typescript":
        # Handle export_statement by looking at its children
        if node.type == "export_statement":
            for sub in node.children:
                if sub.type in _TS_DEF_TYPES:
                    info = _node_to_def(sub, filepath)
                    if info:
                        results.append(info)
        elif node.type in _TS_DEF_TYPES:
            info = _node_to_def(node, filepath)
            if info:
                results.append(info)

    elif family == "python":
        if node.type in _PY_DEF_TYPES:
            info = _node_to_def(node, filepath)
            if info:
                results.append(info)

    elif family == "go":
        if node.type == "function_declaration":
            info = _node_to_def(node, filepath)
            if info:
                results.append(info)
        elif node.type == "type_declaration":
            # Go type_declaration has type_spec children with the actual name
            for sub in node.children:
                if sub.type == "type_spec":
                    name = None
                    go_kind = "type"
                    for subsub in sub.children:
                        if subsub.type == "type_identifier":
                            name = subsub.text.decode("utf-8", errors="replace")
                        elif subsub.type == "struct_type":
                            go_kind = "struct"
                        elif subsub.type == "interface_type":
                            go_kind = "interface"
                    if name:
                        results.append({
                            "name": name,
                            "kind": go_kind,
                            "line": sub.start_point.row + 1,
                            "file": filepath,
                        })

    return results


def _node_to_def(node, filepath: str) -> Optional[dict]:
    """Extract name from a definition node by finding its identifier child."""
    kind = _NODE_KIND_MAP.get(node.type, node.type)
    name = None
    for child in node.children:
        if child.type in ("identifier", "type_identifier"):
            name = child.text.decode("utf-8", errors="replace")
            break
    if name:
        return {
            "name": name,
            "kind": kind,
            "line": node.start_point.row + 1,
            "file": filepath,
        }
    return None


# ---------------------------------------------------------------------------
# Import graph
# ---------------------------------------------------------------------------

# Regex patterns for import statements
_TS_IMPORT_RE = re.compile(
    r"""(?:import\s+.*?\s+from\s+['"]([^'"]+)['"]|require\s*\(\s*['"]([^'"]+)['"]\s*\))"""
)
_PY_IMPORT_RE = re.compile(
    r"""^(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))""", re.MULTILINE
)
_GO_IMPORT_RE = re.compile(r'''import\s+"([^"]+)"''')


def _build_import_graph(project_dir: Path, file_defs: dict) -> dict:
    """Build {file_path: [imported_file_paths]} from import statements.

    file_defs maps str(filepath) -> list of definition dicts.
    """
    project_dir = Path(project_dir).resolve()
    graph = {}  # str -> list[str]

    # Build a lookup from module-ish name to file path
    known_files = set(file_defs.keys())

    for fpath_str in file_defs:
        fpath = Path(fpath_str)
        ext = fpath.suffix.lower()
        family = _lang_family(ext)

        try:
            content = fpath.read_text(errors="ignore")
        except (OSError, PermissionError):
            continue

        imports = []

        if family == "typescript":
            for m in _TS_IMPORT_RE.finditer(content):
                raw = m.group(1) or m.group(2)
                if raw:
                    resolved = _resolve_ts_import(fpath, raw, known_files)
                    if resolved:
                        imports.append(resolved)

        elif family == "python":
            for m in _PY_IMPORT_RE.finditer(content):
                raw = m.group(1) or m.group(2)
                if raw:
                    resolved = _resolve_py_import(fpath, raw, known_files, project_dir)
                    if resolved:
                        imports.append(resolved)

        elif family == "go":
            for m in _GO_IMPORT_RE.finditer(content):
                raw = m.group(1)
                if raw:
                    resolved = _resolve_go_import(raw, known_files, project_dir)
                    if resolved:
                        imports.append(resolved)

        if imports:
            graph[fpath_str] = imports

    return graph


def _resolve_ts_import(source_file: Path, raw_import: str, known_files: set) -> Optional[str]:
    """Resolve a TS/JS relative import to an actual file path."""
    if not raw_import.startswith("."):
        return None  # External package

    base_dir = source_file.parent
    candidate_base = (base_dir / raw_import).resolve()

    # Try with extensions
    for ext in (".ts", ".tsx", ".js", ".jsx"):
        candidate = str(candidate_base) + ext
        if candidate in known_files:
            return candidate

    # Try index files
    for ext in (".ts", ".tsx", ".js", ".jsx"):
        candidate = str(candidate_base / ("index" + ext))
        if candidate in known_files:
            return candidate

    return None


def _resolve_py_import(source_file: Path, raw_import: str, known_files: set, project_dir: Path) -> Optional[str]:
    """Resolve a Python import to a file path."""
    # Convert dotted module to path
    parts = raw_import.split(".")

    # Try relative to project dir
    candidate = project_dir / Path(*parts)
    for suffix in (".py",):
        full = str(candidate) + suffix
        if full in known_files:
            return full

    # Try relative to source file's directory
    candidate = source_file.parent / Path(*parts)
    for suffix in (".py",):
        full = str(candidate) + suffix
        if full in known_files:
            return full

    # Try as package (directory with __init__.py)
    init = str(candidate / "__init__.py")
    if init in known_files:
        return init

    return None


def _resolve_go_import(raw_import: str, known_files: set, project_dir: Path) -> Optional[str]:
    """Resolve a Go import to files in the project (internal packages only)."""
    # Only resolve project-local imports
    for fpath in known_files:
        if raw_import in fpath:
            return fpath
    return None


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _score_by_references(file_defs: dict, import_graph: dict) -> list:
    """Score files by inbound reference count.

    Returns list of {file, score, definitions} sorted by score desc.
    """
    # Count inbound references
    ref_counts = {}
    for _source, targets in import_graph.items():
        for target in targets:
            ref_counts[target] = ref_counts.get(target, 0) + 1

    # Build scored list
    scored = []
    for fpath, defs in file_defs.items():
        scored.append({
            "file": fpath,
            "score": ref_counts.get(fpath, 0),
            "definitions": defs,
        })

    # Sort by score descending, then by file path for stability
    scored.sort(key=lambda x: (-x["score"], x["file"]))
    return scored


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def _compute_cache_key(project_dir: Path) -> str:
    """Compute a cache key from git HEAD + sorted file list."""
    project_dir = Path(project_dir).resolve()

    # Try git rev-parse HEAD
    git_head = ""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(project_dir),
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            git_head = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Sorted file list
    files = []
    for root, dirs, filenames in os.walk(project_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in sorted(filenames):
            fpath = Path(root) / fname
            if fpath.suffix in INCLUDE_EXTENSIONS:
                files.append(str(fpath.relative_to(project_dir)))

    content = git_head + "\n" + "\n".join(sorted(files))
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _get_cache_path(project_dir: Path) -> Path:
    """Return the cache file path for a project."""
    return Path(project_dir).resolve() / ".astra" / "repo_map_cache.md"


def _read_cache(project_dir: Path) -> Optional[str]:
    """Read cached repo map if the cache key matches."""
    cache_path = _get_cache_path(project_dir)
    if not cache_path.exists():
        return None

    try:
        content = cache_path.read_text()
    except (OSError, PermissionError):
        return None

    # First line is the cache key
    lines = content.split("\n", 1)
    if len(lines) < 2:
        return None

    stored_key = lines[0].strip()
    current_key = _compute_cache_key(project_dir)

    if stored_key == current_key:
        return lines[1]

    return None


def _write_cache(project_dir: Path, repo_map: str) -> None:
    """Write repo map to cache with current cache key."""
    cache_path = _get_cache_path(project_dir)
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        key = _compute_cache_key(project_dir)
        cache_path.write_text(key + "\n" + repo_map)
    except (OSError, PermissionError):
        pass  # Cache write failure is non-fatal


# ---------------------------------------------------------------------------
# Tree-sitter map generation
# ---------------------------------------------------------------------------

def generate_treesitter_map(project_dir: Path, budget_tokens: int = 2000) -> str:
    """Generate a repo map using tree-sitter parsing with import-graph scoring.

    Args:
        project_dir: Root directory to scan.
        budget_tokens: Approximate token budget (4 chars ~ 1 token).

    Returns:
        A string map with most-referenced files first and their definitions.

    Raises:
        ImportError: If tree-sitter is not installed.
    """
    import tree_sitter  # noqa: F401 — let ImportError propagate

    project_dir = Path(project_dir).resolve()
    char_budget = budget_tokens * 4

    # Collect definitions per file
    file_defs = {}  # str(filepath) -> [def dicts]

    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in sorted(files):
            fpath = Path(root) / fname
            ext = fpath.suffix.lower()
            if ext not in INCLUDE_EXTENSIONS:
                continue

            language = _get_ts_language(ext)
            if language is None:
                continue

            defs = _extract_definitions(fpath, language)
            if defs:
                file_defs[str(fpath)] = defs

    if not file_defs:
        return ""

    # Build import graph and score
    import_graph = _build_import_graph(project_dir, file_defs)
    scored = _score_by_references(file_defs, import_graph)

    # Render output
    lines = []
    total_chars = 0

    for entry in scored:
        fpath = entry["file"]
        try:
            rel_path = str(Path(fpath).relative_to(project_dir))
        except ValueError:
            rel_path = fpath

        score = entry["score"]
        header = f"{rel_path} ({score} refs):" if score > 0 else f"{rel_path}:"
        entry_lines = [header]

        for d in entry["definitions"]:
            entry_lines.append(f"  {d['kind']} {d['name']}")

        entry_text = "\n".join(entry_lines)

        if total_chars + len(entry_text) + 1 > char_budget:
            # Add truncation marker if we still have entries
            remaining = len(scored) - len([l for l in lines if l and not l.startswith(" ")])
            if remaining > 0:
                lines.append("  ...")
            break

        lines.append(entry_text)
        total_chars += len(entry_text) + 1  # +1 for newline

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_repo_map(project_dir: Path, budget_tokens: int = 2000) -> str:
    """Generate a repo map, preferring tree-sitter with grep fallback.

    This is the main entry point the orchestrator should call.

    Args:
        project_dir: Root directory to scan.
        budget_tokens: Approximate token budget (4 chars ~ 1 token).

    Returns:
        A string map of the project structure with key definitions.
    """
    project_dir = Path(project_dir).resolve()

    # Check cache
    cached = _read_cache(project_dir)
    if cached is not None:
        return cached

    # Try tree-sitter first
    try:
        result = generate_treesitter_map(project_dir, budget_tokens)
        if result:
            _write_cache(project_dir, result)
            return result
    except ImportError:
        logger.debug("tree-sitter not available, falling back to grep")
    except Exception as e:
        logger.debug("tree-sitter failed: %s, falling back to grep", e)

    # Fallback to grep-based map
    result = generate_lightweight_map(project_dir, budget_tokens)
    _write_cache(project_dir, result)
    return result


# ---------------------------------------------------------------------------
# Grep-based fallback (original implementation)
# ---------------------------------------------------------------------------

def generate_lightweight_map(
    project_dir: Path,
    budget_tokens: int = 500,
) -> str:
    """Generate a lightweight repo map with file listing and export extraction.

    Args:
        project_dir: Root directory to scan.
        budget_tokens: Approximate token budget (4 chars ~ 1 token).

    Returns:
        A string map of the project structure with key exports.
    """
    project_dir = Path(project_dir).resolve()
    char_budget = budget_tokens * 4
    lines = []

    for root, dirs, files in os.walk(project_dir):
        # Filter out skip directories in-place
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        rel_root = Path(root).relative_to(project_dir)

        for fname in sorted(files):
            fpath = Path(root) / fname
            ext = fpath.suffix
            if ext not in INCLUDE_EXTENSIONS:
                continue

            rel_path = str(rel_root / fname) if str(rel_root) != "." else fname

            # Extract exports/symbols
            symbols = _extract_symbols(fpath)
            if symbols:
                sym_str = ", ".join(symbols[:10])  # Cap at 10 per file
                lines.append(f"  {rel_path}: {sym_str}")
            else:
                lines.append(f"  {rel_path}")

    result = "\n".join(lines)

    # Truncate to budget
    if len(result) > char_budget:
        result = result[:char_budget].rsplit("\n", 1)[0] + "\n  ..."

    return result


def _extract_symbols(filepath: Path) -> list:
    """Extract exported symbols from a source file."""
    try:
        content = filepath.read_text(errors="ignore")
    except (OSError, PermissionError):
        return []

    symbols = []
    for pattern in EXPORT_PATTERNS:
        for match in pattern.finditer(content):
            text = match.group(1)
            # Handle "export { a, b, c }" style
            if "," in text:
                symbols.extend(s.strip().split(" ")[0] for s in text.split(","))
            else:
                symbols.append(text.strip())

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for s in symbols:
        if s and s not in seen:
            seen.add(s)
            unique.append(s)

    return unique


def generate_file_tree(project_dir: Path, max_files: int = 200) -> str:
    """Generate a compact file tree — paths only, no definitions.

    Much cheaper than generate_repo_map() (~10x fewer tokens).
    Suitable for architect planning where structure matters more than signatures.
    """
    project_dir = Path(project_dir).resolve()
    files = []

    for root, dirs, filenames in os.walk(project_dir):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for fname in sorted(filenames):
            fpath = Path(root) / fname
            if fpath.suffix in INCLUDE_EXTENSIONS:
                files.append(str(fpath.relative_to(project_dir)))

    if len(files) > max_files:
        files = files[:max_files]
        files.append(f"... ({len(files)} more files)")

    return "\n".join(files)


def generate_context_prime(
    detection: dict,
    repo_map: str,
    insights: Optional[dict] = None,
) -> str:
    """Generate a context primer combining detection, repo map, and insights.

    Used to give agents project context without loading full files.
    """
    lines = [
        f"Stack: {detection.get('stack', 'unknown')}",
        f"Test: {detection.get('test_command', 'n/a')}",
        f"Build: {detection.get('build_command', 'n/a')}",
        "",
        "Files:",
        repo_map,
    ]

    if insights and insights.get("friction_patterns"):
        lines.append("")
        lines.append("Known friction patterns:")
        for p in insights["friction_patterns"]:
            lines.append(f"  - {p.get('pattern', 'unknown')} (x{p.get('count', 0)})")

    return "\n".join(lines)
