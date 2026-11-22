"""由判定结果生成整改建议。

只对「不符合 / 部分符合」产出建议；命中规则时按规则库原文输出，
没有命中就返回空列表，调用方必须显式处理，不得编造问题或条款。
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict

from core.contracts.verdict import Verdict
from core.model.entities import AssetRun, Item, ItemResult
from core.remediation.library import (
    PRIORITY_ORDER,
    RemediationLibrary,
    RemediationRule,
)

_TARGET_VERDICTS = {Verdict.PARTIAL, Verdict.NON_COMPLIANT}


class Advice(BaseModel):
    """一条整改建议，字段全部来自规则库，不做推测。"""

    model_config = ConfigDict(frozen=True)

    rule_id: str
    item_id: str
    seq: int
    title: str = ""
    problem: str
    cause: str
    action: str
    priority: str
    clause: str


def suggest(
    library: RemediationLibrary,
    items: list[Item] | dict[int, Item],
    run: AssetRun,
) -> list[Advice]:
    """返回该资产运行结果对应的建议；无命中时为空列表。"""
    item_by_seq = _index_items(items)
    family = run.asset.family
    advices: list[Advice] = []
    for result in sorted(run.items, key=lambda entry: entry.seq):
        if result.verdict not in _TARGET_VERDICTS:
            continue
        item = item_by_seq.get(result.seq)
        level = item.level if item is not None else None
        rule = _pick_rule(library.rules, result, level, family)
        if rule is None:
            continue
        advices.append(
            Advice(
                rule_id=rule.id,
                item_id=result.item_id,
                seq=result.seq,
                title=rule.title,
                problem=rule.problem,
                cause=rule.cause,
                action=rule.action,
                priority=rule.priority,
                clause=rule.clause,
            )
        )
    return advices


def _index_items(items: list[Item] | dict[int, Item]) -> dict[int, Item]:
    if isinstance(items, Mapping):
        return {int(seq): item for seq, item in items.items()}
    return {item.seq: item for item in items}


def _pick_rule(
    rules: list[RemediationRule],
    result: ItemResult,
    level: int | None,
    family: str,
) -> RemediationRule | None:
    """按 seq 优先、控制点关键字兜底，同级取优先级最高的一条。"""
    candidates = [
        rule for rule in rules if _applicable(rule, result.seq, level, family)
    ]
    bound = [
        rule for rule in candidates if rule.applies_to.item_seqs is not None
    ]
    if bound:
        return min(bound, key=_rank)

    keyword = result.control_point.strip()
    if not keyword:
        return None
    fallback = [
        rule
        for rule in candidates
        if rule.applies_to.item_seqs is None
        and (keyword in rule.title or keyword in rule.problem)
    ]
    return min(fallback, key=_rank) if fallback else None


def _applicable(
    rule: RemediationRule,
    seq: int,
    level: int | None,
    family: str,
) -> bool:
    applies = rule.applies_to
    if applies.family and family not in applies.family:
        return False
    if applies.level:
        if level is None or level not in applies.level:
            return False
    if applies.item_seqs is not None:
        return seq in applies.item_seqs
    return True


def _rank(rule: RemediationRule) -> tuple[int, str]:
    return (PRIORITY_ORDER[rule.priority], rule.id)
