"""Apriori and FP-Growth implementations for invoice-level market baskets."""

from __future__ import annotations

from itertools import combinations
from math import ceil
from typing import Iterable

Itemset = frozenset[str]


def _prepare_transactions(transactions: Iterable[Iterable[str]]) -> list[Itemset]:
    baskets = [frozenset(item for item in basket if item) for basket in transactions]
    if not baskets:
        raise ValueError("At least one transaction is required.")
    return baskets


def _minimum_count(min_support: float, transaction_count: int) -> int:
    if not 0 < min_support <= 1:
        raise ValueError("min_support must be greater than 0 and at most 1.")
    return ceil(min_support * transaction_count)


def apriori(transactions: Iterable[Iterable[str]], min_support: float) -> dict[Itemset, int]:
    """Return frequent itemsets mapped to their transaction counts."""
    baskets = _prepare_transactions(transactions)
    minimum = _minimum_count(min_support, len(baskets))
    single_counts: dict[str, int] = {}
    item_transactions: dict[str, set[int]] = {}
    for transaction_id, basket in enumerate(baskets):
        for item in basket:
            single_counts[item] = single_counts.get(item, 0) + 1
            item_transactions.setdefault(item, set()).add(transaction_id)

    frequent: dict[Itemset, int] = {
        frozenset((item,)): count
        for item, count in single_counts.items()
        if count >= minimum
    }
    all_frequent = dict(frequent)
    previous = set(frequent)
    size = 2
    while previous:
        ordered_previous = sorted(previous, key=lambda itemset: tuple(sorted(itemset)))
        candidates: set[Itemset] = set()
        for left, right in combinations(ordered_previous, 2):
            candidate = left | right
            if len(candidate) == size and all(
                frozenset(subset) in previous
                for subset in combinations(sorted(candidate), size - 1)
            ):
                candidates.add(candidate)
        if not candidates:
            break
        counts: dict[Itemset, int] = {}
        for candidate in candidates:
            ordered_items = sorted(candidate, key=lambda item: len(item_transactions[item]))
            least_common = item_transactions[ordered_items[0]]
            counts[candidate] = sum(
                all(transaction_id in item_transactions[item] for item in ordered_items[1:])
                for transaction_id in least_common
            )
        frequent = {itemset: count for itemset, count in counts.items() if count >= minimum}
        all_frequent.update(frequent)
        previous = set(frequent)
        size += 1
    return all_frequent


class _Node:
    def __init__(self, item: str | None, parent: _Node | None) -> None:
        self.item = item
        self.parent = parent
        self.count = 0
        self.children: dict[str, _Node] = {}
        self.next_same_item: _Node | None = None


def _build_tree(
    weighted_paths: Iterable[tuple[list[str], int]], minimum: int
) -> tuple[_Node | None, dict[str, tuple[int, _Node | None]]]:
    paths = list(weighted_paths)
    frequencies: dict[str, int] = {}
    for path, weight in paths:
        for item in set(path):
            frequencies[item] = frequencies.get(item, 0) + weight
    frequencies = {item: count for item, count in frequencies.items() if count >= minimum}
    if not frequencies:
        return None, {}

    root = _Node(None, None)
    header: dict[str, tuple[int, _Node | None]] = {
        item: (count, None) for item, count in frequencies.items()
    }
    tails: dict[str, _Node] = {}
    for path, weight in paths:
        ordered = sorted(
            (item for item in path if item in frequencies),
            key=lambda item: (-frequencies[item], item),
        )
        current = root
        for item in ordered:
            child = current.children.get(item)
            if child is None:
                child = _Node(item, current)
                current.children[item] = child
                count, first = header[item]
                if first is None:
                    header[item] = (count, child)
                else:
                    tails[item].next_same_item = child
                tails[item] = child
            child.count += weight
            current = child
    return root, header


def fpgrowth(transactions: Iterable[Iterable[str]], min_support: float) -> dict[Itemset, int]:
    """Return frequent itemsets using an FP-tree and conditional pattern bases."""
    baskets = _prepare_transactions(transactions)
    minimum = _minimum_count(min_support, len(baskets))
    initial_paths = [(list(basket), 1) for basket in baskets]
    all_frequent: dict[Itemset, int] = {}

    def mine(weighted_paths: list[tuple[list[str], int]], prefix: Itemset) -> None:
        _, header = _build_tree(weighted_paths, minimum)
        for item, (count, first_node) in sorted(
            header.items(), key=lambda entry: (entry[1][0], entry[0])
        ):
            pattern = prefix | frozenset((item,))
            all_frequent[pattern] = count
            conditional_paths: list[tuple[list[str], int]] = []
            node = first_node
            while node is not None:
                ancestors: list[str] = []
                parent = node.parent
                while parent is not None and parent.item is not None:
                    ancestors.append(parent.item)
                    parent = parent.parent
                if ancestors:
                    conditional_paths.append((ancestors, node.count))
                node = node.next_same_item
            if conditional_paths:
                mine(conditional_paths, pattern)

    mine(initial_paths, frozenset())
    return all_frequent


def association_rules(
    frequent_itemsets: dict[Itemset, int],
    transaction_count: int,
    min_confidence: float,
) -> list[dict[str, object]]:
    """Generate directed rules with support, confidence, and lift."""
    if not 0 <= min_confidence <= 1:
        raise ValueError("min_confidence must be between 0 and 1.")
    rules: list[dict[str, object]] = []
    for itemset, itemset_count in frequent_itemsets.items():
        if len(itemset) < 2:
            continue
        for size in range(1, len(itemset)):
            for antecedent_tuple in combinations(sorted(itemset), size):
                antecedent = frozenset(antecedent_tuple)
                consequent = itemset - antecedent
                antecedent_count = frequent_itemsets.get(antecedent)
                consequent_count = frequent_itemsets.get(consequent)
                if not antecedent_count or not consequent_count:
                    continue
                confidence = itemset_count / antecedent_count
                if confidence < min_confidence:
                    continue
                rules.append(
                    {
                        "antecedent": " | ".join(sorted(antecedent)),
                        "consequent": " | ".join(sorted(consequent)),
                        "support_count": itemset_count,
                        "support": itemset_count / transaction_count,
                        "confidence": confidence,
                        "lift": confidence / (consequent_count / transaction_count),
                    }
                )
    return sorted(rules, key=lambda rule: (-float(rule["lift"]), str(rule["antecedent"])))
