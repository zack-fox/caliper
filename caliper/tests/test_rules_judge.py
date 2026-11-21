"""规则 DSL 与判定合成。"""

from __future__ import annotations

import pytest

from core.checks.mapping import CheckBinding, ChecksMap, PointBinding
from core.contracts.verdict import Verdict
from core.judge.synth import judge_item
from core.model.entities import CheckBlock, CheckStatus, EvidenceAnchor, Item, OutputLine
from core.rules.dsl import RuleError, evaluate, validate_expect
from core.rules.engine import Rule, RuleSet


def _block(title: str, lines: list[str], status: CheckStatus = CheckStatus.COLLECTED) -> CheckBlock:
    return CheckBlock(
        session=1,
        block_index=1,
        section="1. SYSTEM",
        title=title,
        os_family="debian",
        status=status,
        output=[OutputLine(line=index, text=text) for index, text in enumerate(lines, 1)],
        source="demo.log",
    )


def _item(policy: str, binary: bool, mode: str = "auto") -> Item:
    return Item.model_validate(
        {
            "item_id": "L3-CES1-01",
            "level": 3,
            "seq": 1,
            "unit_no": 1,
            "控制点": "身份鉴别",
            "控制项": "a）示例控制项；",
            "重要程度": "重要",
            "检查内容": "示例检查内容",
            "判断标准": "示例判断标准",
            "policy": policy,
            "mode": mode,
            "binary": binary,
            "optional_clause": False,
        }
    )


def test_validate_rejects_forbidden_and_deep_nesting() -> None:
    with pytest.raises(RuleError, match="不允许字段"):
        validate_expect({"and": [{"contains": "x"}]})
    with pytest.raises(RuleError, match="嵌套超过"):
        validate_expect(
            {"all": [{"any": [{"all": [{"contains": "x"}]}]}]}
        )
    with pytest.raises(RuleError, match="未知操作"):
        validate_expect({"regex": "x"})


def test_evaluate_operators() -> None:
    block = _block("Password policy", ["PASS_MAX_DAYS 99999", "PASS_MIN_LEN 8"])
    assert evaluate({"contains": "PASS_MAX_DAYS"}, block)[0] is True
    assert evaluate({"not_contains": "PASS_MIN_LEN"}, block)[0] is False
    assert evaluate({"lt": {"prefix": "PASS_MAX_DAYS", "value": 91}}, block)[0] is False
    assert evaluate({"gt": {"prefix": "PASS_MAX_DAYS", "value": 91}}, block)[0] is True
    assert evaluate(
        {"regex_empty": True}, _block("x", ["no swap"], CheckStatus.EMPTY)
    )[0] is True


def test_evaluate_anchors_are_objects() -> None:
    """eq/in 命中时也必须返回 EvidenceAnchor 列表，不能被当作可迭代字段拆开。"""
    block = _block("Password policy", ["PASS_MAX_DAYS 99999", "PASS_MIN_LEN 8"])
    for expression in ({"eq": "PASS_MIN_LEN 8"}, {"in": ["PASS_MIN_LEN 8"]}):
        passed, anchors = evaluate(expression, block)
        assert passed is True
        assert anchors and all(isinstance(anchor, EvidenceAnchor) for anchor in anchors)


def test_judge_binary_never_partial() -> None:
    item = _item("binary", True)
    rules = RuleSet(
        rules=[
            Rule(
                level=3,
                item=1,
                point=1,
                block="A",
                expect={"contains": "ok"},
                pass_reason="通过",
                fail_reason="未通过",
            ),
            Rule(
                level=3,
                item=1,
                point=2,
                block="B",
                expect={"contains": "ok"},
                pass_reason="通过",
                fail_reason="未通过",
            ),
        ]
    )
    blocks = {"A": _block("A", ["ok"]), "B": _block("B", ["bad"])}
    result = judge_item(item, rules, blocks, expected_points={1, 2})
    assert result.verdict is Verdict.NON_COMPLIANT
    assert result.verdict is not Verdict.PARTIAL
    assert result.points[0].rule_refs


def test_checks_map_isolates_levels() -> None:
    """同一检查块同时服务两级时，实施点不能串用。"""
    checks = ChecksMap(
        checks=[
            CheckBinding(
                title="Shared block",
                block_index=1,
                binds=[
                    PointBinding(item=1, level=3, points=[1, 2, 4]),
                    PointBinding(item=1, level=2, points=[2]),
                ],
            )
        ]
    )
    assert checks.points_for_item(1, 3) == {1, 2, 4}
    assert checks.points_for_item(1, 2) == {2}
    assert checks.mapped_items(2) == {1}


def test_missing_block_marks_uncollected() -> None:
    item = _item("mixed_partial", False)
    rules = RuleSet(
        rules=[
            Rule(
                level=3,
                item=1,
                point=1,
                block="A",
                expect={"contains": "ok"},
                pass_reason="通过",
                fail_reason="未通过",
            )
        ]
    )
    result = judge_item(item, rules, {}, expected_points={1})
    assert result.verdict is Verdict.UNCOLLECTED
    assert result.note.startswith("未采集：")


def test_uncovered_points_mark_uncollected() -> None:
    item = _item("mixed_partial", False)
    rules = RuleSet(
        rules=[
            Rule(
                level=3,
                item=1,
                point=1,
                block="A",
                expect={"contains": "ok"},
                pass_reason="通过",
                fail_reason="未通过",
            )
        ]
    )
    result = judge_item(item, rules, {"A": _block("A", ["ok"])}, expected_points={1, 2})
    assert result.verdict is Verdict.UNCOLLECTED
    assert "规则未覆盖实施点 2" in result.note
