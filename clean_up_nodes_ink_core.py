"""
Core path-node cleanup logic that does not depend on inkex.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from typing import List, Sequence


Node = Sequence[Sequence[float]]
Subpath = Sequence[Node]

TOLERANCE_LEVEL_PIXELS = {
    "weak": 4.0,
    "medium_weak": 6.0,
    "medium": 8.0,
    "medium_strong": 10.0,
    "strong": 12.0,
}


@dataclass(frozen=True)
class SubpathCleanupResult:
    subpath: List[List[List[float]]]
    nodetypes: str
    removed_nodes: int


@dataclass(frozen=True)
class DuplicateCandidate:
    first_index: int
    second_index: int
    distance: float


def normalize_tolerance_level(name: str) -> str:
    return name if name in TOLERANCE_LEVEL_PIXELS else "medium"


def tolerance_radius_for_level(level: str = "medium") -> float:
    return TOLERANCE_LEVEL_PIXELS[normalize_tolerance_level(level)]


def clean_duplicate_nodes_in_subpath(
    subpath: Subpath,
    tolerance: float,
    closed: bool = False,
    nodetypes: Sequence[str] | None = None,
    reference_subpath: Subpath | None = None,
) -> SubpathCleanupResult:
    resolved_nodetypes = resolve_nodetypes(nodetypes, len(subpath))
    resolved_reference = resolve_reference_subpath(reference_subpath, subpath)
    if len(subpath) < 2:
        return SubpathCleanupResult(
            [clone_node(node) for node in subpath],
            "".join(resolved_nodetypes),
            0,
        )

    cleaned: List[List[List[float]]] = [clone_node(subpath[0])]
    cleaned_reference: List[List[List[float]]] = [clone_node(resolved_reference[0])]
    cleaned_nodetypes = [resolved_nodetypes[0]]
    removed = 0

    for index, raw_node in enumerate(subpath[1:], start=1):
        node = clone_node(raw_node)
        reference_node = clone_node(resolved_reference[index])
        if nodes_form_collapsible_segment(
            cleaned_reference[-1], reference_node, tolerance
        ):
            cleaned[-1] = merge_duplicate_nodes(cleaned[-1], node)
            cleaned_reference[-1] = merge_duplicate_nodes(
                cleaned_reference[-1], reference_node
            )
            cleaned_nodetypes[-1] = "c"
            removed += 1
        else:
            cleaned.append(node)
            cleaned_reference.append(reference_node)
            cleaned_nodetypes.append(resolved_nodetypes[index])

    if closed and len(cleaned) > 1 and nodes_form_collapsible_segment(
        cleaned_reference[-1], cleaned_reference[0], tolerance
    ):
        cleaned[0] = merge_duplicate_nodes(cleaned[-1], cleaned[0])
        cleaned_reference[0] = merge_duplicate_nodes(
            cleaned_reference[-1], cleaned_reference[0]
        )
        cleaned.pop()
        cleaned_reference.pop()
        cleaned_nodetypes[0] = "c"
        cleaned_nodetypes.pop()
        removed += 1

    return SubpathCleanupResult(cleaned, "".join(cleaned_nodetypes), removed)


def merge_duplicate_nodes(_first: Node, second: Node) -> List[List[float]]:
    first = clone_node(_first)
    second = clone_node(second)

    anchor = first[1][:]
    incoming = translate_point(anchor, vector_between(first[1], first[0]))
    outgoing = translate_point(anchor, vector_between(second[1], second[2]))
    return [incoming, anchor, outgoing]


def clone_node(node: Node) -> List[List[float]]:
    return [[float(point[0]), float(point[1])] for point in node]


def resolve_reference_subpath(
    reference_subpath: Subpath | None, fallback_subpath: Subpath
) -> List[List[List[float]]]:
    if reference_subpath is None:
        return [clone_node(node) for node in fallback_subpath]

    resolved = [clone_node(node) for node in reference_subpath]
    if len(resolved) != len(fallback_subpath):
        return [clone_node(node) for node in fallback_subpath]
    return resolved


def resolve_nodetypes(nodetypes: Sequence[str] | None, count: int) -> List[str]:
    resolved = list(nodetypes or [])
    if len(resolved) < count:
        resolved.extend(["c"] * (count - len(resolved)))
    return resolved[:count]


def vector_between(origin: Sequence[float], target: Sequence[float]) -> List[float]:
    return [
        float(target[0]) - float(origin[0]),
        float(target[1]) - float(origin[1]),
    ]


def translate_point(point: Sequence[float], vector: Sequence[float]) -> List[float]:
    return [
        float(point[0]) + float(vector[0]),
        float(point[1]) + float(vector[1]),
    ]


def find_duplicate_candidates_in_subpath(
    subpath: Subpath,
    tolerance: float,
    closed: bool = False,
    all_pairs: bool = False,
) -> List[DuplicateCandidate]:
    candidates: List[DuplicateCandidate] = []
    if len(subpath) < 2:
        return candidates

    if all_pairs:
        for first_index in range(len(subpath) - 1):
            for second_index in range(first_index + 1, len(subpath)):
                if nodes_form_collapsible_segment(
                    subpath[first_index], subpath[second_index], tolerance
                ):
                    distance = point_distance(
                        subpath[first_index][1], subpath[second_index][1]
                    )
                    candidates.append(
                        DuplicateCandidate(
                            first_index=first_index,
                            second_index=second_index,
                            distance=distance,
                        )
                    )
        return candidates

    for index in range(1, len(subpath)):
        if nodes_form_collapsible_segment(subpath[index - 1], subpath[index], tolerance):
            first_anchor = subpath[index - 1][1]
            second_anchor = subpath[index][1]
            distance = point_distance(first_anchor, second_anchor)
            candidates.append(
                DuplicateCandidate(
                    first_index=index - 1,
                    second_index=index,
                    distance=distance,
                )
            )

    if closed and len(subpath) > 2:
        if nodes_form_collapsible_segment(subpath[-1], subpath[0], tolerance):
            distance = point_distance(subpath[-1][1], subpath[0][1])
            candidates.append(
                DuplicateCandidate(
                    first_index=len(subpath) - 1,
                    second_index=0,
                    distance=distance,
                )
            )

    return candidates


def point_distance(first: Sequence[float], second: Sequence[float]) -> float:
    return hypot(float(first[0]) - float(second[0]), float(first[1]) - float(second[1]))


def nodes_form_collapsible_segment(first: Node, second: Node, tolerance: float) -> bool:
    return same_point(first[1], second[1], tolerance)


def same_point(
    first: Sequence[float], second: Sequence[float], tolerance: float
) -> bool:
    return point_distance(first, second) <= max(float(tolerance), 0.0)
