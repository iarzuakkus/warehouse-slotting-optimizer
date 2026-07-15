"""Siparişlerde sık geçen ürün kümelerini FP-Growth ile bulur."""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from math import ceil


@dataclass(frozen=True)
class FrequentItemset:
    items: tuple[str, ...]
    support_count: int
    support: float


@dataclass(frozen=True)
class AssociationRule:
    antecedent: tuple[str, ...]
    consequent: tuple[str, ...]
    support: float
    confidence: float
    lift: float


@dataclass
class _FPNode:
    item: str | None
    count: int = 0
    parent: "_FPNode | None" = None
    children: dict[str, "_FPNode"] = field(default_factory=dict)


def _build_tree(
    weighted_transactions: list[tuple[list[str], int]],
    minimum_count: int,
) -> tuple[_FPNode, dict[str, list[_FPNode]], Counter[str]]:
    frequencies: Counter[str] = Counter()
    for items, weight in weighted_transactions:
        for item in set(items):
            frequencies[item] += weight
    frequencies = Counter(
        {
            item: count
            for item, count in frequencies.items()
            if count >= minimum_count
        }
    )

    root = _FPNode(item=None)
    header: dict[str, list[_FPNode]] = defaultdict(list)
    for items, weight in weighted_transactions:
        ordered_items = sorted(
            {item for item in items if item in frequencies},
            key=lambda item: (-frequencies[item], item),
        )
        current = root
        for item in ordered_items:
            child = current.children.get(item)
            if child is None:
                child = _FPNode(item=item, parent=current)
                current.children[item] = child
                header[item].append(child)
            child.count += weight
            current = child
    return root, dict(header), frequencies


def _mine_tree(
    header: dict[str, list[_FPNode]],
    frequencies: Counter[str],
    minimum_count: int,
    prefix: frozenset[str],
    output: dict[frozenset[str], int],
) -> None:
    for item in sorted(frequencies, key=lambda value: (frequencies[value], value)):
        pattern = prefix | {item}
        output[pattern] = frequencies[item]

        conditional_transactions: list[tuple[list[str], int]] = []
        for node in header[item]:
            path: list[str] = []
            parent = node.parent
            while parent is not None and parent.item is not None:
                path.append(parent.item)
                parent = parent.parent
            if path:
                conditional_transactions.append((list(reversed(path)), node.count))

        if not conditional_transactions:
            continue
        _, conditional_header, conditional_frequencies = _build_tree(
            conditional_transactions,
            minimum_count,
        )
        if conditional_frequencies:
            _mine_tree(
                conditional_header,
                conditional_frequencies,
                minimum_count,
                pattern,
                output,
            )


def mine_frequent_itemsets(
    transactions: list[set[str]],
    minimum_support: float = 0.05,
    maximum_length: int | None = None,
) -> list[FrequentItemset]:
    """Minimum destek oranını geçen benzersiz ürün kümelerini döndürür."""
    if not 0 < minimum_support <= 1:
        raise ValueError("minimum_support must satisfy 0 < value <= 1")
    if maximum_length is not None and maximum_length <= 0:
        raise ValueError("maximum_length must be positive")
    if not transactions:
        return []

    normalized_transactions = [set(transaction) for transaction in transactions]
    minimum_count = ceil(minimum_support * len(normalized_transactions))
    _, header, frequencies = _build_tree(
        [(list(transaction), 1) for transaction in normalized_transactions],
        minimum_count,
    )
    patterns: dict[frozenset[str], int] = {}
    _mine_tree(
        header,
        frequencies,
        minimum_count,
        frozenset(),
        patterns,
    )

    results = [
        FrequentItemset(
            items=tuple(sorted(items)),
            support_count=count,
            support=count / len(normalized_transactions),
        )
        for items, count in patterns.items()
        if maximum_length is None or len(items) <= maximum_length
    ]
    return sorted(
        results,
        key=lambda result: (-result.support_count, len(result.items), result.items),
    )


def generate_association_rules(
    itemsets: list[FrequentItemset],
    transaction_count: int,
    minimum_confidence: float = 0.30,
    minimum_lift: float = 1.0,
) -> list[AssociationRule]:
    """Sık ürün kümelerinden confidence ve lift değerli kurallar üretir."""
    if transaction_count <= 0:
        raise ValueError("transaction_count must be positive")
    if not 0 < minimum_confidence <= 1:
        raise ValueError("minimum_confidence must satisfy 0 < value <= 1")
    if minimum_lift < 0:
        raise ValueError("minimum_lift cannot be negative")

    support_counts = {
        frozenset(itemset.items): itemset.support_count for itemset in itemsets
    }
    rules: list[AssociationRule] = []
    for itemset in itemsets:
        items = frozenset(itemset.items)
        if len(items) < 2:
            continue
        sorted_items = sorted(items)
        for antecedent_length in range(1, len(items)):
            for antecedent_tuple in combinations(
                sorted_items,
                antecedent_length,
            ):
                antecedent = frozenset(antecedent_tuple)
                consequent = items - antecedent
                antecedent_count = support_counts.get(antecedent)
                consequent_count = support_counts.get(consequent)
                if antecedent_count is None or consequent_count is None:
                    continue

                confidence = itemset.support_count / antecedent_count
                consequent_support = consequent_count / transaction_count
                lift = confidence / consequent_support
                if confidence < minimum_confidence or lift < minimum_lift:
                    continue
                rules.append(
                    AssociationRule(
                        antecedent=tuple(sorted(antecedent)),
                        consequent=tuple(sorted(consequent)),
                        support=itemset.support_count / transaction_count,
                        confidence=confidence,
                        lift=lift,
                    )
                )

    return sorted(
        rules,
        key=lambda rule: (
            -rule.lift,
            -rule.confidence,
            -rule.support,
            rule.antecedent,
            rule.consequent,
        ),
    )
