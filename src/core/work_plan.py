"""
Hierarchical Work Plan — Phases / Epics / Stories / Tasks
==========================================================

Replaces the flat feature_list.json with a 3-tier work model:
  Phase -> Epic -> Story -> Task

Tasks include target_files for conflict detection and scope drift.

Ported from harness-dev, with target_files conflict detection added.
"""

import json as _json
from pathlib import Path
from typing import Optional

from .state import atomic_write, atomic_read


class WorkPlan:
    """Hierarchical work plan with phases, epics, stories, and tasks."""

    def __init__(self, data: dict):
        self.data = data

    # -------------------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------------------

    @classmethod
    def load(cls, path: Path) -> "WorkPlan":
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"work_plan.json not found: {path}")
        data = atomic_read(path)
        if data is None:
            raise FileNotFoundError(f"work_plan.json not found: {path}")
        return cls(data)

    def save(self, path: Path) -> None:
        atomic_write(Path(path), self.data)

    # -------------------------------------------------------------------------
    # Traversal
    # -------------------------------------------------------------------------

    def _all_tasks(self):
        """Yield (phase, epic, story, task) tuples in document order."""
        for phase in self.data.get("phases", []):
            for epic in phase.get("epics", []):
                for story in epic.get("stories", []):
                    for task in story.get("tasks", []):
                        yield phase, epic, story, task

    def _task_phase_index(self, task_id: str) -> int:
        for i, phase in enumerate(self.data.get("phases", [])):
            for epic in phase.get("epics", []):
                for story in epic.get("stories", []):
                    for task in story.get("tasks", []):
                        if task.get("id") == task_id:
                            return i
        return -1

    # -------------------------------------------------------------------------
    # Query helpers
    # -------------------------------------------------------------------------

    def get_task(self, task_id: str) -> Optional[dict]:
        for _, _, _, task in self._all_tasks():
            if task.get("id") == task_id:
                return task
        return None

    def get_story(self, story_id: str) -> Optional[dict]:
        for phase in self.data.get("phases", []):
            for epic in phase.get("epics", []):
                for story in epic.get("stories", []):
                    if story.get("id") == story_id:
                        return story
        return None

    def get_epic(self, epic_id: str) -> Optional[dict]:
        for phase in self.data.get("phases", []):
            for epic in phase.get("epics", []):
                if epic.get("id") == epic_id:
                    return epic
        return None

    # -------------------------------------------------------------------------
    # Next task selection
    # -------------------------------------------------------------------------

    def get_next_task(self) -> Optional[dict]:
        """Return next pending task respecting dependencies and phase gates."""
        for phase in self.data.get("phases", []):
            phase_tasks = [
                task
                for epic in phase.get("epics", [])
                for story in epic.get("stories", [])
                for task in story.get("tasks", [])
            ]
            has_pending = any(t.get("status", "pending") == "pending" for t in phase_tasks)
            if has_pending:
                for task in phase_tasks:
                    if task.get("status", "pending") != "pending":
                        continue
                    if self.are_deps_satisfied(task["id"]):
                        return task
                return None
        return None

    # -------------------------------------------------------------------------
    # Task mutations
    # -------------------------------------------------------------------------

    def mark_task_done(self, task_id: str, path: Path) -> None:
        task = self.get_task(task_id)
        if task is not None:
            task["status"] = "done"
            self.save(path)

    def mark_task_blocked(self, task_id: str, reason: str, path: Path) -> None:
        task = self.get_task(task_id)
        if task is not None:
            task["status"] = "blocked"
            task["blocked_reason"] = reason
            self.save(path)

    def increment_task_attempts(self, task_id: str, path: Path) -> int:
        task = self.get_task(task_id)
        if task is None:
            return 0
        task["attempts"] = task.get("attempts", 0) + 1
        self.save(path)
        return task["attempts"]

    # -------------------------------------------------------------------------
    # Counts
    # -------------------------------------------------------------------------

    def count_tasks(self) -> dict:
        total = done = blocked = pending = 0
        for _, _, _, task in self._all_tasks():
            total += 1
            status = task.get("status", "pending")
            if status == "done":
                done += 1
            elif status == "blocked":
                blocked += 1
            else:
                pending += 1
        return {"total": total, "done": done, "blocked": blocked, "pending": pending}

    def count_stories(self) -> dict:
        total = sum(
            1
            for phase in self.data.get("phases", [])
            for epic in phase.get("epics", [])
            for _ in epic.get("stories", [])
        )
        return {"total": total}

    def count_epics(self) -> dict:
        total = sum(
            1
            for phase in self.data.get("phases", [])
            for _ in phase.get("epics", [])
        )
        return {"total": total}

    # -------------------------------------------------------------------------
    # Phase state
    # -------------------------------------------------------------------------

    def current_phase(self) -> Optional[dict]:
        for phase in self.data.get("phases", []):
            for epic in phase.get("epics", []):
                for story in epic.get("stories", []):
                    for task in story.get("tasks", []):
                        if task.get("status", "pending") == "pending":
                            return phase
        return None

    def is_phase_complete(self, phase_id: str) -> bool:
        for phase in self.data.get("phases", []):
            if phase.get("id") == phase_id:
                for epic in phase.get("epics", []):
                    for story in epic.get("stories", []):
                        for task in story.get("tasks", []):
                            if task.get("status", "pending") == "pending":
                                return False
                return True
        return False

    # -------------------------------------------------------------------------
    # DAG validation
    # -------------------------------------------------------------------------

    def validate_dag(self) -> dict:
        all_task_ids = {task["id"] for _, _, _, task in self._all_tasks()}
        errors = []

        task_phase = {}
        for i, phase in enumerate(self.data.get("phases", [])):
            for epic in phase.get("epics", []):
                for story in epic.get("stories", []):
                    for task in story.get("tasks", []):
                        task_phase[task["id"]] = i

        adj = {}
        for _, _, _, task in self._all_tasks():
            tid = task["id"]
            deps = task.get("depends_on", [])
            adj[tid] = deps
            for dep in deps:
                if dep not in all_task_ids:
                    errors.append(f"Task '{tid}' depends on non-existent task '{dep}'")
                else:
                    my_phase = task_phase.get(tid, -1)
                    dep_phase = task_phase.get(dep, -1)
                    if dep_phase > my_phase:
                        errors.append(
                            f"Task '{tid}' (phase {my_phase}) has backward cross-phase dep on "
                            f"'{dep}' (phase {dep_phase})"
                        )

        WHITE, GRAY, BLACK = 0, 1, 2
        color = {tid: WHITE for tid in all_task_ids}
        cycle_tasks = []

        def dfs(node: str, path: list) -> bool:
            color[node] = GRAY
            path.append(node)
            for neighbor in adj.get(node, []):
                if neighbor not in all_task_ids:
                    continue
                if color[neighbor] == GRAY:
                    cycle_start = path.index(neighbor)
                    cycle_tasks.extend(path[cycle_start:])
                    return True
                if color[neighbor] == WHITE:
                    if dfs(neighbor, path):
                        return True
            path.pop()
            color[node] = BLACK
            return False

        for tid in list(all_task_ids):
            if color[tid] == WHITE:
                if dfs(tid, []):
                    break

        if cycle_tasks:
            errors.append(f"Cycle detected involving tasks: {cycle_tasks}")

        return {"valid": len(errors) == 0, "errors": errors}

    # -------------------------------------------------------------------------
    # Dependency check
    # -------------------------------------------------------------------------

    def are_deps_satisfied(self, task_id: str) -> bool:
        task = self.get_task(task_id)
        if task is None:
            return False
        for dep_id in task.get("depends_on", []):
            dep = self.get_task(dep_id)
            if dep is None or dep.get("status") != "done":
                return False
        return True

    # -------------------------------------------------------------------------
    # Backward compat
    # -------------------------------------------------------------------------

    def sync_from_feature_list(self, feature_list_path: Path, work_plan_path: Path) -> int:
        if not feature_list_path.exists():
            return 0
        try:
            features = _json.loads(feature_list_path.read_text(encoding="utf-8"))
        except (_json.JSONDecodeError, OSError):
            return 0

        newly_done = 0
        for feat in features:
            task = self.get_task(feat.get("id", ""))
            if task is None:
                continue
            if feat.get("passes") and task.get("status") != "done":
                task["status"] = "done"
                newly_done += 1
            if feat.get("blocked") and task.get("status") != "blocked":
                task["status"] = "blocked"
                task["blocked_reason"] = feat.get("block_reason", "marked by generator")

        if newly_done > 0:
            self.save(work_plan_path)
        return newly_done

    def sync_feature_list(self, feature_list_path: Path) -> None:
        features = []
        priority = 1
        for phase, epic, story, task in self._all_tasks():
            features.append({
                "id": task["id"],
                "priority": priority,
                "category": phase.get("name", "feature"),
                "depends_on": task.get("depends_on", []),
                "description": task.get("description", ""),
                "acceptance_criteria": task.get("acceptance_criteria", []),
                "steps": task.get("steps", []),
                "passes": task.get("status") == "done",
                "blocked": task.get("status") == "blocked",
                "retries": task.get("attempts", 0),
            })
            priority += 1
        atomic_write(feature_list_path, features)

    @classmethod
    def from_flat_features(cls, features: list) -> "WorkPlan":
        tasks = []
        for feat in features:
            if feat.get("passes"):
                status = "done"
            elif feat.get("blocked"):
                status = "blocked"
            else:
                status = "pending"
            tasks.append({
                "id": feat.get("id", ""),
                "description": feat.get("description", ""),
                "acceptance_criteria": feat.get("acceptance_criteria", []),
                "steps": feat.get("steps", []),
                "depends_on": feat.get("depends_on", []),
                "status": status,
                "attempts": feat.get("retries", 0),
                "blocked_reason": feat.get("block_reason", None),
            })

        data = {
            "phases": [{
                "id": "phase-0",
                "name": "Features",
                "epics": [{
                    "id": "epic-001",
                    "name": "All Features",
                    "stories": [{
                        "id": "story-001",
                        "name": "Feature Implementation",
                        "tasks": tasks,
                    }],
                }],
            }]
        }
        return cls(data)

    # -------------------------------------------------------------------------
    # target_files conflict detection (NEW)
    # -------------------------------------------------------------------------

    def detect_file_conflicts(self) -> list:
        """Find tasks that share target_files.

        Returns list of {file, task_ids} dicts for each file touched by 2+ tasks.
        """
        file_to_tasks = {}
        for _, _, _, task in self._all_tasks():
            for f in task.get("target_files", []):
                file_to_tasks.setdefault(f, []).append(task["id"])

        return [
            {"file": f, "task_ids": tids}
            for f, tids in file_to_tasks.items()
            if len(tids) > 1
        ]

    def auto_fix_conflicts(self) -> dict:
        """Add depends_on edges to chain tasks sharing target_files.

        For each file touched by multiple tasks (in document order), ensures
        each subsequent task depends on the previous one. Skips if the
        dependency already exists or would create a cycle.

        Returns {conflicts_found: int, deps_added: int}.
        """
        file_to_tasks = {}
        # Collect in document order
        task_order = []
        for _, _, _, task in self._all_tasks():
            task_order.append(task["id"])
            for f in task.get("target_files", []):
                file_to_tasks.setdefault(f, []).append(task["id"])

        conflicts_found = 0
        deps_added = 0

        for f, task_ids in file_to_tasks.items():
            if len(task_ids) < 2:
                continue
            conflicts_found += 1
            for i in range(1, len(task_ids)):
                prev_id = task_ids[i - 1]
                curr_id = task_ids[i]
                curr_task = self.get_task(curr_id)
                if curr_task is None:
                    continue
                if prev_id in curr_task.get("depends_on", []):
                    continue
                # Check if adding this dep would create a cycle
                if self._would_create_cycle(curr_id, prev_id):
                    continue
                curr_task.setdefault("depends_on", []).append(prev_id)
                deps_added += 1

        return {"conflicts_found": conflicts_found, "deps_added": deps_added}

    def _would_create_cycle(self, from_id: str, to_id: str) -> bool:
        """Check if adding from_id -> to_id dependency would create a cycle.

        Returns True if to_id can already reach from_id through existing deps.
        """
        visited = set()

        def dfs(node):
            if node == from_id:
                return True
            if node in visited:
                return False
            visited.add(node)
            task = self.get_task(node)
            if task is None:
                return False
            for dep in task.get("depends_on", []):
                if dfs(dep):
                    return True
            return False

        return dfs(to_id)
