"""规则条件 DSL：求值 + 结构校验。

允许的原子操作：eq / ne / in / not_in / contains / not_contains /
exists / not_exists / regex_empty / gt / lt；组合器只有 all / any，
嵌套最多两层。字段名写错（如 and/or/expected）直接报错，不兜底。
"""

from __future__ import annotations

import re
from typing import Any

from core.model.entities import CheckBlock, CheckStatus, EvidenceAnchor

COMBINATORS = {"all", "any"}
ATOMS = {
    "eq",
    "ne",
    "in",
    "not_in",
    "contains",
    "not_contains",
    "exists",
    "not_exists",
    "regex_empty",
    "gt",
    "lt",
}
FORBIDDEN = {"and", "or", "expected", "not", "all_of", "any_of"}
MAX_DEPTH = 2

_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


class RuleError(Exception):
    """规则表达式非法。"""


def validate_expect(expression: Any, depth: int = 1, path: str = "expect") -> None:
    if not isinstance(expression, dict) or len(expression) != 1:
        raise RuleError(f"{path}：条件必须是只含一个键的对象")
    key, value = next(iter(expression.items()))
    if key in FORBIDDEN:
        raise RuleError(f"{path}：不允许字段 {key!r}，组合器只支持 all / any")
    if key in COMBINATORS:
        if depth > MAX_DEPTH:
            raise RuleError(f"{path}：条件嵌套超过 {MAX_DEPTH} 层")
        if not isinstance(value, list) or not value:
            raise RuleError(f"{path}.{key}：应为非空条件列表")
        for index, child in enumerate(value):
            validate_expect(child, depth + 1, f"{path}.{key}[{index}]")
        return
    if key not in ATOMS:
        raise RuleError(f"{path}：未知操作 {key!r}")
    if key in {"in", "not_in"}:
        if not isinstance(value, list) or not value:
            raise RuleError(f"{path}.{key}：应为非空字符串列表")
        if not all(isinstance(entry, str) for entry in value):
            raise RuleError(f"{path}.{key}：列表元素必须是字符串")
        return
    if key == "regex_empty":
        if not isinstance(value, bool):
            raise RuleError(f"{path}.regex_empty：应为 true/false")
        return
    if key in {"gt", "lt"}:
        if not isinstance(value, dict):
            raise RuleError(f"{path}.{key}：应为 {{prefix, value}}")
        if set(value) != {"prefix", "value"}:
            raise RuleError(f"{path}.{key}：只允许 prefix 与 value 两个键")
        if not isinstance(value["prefix"], str) or not isinstance(value["value"], (int, float)):
            raise RuleError(f"{path}.{key}：prefix 为字符串、value 为数字")
        return
    if not isinstance(value, str):
        raise RuleError(f"{path}.{key}：操作数必须是字符串")


def _numbers(block: CheckBlock, prefix: str) -> list[float]:
    values: list[float] = []
    for line in block.rule_lines:
        stripped = line.strip()
        if not stripped.startswith(prefix):
            continue
        remainder = stripped[len(prefix) :]
        match = _NUMBER_RE.search(remainder)
        if match:
            values.append(float(match.group(0)))
    return values


def evaluate(expression: dict, block: CheckBlock) -> tuple[bool, list[EvidenceAnchor]]:
    """返回 (是否满足, 支撑证据)。"""
    usable = bool(
        block.output
        or block.facts
        or (block.status is CheckStatus.EMPTY and block.command_anchors)
    )
    if block.status in {CheckStatus.FAILED, CheckStatus.SKIPPED} or not usable:
        return False, []
    key, value = next(iter(expression.items()))

    if key == "all":
        anchors: list[EvidenceAnchor] = []
        for child in value:
            passed, child_anchors = evaluate(child, block)
            if not passed:
                return False, child_anchors
            anchors.extend(child_anchors)
        return True, anchors[:3]
    if key == "any":
        anchors = []
        for child in value:
            passed, child_anchors = evaluate(child, block)
            if passed:
                return True, child_anchors[:3]
            anchors.extend(child_anchors)
        return False, anchors[:3]

    lines = block.rule_lines
    stripped = [line.strip() for line in lines]

    if key in {"contains", "exists"}:
        anchor = block.first_anchor(value)
        return anchor is not None, ([anchor] if anchor else [])
    if key in {"not_contains", "not_exists"}:
        anchor = block.first_anchor(value)
        return anchor is None, (block.anchors(1) if anchor is None else [anchor])
    if key == "eq":
        anchor = block.first_anchor(value) if any(line == value for line in stripped) else None
        return anchor is not None, ([anchor] if anchor else [])
    if key == "ne":
        matched = not any(line == value for line in stripped)
        return matched, (block.anchors(1) if matched else [])
    if key == "in":
        hit = next((line for line in stripped if line in value), None)
        if hit is None:
            return False, []
        anchor = block.first_anchor(hit)
        return True, ([anchor] if anchor else block.anchors(1))
    if key == "not_in":
        hit = next((line for line in stripped if line in value), None)
        return hit is None, (block.anchors(1) if hit is None else [])
    if key == "regex_empty":
        matched = (block.status.value == "empty") is value
        return matched, (block.anchors(1) if matched else [])
    if key in {"gt", "lt"}:
        numbers = _numbers(block, value["prefix"])
        threshold = float(value["value"])
        if key == "gt":
            ok = any(number > threshold for number in numbers)
        else:
            ok = any(number < threshold for number in numbers)
        anchor = block.first_anchor(value["prefix"]) if ok else None
        return ok, ([anchor] if anchor else [])

    raise RuleError(f"未知操作 {key!r}")
