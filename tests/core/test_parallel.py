"""Tests for parallel.py -- dependency grouping."""

import pytest

from src.core.parallel import group_by_dependency


class TestGroupByDependency:
    def test_empty_features(self):
        assert group_by_dependency([]) == []

    def test_all_independent(self):
        features = [
            {"id": "001", "depends_on": [], "passes": False, "blocked": False},
            {"id": "002", "depends_on": [], "passes": False, "blocked": False},
            {"id": "003", "depends_on": [], "passes": False, "blocked": False},
        ]
        layers = group_by_dependency(features)
        assert len(layers) == 1
        assert len(layers[0]) == 3

    def test_linear_chain(self):
        features = [
            {"id": "001", "depends_on": [], "passes": False, "blocked": False},
            {"id": "002", "depends_on": ["001"], "passes": False, "blocked": False},
            {"id": "003", "depends_on": ["002"], "passes": False, "blocked": False},
        ]
        layers = group_by_dependency(features)
        assert len(layers) == 3
        assert layers[0][0]["id"] == "001"
        assert layers[1][0]["id"] == "002"
        assert layers[2][0]["id"] == "003"

    def test_diamond_dependency(self):
        features = [
            {"id": "001", "depends_on": [], "passes": False, "blocked": False},
            {"id": "002", "depends_on": ["001"], "passes": False, "blocked": False},
            {"id": "003", "depends_on": ["001"], "passes": False, "blocked": False},
            {"id": "004", "depends_on": ["002", "003"], "passes": False, "blocked": False},
        ]
        layers = group_by_dependency(features)
        assert len(layers) == 3
        assert layers[0][0]["id"] == "001"
        layer1_ids = {f["id"] for f in layers[1]}
        assert layer1_ids == {"002", "003"}
        assert layers[2][0]["id"] == "004"

    def test_skips_passing_features(self):
        features = [
            {"id": "001", "depends_on": [], "passes": True, "blocked": False},
            {"id": "002", "depends_on": ["001"], "passes": False, "blocked": False},
        ]
        layers = group_by_dependency(features)
        assert len(layers) == 1
        assert layers[0][0]["id"] == "002"

    def test_skips_blocked_features(self):
        features = [
            {"id": "001", "depends_on": [], "passes": False, "blocked": True},
            {"id": "002", "depends_on": [], "passes": False, "blocked": False},
        ]
        layers = group_by_dependency(features)
        assert len(layers) == 1
        assert layers[0][0]["id"] == "002"

    def test_resolved_deps_count(self):
        """Features depending on already-passed features go in layer 0."""
        features = [
            {"id": "001", "depends_on": [], "passes": True, "blocked": False},
            {"id": "002", "depends_on": ["001"], "passes": False, "blocked": False},
            {"id": "003", "depends_on": [], "passes": False, "blocked": False},
        ]
        layers = group_by_dependency(features)
        assert len(layers) == 1
        layer_ids = {f["id"] for f in layers[0]}
        assert layer_ids == {"002", "003"}

    def test_mixed_depths(self):
        features = [
            {"id": "001", "depends_on": [], "passes": False, "blocked": False},
            {"id": "002", "depends_on": [], "passes": False, "blocked": False},
            {"id": "003", "depends_on": ["001"], "passes": False, "blocked": False},
            {"id": "004", "depends_on": ["001", "002"], "passes": False, "blocked": False},
            {"id": "005", "depends_on": ["003"], "passes": False, "blocked": False},
        ]
        layers = group_by_dependency(features)
        assert len(layers) == 3
        layer0_ids = {f["id"] for f in layers[0]}
        assert layer0_ids == {"001", "002"}
        layer1_ids = {f["id"] for f in layers[1]}
        assert layer1_ids == {"003", "004"}
        assert layers[2][0]["id"] == "005"
