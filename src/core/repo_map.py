"""
Lightweight Repo Map
=====================

Grep-based file listing with export/class extraction.
Stays under a token budget for prompt injection.
"""

import os
import re
from pathlib import Path
from typing import Optional

# Directories to always skip
SKIP_DIRS = {
    "node_modules", ".git", ".venv", "__pycache__", ".pytest_cache",
    "dist", "build", ".next", ".nuxt", "vendor", ".astra",
}

# File extensions to include
INCLUDE_EXTENSIONS = {
    ".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".rs",
    ".java", ".kt", ".rb", ".php", ".vue", ".svelte",
}

# Patterns to extract from source files
EXPORT_PATTERNS = [
    re.compile(r"export\s+(?:default\s+)?(?:function|class|const|let|var|interface|type|enum)\s+(\w+)"),
    re.compile(r"export\s*\{\s*([^}]+)\s*\}"),
    re.compile(r"^def\s+(\w+)\s*\(", re.MULTILINE),
    re.compile(r"^class\s+(\w+)", re.MULTILINE),
    re.compile(r"^func\s+(\w+)", re.MULTILINE),
]


def generate_lightweight_map(
    project_dir: Path,
    budget_tokens: int = 500,
) -> str:
    """Generate a lightweight repo map with file listing and export extraction.

    Args:
        project_dir: Root directory to scan.
        budget_tokens: Approximate token budget (4 chars ≈ 1 token).

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
