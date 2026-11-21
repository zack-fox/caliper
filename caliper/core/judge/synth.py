"""判定合成：实施点 → 测评项结论。策略只用 contracts/policy.py 的六种。"""

from __future__ import annotations

from core.contracts.policy import Policy
from core.contracts.verdict import Verdict
from core.model.entities import CheckBlock, CheckStatus, Item, ItemResult, PointResult
from core.rules.dsl import evaluate
from core.rules.engine import RuleSet

UNCOLLECTED_PREFIX = "未采集："


def _synthesize(policy: Policy, values: list[bool]) -> Verdict:
    if policy is Policy.ALL_POSITIVE:
        return Verdict.COMPLIANT if all(values) else Verdict.NON_COMPLIANT
    if policy is Policy.ANY_POSITIVE:
        return Verdict.COMPLIANT if any(values) else Verdict.NON_COMPLIANT
    if policy is Policy.MIXED_PARTIAL:
        if all(values):
            return Verdict.COMPLIANT
        if not any(values):
            return Verdict.NON_COMPLIANT
        return Verdict.PARTIAL
    if policy is Policy.BINARY:
        return Verdict.COMPLIANT if all(values) else Verdict.NON_COMPLIANT
    raise ValueError(f"policy {policy.value} 不参与实施点合成")


def _anchor_text(point: PointResult) -> str:
    if not point.anchors:
        return ""
    anchor = point.anchors[0]
    snippet = anchor.snippet[:60]
    return f"（{anchor.file}:{anchor.line} {snippet}）"


def build_result_text(points: list[PointResult]) -> str:
    if not points:
        return ""
    rows = []
    for point in points:
        label = "通过" if point.passed else "未通过"
        rows.append(f"{point.point}) {label}：{point.reason}{_anchor_text(point)}")
    return "\n".join(rows)


def judge_item(
    item: Item,
    ruleset: RuleSet,
    blocks: dict[str, CheckBlock],
    expected_points: set[int] | None = None,
) -> ItemResult:
    base = ItemResult(
        item_id=item.item_id,
        seq=item.seq,
        control_point=item.control_point,
        importance=item.importance,
        verdict=Verdict.UNCOLLECTED,
    )

    if item.policy is Policy.NA:
        base.verdict = Verdict.NOT_APPLICABLE
        base.result_text = "默认不适用"
        return base

    if item.mode == "manual":
        base.note = f"{UNCOLLECTED_PREFIX}需人工核查（访谈或外部证据）"
        return base

    item_rules = ruleset.for_item(item.seq, item.level)
    if not item_rules:
        base.note = f"{UNCOLLECTED_PREFIX}规则尚未实现"
        return base

    if expected_points:
        uncovered = sorted(expected_points - {rule.point for rule in item_rules})
        if uncovered:
            base.note = f"{UNCOLLECTED_PREFIX}规则未覆盖实施点 {', '.join(map(str, uncovered))}"
            return base

    points: list[PointResult] = []
    missing: list[str] = []
    grouped: dict[int, list] = {}
    for rule in item_rules:
        grouped.setdefault(rule.point, []).append(rule)

    for point_no in sorted(grouped):
        point_rules = grouped[point_no]
        passed = True
        reasons: list[str] = []
        anchors: list = []
        rule_refs: list[str] = []
        block_title = ""
        for rule in point_rules:
            block = blocks.get(rule.block)
            if block is None:
                missing.append(f"检查块「{rule.block}」缺失")
                continue
            if block.status in {CheckStatus.FAILED, CheckStatus.SKIPPED}:
                missing.append(f"检查块「{rule.block}」未采集")
                continue
            rule_passed, rule_anchors = evaluate(rule.expect, block)
            rule_refs.append(rule.reference_id(item.item_id))
            passed = passed and rule_passed
            reasons.append(rule.pass_reason if rule_passed else rule.fail_reason)
            anchors.extend(rule_anchors)
            block_title = block_title or rule.block
        points.append(
            PointResult(
                point=point_no,
                passed=passed,
                reason="；".join(dict.fromkeys(reasons)),
                block_title=block_title,
                anchors=anchors[:3],
                rule_refs=list(dict.fromkeys(rule_refs)),
            )
        )

    base.points = points
    if missing:
        base.note = f"{UNCOLLECTED_PREFIX}{'；'.join(dict.fromkeys(missing))}"
        base.result_text = build_result_text(points)
        return base

    values = [bool(point.passed) for point in points]
    verdict = _synthesize(item.policy, values)
    warnings: list[str] = []
    if item.binary and verdict is Verdict.PARTIAL:
        verdict = Verdict.NON_COMPLIANT
        warnings.append("二值单元算出部分符合，已按契约强制降为不符合")
    base.verdict = verdict
    base.result_text = build_result_text(points)
    base.warnings = warnings
    return base
