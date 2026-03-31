"""
Installation Utilities
=======================

Generates .mcp.json, installs agent templates with placeholder
substitution, and checks for rulesync availability.
"""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional


def generate_mcp_json(detection: dict) -> dict:
    """Generate .mcp.json with stack-appropriate MCP servers."""
    stack = detection.get("stack", "unknown")

    servers = {}

    # Always suggest sequential-thinking
    servers["sequential-thinking"] = {
        "command": "npx",
        "args": ["-y", "@anthropic/sequential-thinking"],
    }

    # Stack-specific servers
    if stack in ("typescript", "javascript"):
        servers["playwright"] = {
            "command": "npx",
            "args": ["-y", "@anthropic/playwright-mcp"],
        }
    elif stack == "python":
        servers["filesystem"] = {
            "command": "npx",
            "args": ["-y", "@anthropic/filesystem-mcp"],
        }

    return {"mcpServers": servers}


def merge_mcp_json(existing: dict, new: dict) -> dict:
    """Merge new MCP servers into existing .mcp.json, preserving user servers."""
    merged = dict(existing)
    if "mcpServers" not in merged:
        merged["mcpServers"] = {}

    new_servers = new.get("mcpServers", {})
    for name, config in new_servers.items():
        if name not in merged["mcpServers"]:
            merged["mcpServers"][name] = config

    return merged


def install_agents(
    project_dir: Path,
    detection: dict,
    templates_dir: Path,
    hashes_path: Path,
) -> list:
    """Install agent templates with placeholder substitution.

    Args:
        project_dir: The target project directory
        detection: Detection results for placeholder values
        templates_dir: Directory containing .md agent templates
        hashes_path: Path to .hashes file for idempotent re-runs

    Returns:
        List of {name, action, path} dicts describing what was done.
    """
    project_dir = Path(project_dir)
    templates_dir = Path(templates_dir)
    hashes_path = Path(hashes_path)
    agents_dir = project_dir / ".claude" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)

    # Load stored hashes
    stored_hashes = {}
    if hashes_path.exists():
        try:
            stored_hashes = json.loads(hashes_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    # Placeholder substitution values
    replacements = {
        "{{PROJECT_NAME}}": detection.get("project_name", "project"),
        "{{STACK}}": detection.get("stack", "unknown"),
        "{{TEST_COMMAND}}": detection.get("test_command", ""),
        "{{BUILD_COMMAND}}": detection.get("build_command", ""),
    }

    results = []
    new_hashes = dict(stored_hashes)

    for template_path in sorted(templates_dir.glob("*.md")):
        name = template_path.name
        target_path = agents_dir / name

        # Read and substitute
        content = template_path.read_text()
        for placeholder, value in replacements.items():
            content = content.replace(placeholder, value)

        content_hash = hashlib.sha256(content.encode()).hexdigest()

        # Check if target exists and hash matches
        if target_path.exists():
            existing_hash = stored_hashes.get(name)
            if existing_hash == content_hash:
                results.append({"name": name, "action": "skip", "path": str(target_path)})
                continue

            # Check if user modified the file
            existing_content_hash = hashlib.sha256(
                target_path.read_text().encode()
            ).hexdigest()
            if existing_hash and existing_hash != existing_content_hash:
                results.append({"name": name, "action": "conflict", "path": str(target_path)})
                continue

        # Write the agent file
        target_path.write_text(content)
        new_hashes[name] = content_hash
        action = "create" if not target_path.exists() or name not in stored_hashes else "update"
        results.append({"name": name, "action": action, "path": str(target_path)})

    # Save updated hashes
    hashes_path.write_text(json.dumps(new_hashes, indent=2))

    return results


def check_rulesync() -> bool:
    """Check if rulesync is available on PATH."""
    return shutil.which("rulesync") is not None
