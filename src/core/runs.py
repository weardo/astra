"""
Run-Scoped State Management
============================

RunManager organises plugin runs into timestamped directories under
<data_dir>/runs/, maintains a 'current' symlink for the active run, and
provides helpers for listing, resolving, and pruning past runs.

Ported from harness-dev, adapted for plugin data_dir convention.
"""

import datetime
import json
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class RunManager:
    """Manages run directories under <data_dir>/runs/."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = Path(data_dir)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("RunManager initialised with data_dir=%s", self._data_dir)

    @property
    def runs_dir(self) -> Path:
        return self._data_dir / "runs"

    @property
    def current_link(self) -> Path:
        return self.runs_dir / "current"

    def set_current(self, run_dir: Path) -> None:
        """Atomically update the 'current' symlink to point at run_dir."""
        tmp_link = self.runs_dir / "current.tmp"
        if tmp_link.exists() or tmp_link.is_symlink():
            tmp_link.unlink()
        os.symlink(run_dir.name, tmp_link)
        os.rename(tmp_link, self.current_link)
        logger.info("Updated current symlink -> %s", run_dir.name)

    def create_run(self, strategy: str) -> Path:
        """Create a new timestamped run directory and update the current symlink."""
        strategy_slug = strategy.lower()
        for _ in range(3):
            seq = self._next_sequence_number()
            seq_str = str(seq).zfill(3) if seq <= 999 else str(seq)
            ts = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d-%H%M")
            name = f"{seq_str}-{strategy_slug}-{ts}"
            run_dir = self.runs_dir / name
            try:
                run_dir.mkdir(parents=False, exist_ok=False)
            except FileExistsError:
                continue
            logger.info("Created run directory: %s", run_dir.name)
            self.set_current(run_dir)
            return run_dir
        raise RuntimeError("Failed to create a unique run directory after 3 attempts")

    def get_current(self) -> Optional[Path]:
        """Return resolved Path of the current run, or None if missing/dangling."""
        link = self.current_link
        if not link.is_symlink():
            return None
        target = self.runs_dir / os.readlink(link)
        if not target.exists():
            logger.warning("current symlink points to missing target: %s", target.name)
            return None
        try:
            target.resolve().relative_to(self.runs_dir.resolve())
        except ValueError:
            return None
        return target

    def resolve_run(self, run_id: Optional[str]) -> Optional[Path]:
        """Resolve a run_id string to its directory Path."""
        if run_id is None:
            return self.get_current()
        pattern = re.compile(r"^[0-9]{1,}(-[a-z0-9-]+)?$")
        if not pattern.match(run_id):
            logger.warning("Invalid run_id format: %s", run_id)
            return None
        for entry in self.runs_dir.iterdir():
            if not entry.is_dir():
                continue
            if entry.name == run_id or entry.name.startswith(run_id + "-"):
                return entry
        return None

    def list_runs(self) -> list:
        """Return all run directories as metadata dicts, sorted by sequence number."""
        current = self.get_current()
        runs = []
        for entry in self.runs_dir.iterdir():
            if not entry.is_dir():
                continue
            prefix = entry.name.split("-")[0]
            try:
                seq = int(prefix)
            except ValueError:
                continue
            meta = {
                "id": prefix,
                "name": entry.name,
                "path": entry,
                "is_current": current is not None and entry.resolve() == current.resolve(),
                "strategy": None,
                "created_at": None,
                "phase": None,
                "progress": None,
            }
            parts = entry.name.split("-")
            if len(parts) >= 3:
                meta["strategy"] = parts[1]
                if len(parts) >= 4:
                    meta["created_at"] = parts[-2] + "-" + parts[-1]
            # Try events.jsonl first (new event-sourced format)
            meta["phase"] = self._read_phase_from_events(entry)
            # Fall back to state.json (legacy format)
            if meta["phase"] is None:
                meta["phase"] = self._read_phase_from_state_json(entry)
            # Load feature_list.json for progress
            fl_path = entry / "feature_list.json"
            try:
                with open(fl_path) as f:
                    fl = json.load(f)
                if isinstance(fl, list):
                    total = len(fl)
                    passing = sum(1 for x in fl if x.get("passes"))
                    meta["progress"] = f"{passing}/{total}"
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                pass
            runs.append((seq, meta))
        runs.sort(key=lambda x: x[0])
        result = [m for _, m in runs]
        logger.debug("list_runs found %d runs", len(result))
        return result

    def prune_runs(self, keep: int = 20) -> int:
        """Delete oldest run directories beyond keep total, protecting the current run."""
        runs = self.list_runs()
        if len(runs) <= keep:
            return 0
        current = self.get_current()
        to_delete = runs[: len(runs) - keep]
        pruned = 0
        for meta in to_delete:
            run_path: Path = meta["path"]
            if current is not None and run_path.resolve() == current.resolve():
                continue
            shutil.rmtree(run_path)
            logger.info("Pruned run directory: %s", run_path.name)
            pruned += 1
        return pruned

    def detect_legacy_state(self) -> bool:
        """Return True if old state/state.json exists and no run dirs yet."""
        legacy_state_json = self._data_dir / "state" / "state.json"
        if not legacy_state_json.exists():
            return False
        for entry in self.runs_dir.iterdir():
            if not entry.is_dir():
                continue
            prefix = entry.name.split("-")[0]
            try:
                int(prefix)
                return False
            except ValueError:
                continue
        return True

    def migrate_legacy_state(self) -> Path:
        """Copy old state/ files into a new run directory."""
        legacy_state_dir = self._data_dir / "state"
        strategy = "migrated"
        try:
            state_json = legacy_state_dir / "state.json"
            data = json.loads(state_json.read_text())
            strategy = data.get("strategy", "migrated") or "migrated"
        except (FileNotFoundError, json.JSONDecodeError, OSError, AttributeError):
            pass

        new_run_dir = self.create_run(strategy)

        count = 0
        for src in legacy_state_dir.iterdir():
            if not src.is_file():
                continue
            dst = new_run_dir / src.name
            shutil.copy2(src, dst)
            logger.info("Migrated: %s", src.name)
            count += 1

        logger.info(
            "Legacy state migration complete: %d files copied to %s",
            count,
            new_run_dir.name,
        )
        return new_run_dir

    def _next_sequence_number(self) -> int:
        max_seq = 0
        for entry in self.runs_dir.iterdir():
            if not entry.is_dir():
                continue
            prefix = entry.name.split("-")[0]
            try:
                n = int(prefix)
            except ValueError:
                continue
            if n > max_seq:
                max_seq = n
        next_seq = max_seq + 1
        logger.debug("next sequence number: %d", next_seq)
        return next_seq

    def _read_phase_from_events(self, run_dir: Path) -> Optional[str]:
        """Read phase from events.jsonl via EventStore."""
        events_path = run_dir / "events.jsonl"
        if not events_path.exists() or events_path.stat().st_size == 0:
            return None
        try:
            from src.core.event_store import EventStore

            store = EventStore(run_dir)
            state = store.materialize_state()
            return state.get("phase")
        except Exception:
            return None

    def _read_phase_from_state_json(self, run_dir: Path) -> Optional[str]:
        """Read phase from legacy state.json."""
        state_path = run_dir / "state.json"
        try:
            with open(state_path) as f:
                state = json.load(f)
            return state.get("phase")
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None
