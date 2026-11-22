"""判定合成：实施点 → 测评项结论。策略只用 contracts/policy.py 的六种。"""

from __future__ import annotations

from core.contracts.policy import Policy
from core.contracts.verdict import Verdict
from core.model.entities import CheckBlock, CheckStatus, Item, ItemResult, PointResult
from core.rules.dsl import evaluate
from core.rules.engine import RuleSet

UNCOLLECTED_PREFIX = "未采集："
UNCOVERED_PREFIX = "未覆盖："
MISSING_BLOCK = "未找到可核查证据块"


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
        label = (
            "人工核查"
            if point.manual
            else "未采集" if point.passed is None else "通过" if point.passed else "未通过"
        )
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

    manual_points = [
        PointResult(point=entry.point, passed=None, reason=entry.reason, manual=True)
        for entry in item.manual_points
    ]
    manual_numbers = {point.point for point in manual_points}
    item_rules = [
        rule for rule in ruleset.for_item(item.seq, item.level)
        if rule.point not in manual_numbers
    ]
    automatic_expected = (expected_points or set()) - manual_numbers
    if not item_rules:
        if not manual_points:
            reason = f"{UNCOVERED_PREFIX}规则库无对应条目"
        elif automatic_expected:
            reason = (
                f"{UNCOVERED_PREFIX}规则库缺少实施点 "
                f"{', '.join(map(str, sorted(automatic_expected)))} 的对应条目"
            )
        elif manual_points:
            reason = f"{UNCOLLECTED_PREFIX}需完成人工实施点核查"
        else:
            reason = f"{UNCOVERED_PREFIX}规则库无对应条目"
        base.note = reason
        base.warnings = [reason] if reason.startswith(UNCOVERED_PREFIX) else []
        base.points = sorted(manual_points, key=lambda point: point.point)
        base.result_text = build_result_text(base.points)
        return base

    coverage_reason = ""
    if automatic_expected:
        uncovered = sorted(automatic_expected - {rule.point for rule in item_rules})
        if uncovered:
            coverage_reason = (
                f"{UNCOVERED_PREFIX}规则库缺少实施点 "
                f"{', '.join(map(str, uncovered))} 的对应条目"
            )

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
        point_missing: list[str] = []
        point_evaluated = 0
        block_title = ""
        for rule in point_rules:
            rule_refs.append(rule.reference_id(item.item_id))
            block_title = block_title or rule.block
            block = blocks.get(rule.block)
            if block is None:
                if rule.optional_block:
                    continue
                reason = f"{MISSING_BLOCK}「{rule.block}」"
                missing.append(reason)
                point_missing.append(reason)
                continue
            if block.status in {CheckStatus.FAILED, CheckStatus.SKIPPED}:
                reason = f"{MISSING_BLOCK}「{rule.block}」（采集状态 {block.status.value}）"
                missing.append(reason)
                point_missing.append(reason)
                continue
            rule_passed, rule_anchors = evaluate(rule.expect, block)
            point_evaluated += 1
            passed = passed and rule_passed
            reasons.append(rule.pass_reason if rule_passed else rule.fail_reason)
            anchors.extend(rule_anchors)
        if point_missing:
            reasons = [
                "缺少证据，无法完成实施点判定："
                + "；".join(dict.fromkeys(point_missing))
            ]
        elif point_evaluated == 0:
            # 条件证据块未部署，该实施点不参与合成，避免把“未安装”误判为不通过。
            continue
        points.append(
            PointResult(
                point=point_no,
                passed=None if point_missing else passed,
                reason="；".join(dict.fromkeys(reasons)),
                block_title=block_title,
                anchors=anchors[:3],
                rule_refs=list(dict.fromkeys(rule_refs)),
            )
        )

    points.extend(manual_points)
    points.sort(key=lambda point: point.point)
    base.points = points
    if not points:
        titles = "、".join(dict.fromkeys(rule.block for rule in item_rules))
        base.note = f"{UNCOLLECTED_PREFIX}条件证据块未部署（{titles}）"
        return base
    if coverage_reason:
        base.note = coverage_reason
        base.warnings = [coverage_reason]
        base.result_text = build_result_text(points)
        return base
    if missing:
        base.note = f"{UNCOLLECTED_PREFIX}{'；'.join(dict.fromkeys(missing))}"
        base.result_text = build_result_text(points)
        return base
    if manual_points:
        base.note = (
            f"{UNCOLLECTED_PREFIX}实施点 "
            f"{', '.join(map(str, sorted(manual_numbers)))} 需人工核查，复核前不生成整项分数"
        )
        base.result_text = build_result_text(points)
        return base

    values = [bool(point.passed) for point in points if not point.manual]
    verdict = _synthesize(item.policy, values)
    warnings: list[str] = []
    if item.binary and verdict is Verdict.PARTIAL:
        verdict = Verdict.NON_COMPLIANT
        warnings.append("二值单元算出部分符合，已按契约强制降为不符合")
    base.verdict = verdict
    base.result_text = build_result_text(points)
    base.warnings = warnings
    return base
