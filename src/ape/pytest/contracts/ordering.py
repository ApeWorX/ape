"""Ordering and chain wiring for ``@custom:ape-test-after``."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import TYPE_CHECKING

import pytest

from .types import TestModifier

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .functional import ContractTestItem


def method_base_name(item: ContractTestItem) -> str:
    """ABI method name, ignoring parametrize suffix on ``item.name``."""
    return item.abi.name


def matches_after_target(item: ContractTestItem, target: str) -> bool:
    """True if ``item`` is the (possibly parametrized) method named ``target``."""
    if item.name == target or method_base_name(item) == target:
        return True
    return item.name.startswith(f"{target}[")


def validate_after_arg(raw: object, item_label: str) -> str:
    """Require a single predecessor method name."""
    if isinstance(raw, (list, tuple, set)):
        values = [str(v).strip() for v in raw if str(v).strip()]
        if len(values) > 1:
            raise pytest.UsageError(
                f"{item_label}: @custom:ape-test-after allows a single parent only, got {values!r}."
            )
        if not values:
            raise pytest.UsageError(f"{item_label}: @custom:ape-test-after requires a test name.")
        return values[0]

    if not isinstance(raw, str) or not raw.strip():
        raise pytest.UsageError(
            f"{item_label}: @custom:ape-test-after requires a single test name, got {raw!r}."
        )

    if "," in raw:
        raise pytest.UsageError(
            f"{item_label}: @custom:ape-test-after allows a single parent only, got {raw!r}."
        )

    return raw.strip()


def resolve_predecessor(
    item: ContractTestItem,
    siblings: Iterable[ContractTestItem],
) -> ContractTestItem | None:
    """
    Resolve ``TEST_AFTER`` to exactly one sibling item.

    Returns ``None`` when the item has no ``TEST_AFTER`` modifier.
    """
    raw = item.modifiers.get(TestModifier.TEST_AFTER)
    if raw is None:
        return None

    target = validate_after_arg(raw, item.nodeid)
    matches = [sib for sib in siblings if sib is not item and matches_after_target(sib, target)]
    if not matches:
        raise pytest.UsageError(
            f"{item.nodeid}: @custom:ape-test-after '{target}' does not match any test "
            f"in the same contract module."
        )
    if len(matches) > 1:
        names = ", ".join(m.name for m in matches)
        raise pytest.UsageError(
            f"{item.nodeid}: @custom:ape-test-after '{target}' is ambiguous "
            f"(matches: {names}). Use a unique method name or a specific parametrized id."
        )
    return matches[0]


def topological_sort(items: list[ContractTestItem]) -> list[ContractTestItem]:
    """
    Stable topological sort of ``items`` by ``TEST_AFTER`` edges.

    Unrelated items keep their relative order. Cycles raise ``pytest.UsageError``.
    Also wires ``predecessor_item``, ``chain_root``, and ``chain_dependents`` on each item.
    """
    if not items:
        return items

    preds: dict[str, ContractTestItem | None] = {}
    children: dict[str, list[ContractTestItem]] = defaultdict(list)
    by_nodeid = {it.nodeid: it for it in items}

    for item in items:
        item.predecessor_item = None
        item.chain_root = item
        item.chain_dependents = []
        item._ape_test_outcome = None
        item._chain_snapshot_id = None
        item._chain_pending = None

        pred = resolve_predecessor(item, items)
        preds[item.nodeid] = pred
        if pred is not None:
            item.predecessor_item = pred
            children[pred.nodeid].append(item)

    # Kahn topo-sort; stable among ready nodes by original index.
    index = {it.nodeid: i for i, it in enumerate(items)}
    indegree = {it.nodeid: (1 if preds[it.nodeid] is not None else 0) for it in items}
    ready = deque(
        sorted(
            (it for it in items if indegree[it.nodeid] == 0),
            key=lambda x: index[x.nodeid],
        )
    )
    ordered: list[ContractTestItem] = []

    while ready:
        node = ready.popleft()
        ordered.append(node)
        for child in sorted(children[node.nodeid], key=lambda x: index[x.nodeid]):
            indegree[child.nodeid] -= 1
            if indegree[child.nodeid] == 0:
                ready.append(child)

    if len(ordered) != len(items):
        cyclic = [by_nodeid[n].name for n, d in indegree.items() if d > 0]
        raise pytest.UsageError(
            "Cycle detected in @custom:ape-test-after dependencies among: "
            + ", ".join(sorted(cyclic))
        )

    for item in ordered:
        root = item
        while root.predecessor_item is not None:
            root = root.predecessor_item
        item.chain_root = root

    for item in ordered:
        if item.predecessor_item is None:
            desc: list[ContractTestItem] = []
            stack = list(children[item.nodeid])
            while stack:
                cur = stack.pop()
                desc.append(cur)
                stack.extend(children[cur.nodeid])
            item.chain_dependents = desc
            pending = {item.nodeid, *(d.nodeid for d in desc)}
            item._chain_pending = pending
            for d in desc:
                d._chain_pending = pending

    return ordered


def reorder_contract_test_items(items: list) -> None:
    """
    In-place reorder of pytest ``session.items`` so ``TEST_AFTER`` predecessors
    run first within each ``ContractTestModule``.
    """
    from .functional import ContractTestItem

    groups: dict[int, list[ContractTestItem]] = defaultdict(list)
    for it in items:
        if isinstance(it, ContractTestItem):
            groups[id(it.parent)].append(it)

    if not groups:
        return

    sorted_groups = {key: topological_sort(group) for key, group in groups.items()}

    emitted: set[int] = set()
    new_items: list = []
    for it in items:
        if not isinstance(it, ContractTestItem):
            new_items.append(it)
            continue
        key = id(it.parent)
        if key in emitted:
            continue
        new_items.extend(sorted_groups[key])
        emitted.add(key)

    items[:] = new_items
