"""
Atomic JSON State Utilities
=============================

Crash-safe JSON read/write via temp file + flush + fsync + os.replace.
Only the utility functions are ported — StateManager is replaced by EventStore.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Optional


def atomic_write(path: Path, data: dict) -> None:
    """Write JSON atomically: temp file -> flush -> fsync -> replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp = tempfile.mkstemp(
        dir=path.parent,
        prefix=".astra_tmp_",
        suffix=".json",
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_read(path: Path) -> Optional[dict]:
    """Read JSON file, returning None if file doesn't exist."""
    path = Path(path)
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)
