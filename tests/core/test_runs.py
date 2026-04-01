"""Tests for RunManager — ported from harness-dev, adapted for plugin data_dir convention."""

import json
import re
from pathlib import Path

import pytest

from src.core.runs import RunManager


@pytest.fixture
def rm(tmp_path):
    """RunManager instance backed by a temp directory."""
    return RunManager(tmp_path / ".astra")


class TestRunManagerSkeleton:
    def test_runs_dir_property(self, tmp_path):
        rm = RunManager(tmp_path / ".astra")
        assert rm.runs_dir == tmp_path / ".astra" / "runs"

    def test_init_creates_runs_dir(self, tmp_path):
        RunManager(tmp_path / ".astra")
        assert (tmp_path / ".astra" / "runs").is_dir()

    def test_init_idempotent(self, tmp_path):
        RunManager(tmp_path / ".astra")
        RunManager(tmp_path / ".astra")  # second call must not raise


class TestNextSequenceNumber:
    def test_empty_dir_returns_1(self, rm):
        assert rm._next_sequence_number() == 1

    def test_single_run_returns_2(self, rm):
        (rm.runs_dir / "001-feature-20260331-0000").mkdir()
        assert rm._next_sequence_number() == 2

    def test_multiple_runs_returns_max_plus_1(self, rm):
        (rm.runs_dir / "001-feature-20260331-0000").mkdir()
        (rm.runs_dir / "003-bugfix-20260331-0100").mkdir()
        (rm.runs_dir / "002-feature-20260331-0050").mkdir()
        assert rm._next_sequence_number() == 4

    def test_non_conforming_names_ignored(self, rm):
        (rm.runs_dir / "some-random-dir").mkdir()
        assert rm._next_sequence_number() == 1

    def test_sequence_beyond_999(self, rm):
        (rm.runs_dir / "999-feature-20260331-0000").mkdir()
        assert rm._next_sequence_number() == 1000


class TestCreateRun:
    def test_returns_path_object(self, rm):
        run_dir = rm.create_run("feature")
        assert isinstance(run_dir, Path)

    def test_directory_created(self, rm):
        run_dir = rm.create_run("feature")
        assert run_dir.is_dir()

    def test_directory_naming_format(self, rm):
        run_dir = rm.create_run("feature")
        parts = run_dir.name.split("-")
        assert len(parts) == 4
        assert parts[0] == "001"
        assert parts[1] == "feature"
        assert len(parts[2]) == 8  # YYYYMMDD
        assert len(parts[3]) == 4  # HHMM

    def test_strategy_lowercased(self, rm):
        run_dir = rm.create_run("BUGFIX")
        assert "bugfix" in run_dir.name

    def test_sequence_increments(self, rm):
        run1 = rm.create_run("feature")
        run2 = rm.create_run("feature")
        seq1 = int(run1.name.split("-")[0])
        seq2 = int(run2.name.split("-")[0])
        assert seq2 == seq1 + 1

    def test_no_symlink_created(self, rm):
        """create_run does NOT create a current symlink."""
        rm.create_run("feature")
        assert not (rm.runs_dir / "current").exists()

    def test_sequence_beyond_999_zero_pad_dropped(self, rm):
        (rm.runs_dir / "999-feature-20260101-0000").mkdir()
        run_dir = rm.create_run("feature")
        assert run_dir.name.startswith("1000-")

    def test_first_run_gets_001(self, rm):
        run_dir = rm.create_run("feature")
        seq = run_dir.name.split("-")[0]
        assert seq == "001"

    def test_sequential_numbering(self, rm):
        r1 = rm.create_run("feature")
        r2 = rm.create_run("feature")
        r3 = rm.create_run("feature")
        seqs = [int(r.name.split("-")[0]) for r in (r1, r2, r3)]
        assert seqs == [1, 2, 3]

    def test_directory_name_format_regex(self, rm):
        run_dir = rm.create_run("feature")
        assert re.match(r"^\d{3,}-[a-z]+-\d{8}-\d{4}$", run_dir.name), (
            f"Directory name {run_dir.name!r} does not match NNN-strategy-YYYYMMDD-HHMM"
        )

    def test_retry_on_file_exists_error(self, rm, monkeypatch):
        original_mkdir = Path.mkdir
        call_count = {"n": 0}

        def patched_mkdir(self, *args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise FileExistsError("simulated collision")
            return original_mkdir(self, *args, **kwargs)

        monkeypatch.setattr(Path, "mkdir", patched_mkdir)
        run_dir = rm.create_run("feature")
        assert run_dir.is_dir()
        assert call_count["n"] >= 2


class TestGetLatest:
    def test_returns_none_when_no_runs(self, rm):
        assert rm.get_latest() is None

    def test_returns_only_run(self, rm):
        run_dir = rm.create_run("feature")
        assert rm.get_latest() == run_dir

    def test_returns_highest_sequence(self, rm):
        rm.create_run("feature")
        run2 = rm.create_run("feature")
        assert rm.get_latest() == run2

    def test_ignores_non_run_dirs(self, rm):
        run_dir = rm.create_run("feature")
        (rm.runs_dir / "some-random-dir").mkdir()
        assert rm.get_latest() == run_dir


class TestResolveRun:
    def test_none_delegates_to_get_latest(self, rm):
        run_dir = rm.create_run("feature")
        assert rm.resolve_run(None) == run_dir

    def test_numeric_prefix_match(self, rm):
        run_dir = rm.runs_dir / "003-bugfix-20260331-0830"
        run_dir.mkdir()
        assert rm.resolve_run("003") == run_dir

    def test_exact_name_match(self, rm):
        run_dir = rm.runs_dir / "003-bugfix-20260331-0830"
        run_dir.mkdir()
        assert rm.resolve_run("003-bugfix-20260331-0830") == run_dir

    def test_no_match_returns_none(self, rm):
        assert rm.resolve_run("099") is None

    def test_invalid_format_returns_none(self, rm):
        assert rm.resolve_run("abc-bad") is None

    def test_invalid_format_does_not_raise(self, rm):
        result = rm.resolve_run("../escape")
        assert result is None


class TestListRuns:
    def test_empty_returns_empty_list(self, rm):
        assert rm.list_runs() == []

    def test_returns_list_of_dicts(self, rm):
        rm.create_run("feature")
        runs = rm.list_runs()
        assert len(runs) == 1
        assert "id" in runs[0]
        assert "name" in runs[0]
        assert "path" in runs[0]
        assert "is_latest" in runs[0]
        assert "strategy" in runs[0]

    def test_sorted_by_sequence(self, rm):
        (rm.runs_dir / "003-feature-20260331-0000").mkdir()
        (rm.runs_dir / "001-feature-20260331-0000").mkdir()
        (rm.runs_dir / "002-feature-20260331-0000").mkdir()
        runs = rm.list_runs()
        seqs = [int(r["id"]) for r in runs]
        assert seqs == sorted(seqs)

    def test_is_latest_true_for_latest_run(self, rm):
        rm.create_run("feature")
        run2 = rm.create_run("feature")
        runs = rm.list_runs()
        latest_entries = [r for r in runs if r["is_latest"]]
        assert len(latest_entries) == 1
        assert latest_entries[0]["name"] == run2.name

    def test_corrupt_state_json_does_not_raise(self, rm):
        run_dir = rm.create_run("feature")
        (run_dir / "state.json").write_text("NOT JSON {{{")
        runs = rm.list_runs()
        assert len(runs) == 1
        assert runs[0]["phase"] is None

    def test_missing_feature_list_json_progress_none(self, rm):
        rm.create_run("feature")
        runs = rm.list_runs()
        assert runs[0]["progress"] is None

    def test_with_state_json_phase_extracted(self, rm):
        run_dir = rm.create_run("feature")
        (run_dir / "state.json").write_text(json.dumps({"phase": "planning"}))
        runs = rm.list_runs()
        assert runs[0]["phase"] == "planning"

    def test_non_run_dirs_excluded(self, rm):
        (rm.runs_dir / "some-dir").mkdir()
        assert rm.list_runs() == []

    def test_events_jsonl_phase_extracted(self, rm):
        """Phase is read from events.jsonl via EventStore when state.json absent."""
        run_dir = rm.create_run("feature")
        from src.core.event_store import EventStore

        store = EventStore(run_dir)
        store.append({"type": "run_started", "data": {"run_id": "r1"}})
        store.append({"type": "planner_completed", "data": {}})
        runs = rm.list_runs()
        assert runs[0]["phase"] == "generator"


class TestPruneRuns:
    def test_under_limit_returns_zero(self, rm):
        for i in range(3):
            rm.create_run("feature")
        pruned = rm.prune_runs(keep=5)
        assert pruned == 0
        assert len(rm.list_runs()) == 3

    def test_at_limit_returns_zero(self, rm):
        for i in range(5):
            rm.create_run("feature")
        pruned = rm.prune_runs(keep=5)
        assert pruned == 0
        assert len(rm.list_runs()) == 5

    def test_over_limit_deletes_oldest(self, rm):
        runs = [rm.create_run("feature") for _ in range(5)]
        pruned = rm.prune_runs(keep=3)
        assert pruned == 2
        remaining = rm.list_runs()
        assert len(remaining) == 3
        assert not runs[0].exists()
        assert not runs[1].exists()
        assert runs[2].exists()
        assert runs[3].exists()
        assert runs[4].exists()

    def test_latest_run_protected_from_deletion(self, rm):
        """Latest run is always protected even if it would be pruned by age."""
        runs = [rm.create_run("feature") for _ in range(5)]
        pruned = rm.prune_runs(keep=3)
        # Latest (runs[4]) must survive
        assert runs[4].exists()

    def test_pruned_directories_no_longer_exist(self, rm):
        runs = [rm.create_run("feature") for _ in range(4)]
        rm.prune_runs(keep=2)
        assert not runs[0].exists()
        assert not runs[1].exists()

    def test_returns_count_of_deleted_dirs(self, rm):
        for _ in range(7):
            rm.create_run("feature")
        count = rm.prune_runs(keep=4)
        assert count == 3


class TestDetectLegacyState:
    def test_returns_true_when_legacy_state_exists_and_no_runs(self, rm):
        legacy = rm._data_dir / "state"
        legacy.mkdir()
        (legacy / "state.json").write_text("{}")
        assert rm.detect_legacy_state() is True

    def test_returns_false_when_no_legacy_state_dir(self, rm):
        assert rm.detect_legacy_state() is False

    def test_returns_false_when_legacy_dir_but_no_state_json(self, rm):
        (rm._data_dir / "state").mkdir()
        assert rm.detect_legacy_state() is False

    def test_returns_false_when_runs_already_exist(self, rm):
        legacy = rm._data_dir / "state"
        legacy.mkdir()
        (legacy / "state.json").write_text("{}")
        rm.create_run("feature")
        assert rm.detect_legacy_state() is False

    def test_does_not_modify_any_files(self, rm):
        legacy = rm._data_dir / "state"
        legacy.mkdir()
        state_json = legacy / "state.json"
        state_json.write_text('{"phase":"generator"}')
        before = state_json.read_text()
        rm.detect_legacy_state()
        assert state_json.read_text() == before
        run_dirs = [e for e in rm.runs_dir.iterdir() if e.is_dir()]
        assert run_dirs == []


class TestMigrateLegacyState:
    def _make_legacy(self, rm, strategy="feature", extra_files=None):
        legacy = rm._data_dir / "state"
        legacy.mkdir(exist_ok=True)
        state_data = {"strategy": strategy, "phase": "generator"}
        (legacy / "state.json").write_text(json.dumps(state_data))
        (legacy / "feature_list.json").write_text("[]")
        if extra_files:
            for name, content in extra_files.items():
                (legacy / name).write_text(content)
        return legacy

    def test_returns_new_run_path(self, rm):
        self._make_legacy(rm)
        result = rm.migrate_legacy_state()
        assert result.parent == rm.runs_dir
        assert result.is_dir()

    def test_all_files_copied_to_new_run_dir(self, rm):
        legacy = self._make_legacy(rm, extra_files={"progress.txt": "hello"})
        result = rm.migrate_legacy_state()
        for f in legacy.iterdir():
            if f.is_file():
                assert (result / f.name).exists(), f"{f.name} not copied"

    def test_file_contents_preserved(self, rm):
        self._make_legacy(rm)
        result = rm.migrate_legacy_state()
        orig = json.loads((rm._data_dir / "state" / "state.json").read_text())
        copied = json.loads((result / "state.json").read_text())
        assert copied == orig

    def test_migrated_run_is_latest(self, rm):
        self._make_legacy(rm)
        result = rm.migrate_legacy_state()
        assert rm.get_latest().resolve() == result.resolve()

    def test_source_dir_not_deleted(self, rm):
        legacy = self._make_legacy(rm)
        rm.migrate_legacy_state()
        assert legacy.exists()
        assert (legacy / "state.json").exists()

    def test_strategy_derived_from_state_json(self, rm):
        self._make_legacy(rm, strategy="bugfix")
        result = rm.migrate_legacy_state()
        assert "-bugfix-" in result.name

    def test_strategy_defaults_to_migrated_when_key_missing(self, rm):
        legacy = rm._data_dir / "state"
        legacy.mkdir()
        (legacy / "state.json").write_text('{"phase":"generator"}')
        result = rm.migrate_legacy_state()
        assert "-migrated-" in result.name

    def test_strategy_defaults_to_migrated_on_corrupt_json(self, rm):
        legacy = rm._data_dir / "state"
        legacy.mkdir()
        (legacy / "state.json").write_text("NOT JSON {{{")
        result = rm.migrate_legacy_state()
        assert "-migrated-" in result.name

    def test_strategy_defaults_to_migrated_when_state_json_missing(self, rm):
        legacy = rm._data_dir / "state"
        legacy.mkdir()
        (legacy / "feature_list.json").write_text("[]")
        result = rm.migrate_legacy_state()
        assert "-migrated-" in result.name

    def test_logs_per_file_migrated(self, rm, caplog):
        import logging

        self._make_legacy(rm)
        with caplog.at_level(logging.INFO, logger="src.core.runs"):
            rm.migrate_legacy_state()
        migrated_msgs = [r.message for r in caplog.records if r.message.startswith("Migrated:")]
        assert len(migrated_msgs) >= 2
        filenames = [m.split(": ", 1)[1] for m in migrated_msgs]
        assert "state.json" in filenames
        assert "feature_list.json" in filenames

    def test_logs_summary(self, rm, caplog):
        import logging

        self._make_legacy(rm)
        with caplog.at_level(logging.INFO, logger="src.core.runs"):
            result = rm.migrate_legacy_state()
        summary_msgs = [
            r.message
            for r in caplog.records
            if "Legacy state migration complete" in r.message
        ]
        assert len(summary_msgs) == 1
        assert result.name in summary_msgs[0]

    def test_subdirectories_in_legacy_not_copied(self, rm):
        legacy = self._make_legacy(rm)
        sub = legacy / "subdir"
        sub.mkdir()
        (sub / "nested.txt").write_text("nested")
        result = rm.migrate_legacy_state()
        assert not (result / "subdir").exists()
