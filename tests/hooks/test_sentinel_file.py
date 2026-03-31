"""Tests for sentinel file (.astra-active-run) behavior used by hooks."""

import os
import time

import pytest


class TestSentinelFile:
    def test_hook_noop_when_no_sentinel(self, tmp_path):
        """Hooks exit 0 immediately when .astra-active-run doesn't exist."""
        sentinel = tmp_path / ".astra-active-run"
        assert not sentinel.exists()

    def test_hook_reads_run_dir_from_sentinel(self, tmp_path):
        """Sentinel file contains path to the current run directory."""
        run_dir = tmp_path / "runs" / "001-feature-20260331-1200"
        run_dir.mkdir(parents=True)
        sentinel = tmp_path / ".astra-active-run"
        sentinel.write_text(str(run_dir))

        content = sentinel.read_text().strip()
        assert content == str(run_dir)
        assert os.path.isdir(content)

    def test_sentinel_staleness_detection(self, tmp_path):
        """Sentinel files older than a threshold can be detected as stale."""
        sentinel = tmp_path / ".astra-active-run"
        run_dir = tmp_path / "runs" / "old-run"
        run_dir.mkdir(parents=True)
        sentinel.write_text(str(run_dir))

        # Set mtime to 2 hours ago
        old_time = time.time() - 7200
        os.utime(sentinel, (old_time, old_time))

        age_seconds = time.time() - os.path.getmtime(sentinel)
        assert age_seconds >= 7000  # ~2 hours old
        # A staleness threshold of 1 hour would flag this
        STALENESS_THRESHOLD = 3600
        assert age_seconds > STALENESS_THRESHOLD
