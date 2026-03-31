"""Tests for cross-worker discovery relay."""

import json

import pytest

from src.core.discovery import append_discovery, read_discoveries, format_for_prompt


class TestDiscovery:
    def test_append_finding(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        append_discovery(run_dir, worker_id=0, finding="Found a shared config at src/config.ts")
        discoveries = read_discoveries(run_dir)
        assert len(discoveries) == 1
        assert "shared config" in discoveries[0]["finding"]

    def test_read_findings_returns_all(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        append_discovery(run_dir, worker_id=0, finding="Finding A")
        append_discovery(run_dir, worker_id=1, finding="Finding B")
        append_discovery(run_dir, worker_id=0, finding="Finding C")
        discoveries = read_discoveries(run_dir)
        assert len(discoveries) == 3

    def test_format_findings_for_prompt(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        append_discovery(run_dir, worker_id=0, finding="Config is at src/config.ts")
        append_discovery(run_dir, worker_id=1, finding="Auth uses JWT tokens")
        result = format_for_prompt(run_dir)
        assert "Config is at src/config.ts" in result
        assert "Auth uses JWT tokens" in result

    def test_empty_discoveries_returns_empty(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        discoveries = read_discoveries(run_dir)
        assert discoveries == []
        result = format_for_prompt(run_dir)
        assert result == ""
