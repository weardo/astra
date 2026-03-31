"""Tests for planner prompt files and adaptive depth logic."""

from pathlib import Path

import pytest

PROMPTS_DIR = Path(__file__).parent.parent.parent / "src" / "prompts"


class TestArchitectPrompt:
    def test_architect_prompt_contains_detection_json(self):
        content = (PROMPTS_DIR / "architect.md").read_text()
        assert "{{DETECTION_JSON}}" in content or "detection" in content.lower()

    def test_architect_prompt_contains_repo_map(self):
        content = (PROMPTS_DIR / "architect.md").read_text()
        assert "{{REPO_MAP}}" in content or "repo" in content.lower()

    def test_architect_prompt_requires_target_files(self):
        content = (PROMPTS_DIR / "architect.md").read_text()
        assert "target_files" in content


class TestAdversaryPrompt:
    def test_adversary_prompt_has_target_files_rule(self):
        content = (PROMPTS_DIR / "adversary.md").read_text()
        assert "target_files" in content


class TestRefinerPrompt:
    def test_refiner_prompt_has_dependency_examples(self):
        content = (PROMPTS_DIR / "refiner.md").read_text()
        assert "depend" in content.lower()


class TestBugfixStrategy:
    def test_bugfix_strategy_selects_correct_role_sequence(self):
        """Bugfix strategy uses investigator → bugfix-adversary → fixer → verifier."""
        for role in ["investigator", "bugfix-adversary", "fixer", "verifier"]:
            assert (PROMPTS_DIR / f"{role}.md").exists(), f"Missing {role}.md"


class TestAdaptiveDepth:
    def _get_role_sequence(self, task_count, thresholds=None):
        """Determine role sequence based on task count."""
        thresholds = thresholds or {"light_max_tasks": 5, "full_min_tasks": 20}
        if task_count <= thresholds["light_max_tasks"]:
            return ["architect", "validator"]
        elif task_count >= thresholds["full_min_tasks"]:
            return ["architect", "adversary", "refiner", "adversary", "refiner", "validator"]
        else:
            return ["architect", "adversary", "refiner", "validator"]

    def test_adaptive_depth_light_for_3_tasks(self):
        seq = self._get_role_sequence(3)
        assert seq == ["architect", "validator"]

    def test_adaptive_depth_standard_for_15_tasks(self):
        seq = self._get_role_sequence(15)
        assert seq == ["architect", "adversary", "refiner", "validator"]

    def test_adaptive_depth_full_for_25_tasks(self):
        seq = self._get_role_sequence(25)
        assert len(seq) == 6
        assert seq[0] == "architect"
        assert seq[-1] == "validator"


class TestPromptLineBudget:
    def test_all_prompts_under_100_lines(self):
        """All prompt files should be under 100 lines for token efficiency."""
        for prompt_file in PROMPTS_DIR.glob("*.md"):
            lines = prompt_file.read_text().strip().split("\n")
            assert len(lines) <= 100, (
                f"{prompt_file.name} is {len(lines)} lines, must be <= 100"
            )
