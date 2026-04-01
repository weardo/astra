"""
Parallel Agent Teams
=====================

Groups tasks by dependency layers for parallel execution.
Worktree lifecycle is handled by Claude Code's native `isolation: "worktree"`.
"""

from collections import defaultdict


def group_by_dependency(features: list) -> list[list[dict]]:
    """Group features into dependency layers for parallel execution.

    Features with no dependencies go in layer 0.
    Features depending on layer 0 features go in layer 1, etc.

    Returns list of layers, where each layer is a list of features
    that can be executed in parallel.
    """
    if not features:
        return []

    # Build dependency graph
    id_to_feature = {f["id"]: f for f in features}
    remaining = {f["id"] for f in features if not f.get("passes") and not f.get("blocked")}

    # Track which features are resolved (passed, blocked, or already assigned to a layer)
    resolved = {f["id"] for f in features if f.get("passes") or f.get("blocked")}

    layers = []
    max_iterations = len(features) + 1  # Prevent infinite loop on circular deps

    for _ in range(max_iterations):
        if not remaining:
            break

        # Find features whose dependencies are all resolved
        layer = []
        for fid in list(remaining):
            feature = id_to_feature[fid]
            deps = feature.get("depends_on", [])
            if all(d in resolved for d in deps):
                layer.append(feature)

        if not layer:
            # Circular dependency or unresolvable — put remaining in final layer
            layer = [id_to_feature[fid] for fid in remaining]
            layers.append(layer)
            break

        layers.append(layer)
        for f in layer:
            remaining.discard(f["id"])
            resolved.add(f["id"])

    return layers
