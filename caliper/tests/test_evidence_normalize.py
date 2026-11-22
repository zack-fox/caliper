"""事实归一化与人工实施点的接线。"""

from __future__ import annotations

import pytest

from core.checks.mapping import CheckBinding, ChecksMap, PointBinding
from core.contracts.verdict import Verdict
from core.evidence.normalize import normalize_blocks
from core.judge.synth import judge_item
from core.model.entities import CheckBlock, CheckStatus, Item, OutputLine
from core.rules.engine import Rule, RuleSet


def _block(
    title: str,
    lines: list[tuple[int, str]],
    status: CheckStatus = CheckStatus.COLLECTED,
) -> CheckBlock:
    return CheckBlock(
        session=1,
        block_index=1,
        section="2. IDENTIFICATION",
        title=title,
        os_family="debian",
        status=status,
        output=[OutputLine(line=line, text=text) for line, text in lines],
        source="raw/host.log",
    )


def _checks(title: str, normalize: str, item: int = 1, point: int = 1) -> ChecksMap:
    return ChecksMap(
        checks=[
            CheckBinding(
                title=title,
                block_index=1,
                binds=[PointBinding(item=item, points=[point])],
                normalize=normalize,
            )
        ]
    )


def _item(check_content: str, manual_points: list[dict] | None = None) -> Item:
    return Item.model_validate(
        {
            "item_id": "L3-CES1-01",
            "level": 3,
            "seq": 1,
            "unit_no": 1,
            "控制点": "身份鉴别",
            "控制项": "a）示例控制项；",
            "重要程度": "重要",
            "检查内容": check_content,
            "判断标准": "示例判断标准",
            "policy": "mixed_partial",
            "mode": "auto",
            "binary": False,
            "optional_clause": False,
            "manual_points": manual_points or [],
        }
    )


def test_normalize_blocks_derives_fact_with_source_anchors() -> None:
    block = _block("Empty / expired password", [(12, "no empty-password account")])
    warnings: list[str] = []

    normalize_blocks([block], _checks("Empty / expired password", "empty_password"), warnings)

    assert block.status is CheckStatus.COLLECTED
    fact = next(fact for fact in block.facts if fact.text == "fact:empty_password.none=true")
    assert fact.anchors[0].file == "raw/host.log"
    assert fact.anchors[0].line == 12
    assert warnings == []


def test_normalize_blocks_marks_insufficient_evidence_failed() -> None:
    block = _block("Duplicate UID / UID=0 accounts", [(5, "unexpected output")])
    warnings: list[str] = []

    normalize_blocks(
        [block], _checks("Duplicate UID / UID=0 accounts", "duplicate_uid"), warnings
    )

    assert block.status is CheckStatus.FAILED
    assert any("证据结构不足" in message for message in warnings)


def test_judge_item_skips_manual_points() -> None:
    item = _item(
        "1) 应核查自动实施点；\n\n2) 应核查账户归属；",
        [{"point": 2, "reason": "账户归属需人工访谈确认"}],
    )
    rules = RuleSet(
        rules=[
            Rule(
                level=3,
                item=1,
                point=1,
                block="A",
                expect={"contains": "ok"},
                pass_reason="自动点通过",
                fail_reason="自动点未通过",
            ),
            Rule(
                level=3,
                item=1,
                point=2,
                block="B",
                expect={"contains": "never"},
                pass_reason="不应参与判定",
                fail_reason="不应参与判定",
            ),
        ]
    )
    blocks = {
        "A": _block("A", [(1, "ok")]),
        "B": _block("B", [(1, "bad")]),
    }

    result = judge_item(item, rules, blocks, expected_points={1, 2})

    point2 = next(point for point in result.points if point.point == 2)
    assert point2.manual is True
    assert point2.passed is None
    assert "人工核查" in result.result_text
    assert result.verdict is Verdict.UNCOLLECTED


@pytest.mark.parametrize(
    ("lines", "expected_status", "expected_fact"),
    [
        ([(3, "rotate 200")], CheckStatus.FAILED, None),
        ([(3, "daily")], CheckStatus.FAILED, None),
        ([(3, "daily"), (4, "rotate 179")], CheckStatus.COLLECTED, "fact:log.retention.six_months=false"),
        ([(3, "weekly"), (4, "rotate 26")], CheckStatus.COLLECTED, "fact:log.retention.six_months=true"),
        ([(3, "MaxRetentionSec=30day")], CheckStatus.COLLECTED, "fact:log.retention.six_months=false"),
        ([(3, "maxage 180")], CheckStatus.COLLECTED, "fact:log.retention.six_months=true"),
    ],
)
def test_log_retention_requires_a_determinable_period(
    lines: list[tuple[int, str]], expected_status: CheckStatus, expected_fact: str | None
) -> None:
    block = _block("Log retention", lines)
    warnings: list[str] = []
    normalize_blocks([block], _checks("Log retention", "log_retention"), warnings)

    assert block.status is expected_status
    if expected_fact is None:
        assert block.facts == []
        assert any("证据结构不足" in warning for warning in warnings)
    else:
        assert expected_fact in block.rule_lines
        fact = next(fact for fact in block.facts if fact.text == expected_fact)
        assert fact.anchors[0].line in {line for line, _ in lines}


def test_faillock_module_alone_is_not_a_complete_policy() -> None:
    block = _block("Login failure lockout (faillock)", [(8, "auth required pam_faillock.so")])
    warnings: list[str] = []
    normalize_blocks(
        [block], _checks("Login failure lockout (faillock)", "faillock"), warnings
    )

    assert block.status is CheckStatus.FAILED
    assert "fact:faillock.module=true" in block.rule_lines
    assert not any(fact.text.startswith("fact:faillock.policy=") for fact in block.facts)


def test_security_agent_process_alone_is_insufficient() -> None:
    block = _block("Security agent (EDR / AV / IDS)", [(9, "demo 123 1 0 ? /opt/wazuh/bin/ossec")])
    block.commands = ["ps -ef"]
    warnings: list[str] = []
    normalize_blocks(
        [block], _checks("Security agent (EDR / AV / IDS)", "security_agent"), warnings
    )

    assert block.status is CheckStatus.FAILED
    assert "fact:security_agent.process.present=true" in block.rule_lines
    assert not any(fact.text.startswith("fact:security_agent.package.") for fact in block.facts)


def test_selinux_subject_labels_alone_are_insufficient() -> None:
    block = _block("SELinux status", [(10, "system_u:system_r:init_t:s0 demo-process")])
    block.commands = ["ps -eZ"]
    warnings: list[str] = []
    normalize_blocks([block], _checks("SELinux status", "selinux"), warnings)

    assert block.status is CheckStatus.FAILED
    assert "fact:security_labels.subject=true" in block.rule_lines
    assert "fact:security_labels.configured=true" not in block.rule_lines
