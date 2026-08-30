"""Static validation for the versioned cuisine discovery seed."""

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast


SEED_PATH = Path(__file__).resolve().parents[1] / "app" / "data" / "cuisines" / "v1.json"


def _normalise(value: str) -> str:
    return " ".join(value.casefold().split())


def _seed() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(SEED_PATH.read_text()))


def _assert_acyclic(node_ids: Iterable[str], parents: dict[str, list[str]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        assert node_id not in visiting, f"Cycle detected at {node_id}"
        if node_id in visited:
            return

        visiting.add(node_id)
        for parent_id in parents[node_id]:
            visit(parent_id)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in node_ids:
        visit(node_id)


def test_v1_seed_has_unique_ids_aliases_and_an_acyclic_graph() -> None:
    seed = _seed()
    nodes = seed["nodes"]
    edges = seed["edges"]

    node_ids = [node["id"] for node in nodes]
    assert len(node_ids) == len(set(node_ids))

    aliases: dict[str, str] = {}
    for node in nodes:
        for value in [node["name"], *node["aliases"]]:
            normalised = _normalise(value)
            existing = aliases.setdefault(normalised, node["id"])
            assert existing == node["id"], f"Ambiguous alias {value!r}: {existing}, {node['id']}"

    parents = {node_id: [] for node_id in node_ids}
    assert len(edges) == len({tuple(edge) for edge in edges})
    for child_id, parent_id in edges:
        assert child_id in parents
        assert parent_id in parents
        parents[child_id].append(parent_id)

    _assert_acyclic(node_ids, parents)

    source_ids = set(seed["sources"])
    assert set(seed["default_provenance"]).issubset(source_ids)
