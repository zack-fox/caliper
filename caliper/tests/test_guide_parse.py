"""指导书解析质量核查的回归测试（不依赖真实工作簿）。"""

from __future__ import annotations

from tools.parse_guides import (
    GuideRecord,
    find_conflicts,
    find_missing_units,
    missing_fields,
    parse_sheet_name,
)


def record(**overrides: object) -> GuideRecord:
    base = dict(
        domain="network",
        level=3,
        object="H3C",
        object_kind="vendor",
        sheet="H3C（三级）",
        excel_row=2,
        seq="1",
        unit_no="L3-CES1-01",
        control_point="身份鉴别",
        item_text="a）应对登录的用户进行身份标识和鉴别；",
        operation_guide="display current-configuration",
        result_pass="经核查：已启用身份鉴别。",
        result_partial="",
        result_fail="经核查：未启用身份鉴别。",
        result_na="—",
        note="",
        problem="未启用身份鉴别",
        threat="身份冒用",
        harm="设备被非授权访问",
        high_risk_case="—（未命中第一层判例）",
        major_risk="—（未命中附录G触发项）",
        risk_value="低",
        remediation="启用身份鉴别。",
        missing_fields=[],
    )
    base.update(overrides)
    return GuideRecord(**base)  # type: ignore[arg-type]


def test_parse_sheet_name_supports_three_domains() -> None:
    assert parse_sheet_name("network", "H3C（三级）") == (3, "H3C")
    assert parse_sheet_name("network", "Cisco（二级） ") == (2, "Cisco")
    assert parse_sheet_name("database", "【四级】MySQL数据库") == (4, "MySQL")
    assert parse_sheet_name("os", "【三级】Ubuntu（Debian）操作系统 ") == (
        3,
        "Ubuntu（Debian）",
    )


def test_missing_fields_ignores_explicit_not_applicable() -> None:
    values = {
        "操作指导": "display current-configuration",
        "结果记录（符合）": "—",
        "结果记录（不符合）": "—",
        "问题描述（不符合情形）": "",
        "危害分析": "—",
        "整改建议": " ",
    }
    assert missing_fields(values) == ["问题描述（不符合情形）", "整改建议"]


def test_punctuation_only_difference_is_not_conflict() -> None:
    left = record(object="H3C", item_text="a）应对登录的用户进行身份标识和鉴别；")
    right = record(object="HUAWEI", item_text="a) 应对登录的用户进行身份标识和鉴别：")
    assert find_conflicts([left, right]) == []


def test_control_point_and_clause_difference_is_conflict() -> None:
    left = record(object="H3C", control_point="安全审计")
    right = record(object="中兴ZTE", control_point="访问控制")
    conflicts = find_conflicts([left, right])
    assert [(item["field"], item["left_object"], item["right_object"]) for item in conflicts] == [
        ("控制点", "H3C", "中兴ZTE")
    ]


def test_missing_units_detects_number_gap() -> None:
    records = [
        record(unit_no="L3-CES1-01"),
        record(unit_no="L3-CES1-02", excel_row=3),
        record(unit_no="L3-CES1-04", excel_row=4),
    ]
    assert find_missing_units(records) == [
        {
            "domain": "network",
            "level": 3,
            "expected_range": "1..4",
            "actual_count": 3,
            "missing_numbers": [3],
        }
    ]
