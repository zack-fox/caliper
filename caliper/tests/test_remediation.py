"""整改建议库、生成器与润色白名单。"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest
import yaml

from adapters.llm import PAYLOAD_FIELDS, build_payload, polish
from core.contracts.enums import AssetType, Importance
from core.contracts.verdict import Verdict
from core.items.loader import load_pack
from core.model.entities import Asset, AssetRun, Item, ItemResult
from core.remediation.generator import suggest
from core.remediation.library import (
    RemediationError,
    RemediationLibrary,
    RemediationRule,
)

PACK = Path(__file__).resolve().parents[1] / "packs" / "linux_os"


@pytest.fixture(scope="module")
def items() -> list[Item]:
    return load_pack(PACK).items_for_level(3)


def _run(
    items: list[Item],
    seq: int,
    verdict: Verdict,
    asset_type: AssetType = AssetType.SERVER,
) -> AssetRun:
    item = next(entry for entry in items if entry.seq == seq)
    result = ItemResult(
        item_id=item.item_id,
        seq=item.seq,
        control_point=item.control_point,
        importance=item.importance,
        verdict=verdict,
        note="证据包 pkg-A01，主机 192.0.2.10，日志原文",
        result_text="经核查：存在弱口令账户。",
    )
    asset = Asset(
        device_name="测试服务器",
        ip="192.0.2.10",
        importance=Importance.IMPORTANT,
        guide="三级-安全通用要求",
        asset_type=asset_type,
    )
    return AssetRun(asset=asset, os_family="debian", items=[result])


def test_load_real_pack(items: list[Item]) -> None:
    library = RemediationLibrary.load(PACK, items)
    assert library.status == "active"
    assert len(library.rules) >= 12
    assert library.rule_by_id("REM-01") is not None
    assert all(rule.clause for rule in library.rules)
    assert all(rule.clause.startswith("GB/T 22239-2019") for rule in library.rules)


@pytest.mark.parametrize("verdict", [Verdict.NON_COMPLIANT, Verdict.PARTIAL])
def test_suggest_for_non_compliant(items: list[Item], verdict: Verdict) -> None:
    library = RemediationLibrary.load(PACK)
    advice = suggest(library, items, _run(items, 1, verdict))
    assert len(advice) == 1
    entry = advice[0]
    assert entry.rule_id == "REM-01"
    assert entry.item_id == "L3-CES1-01"
    assert entry.seq == 1
    assert "GB/T 22239-2019" in entry.clause
    assert entry.priority in {"高", "中", "低"}


def test_compliant_result_gets_no_advice(items: list[Item]) -> None:
    library = RemediationLibrary.load(PACK)
    assert suggest(library, items, _run(items, 1, Verdict.COMPLIANT)) == []


def test_no_matching_rule_returns_empty(items: list[Item]) -> None:
    library = RemediationLibrary.load(PACK)
    # 个人信息保护没有配置建议规则，必须返回空而不是编造建议。
    assert suggest(library, items, _run(items, 33, Verdict.NON_COMPLIANT)) == []


def test_keyword_fallback_for_unbound_rule(items: list[Item]) -> None:
    rule = RemediationRule.model_validate(
        {
            "id": "REM-KW",
            "title": "身份鉴别策略核查",
            "applies_to": {
                "level": [3],
                "family": ["server"],
                "item_seqs": None,
            },
            "priority": "低",
            "problem": "身份鉴别相关配置缺失。",
            "cause": "未配置基线策略。",
            "action": "按基线补齐身份鉴别策略。",
            "clause": "GB/T 22239-2019 8.1.4.1 身份鉴别",
        }
    )
    library = RemediationLibrary(version="test", status="active", rules=[rule])
    advice = suggest(library, items, _run(items, 1, Verdict.NON_COMPLIANT))
    assert [entry.rule_id for entry in advice] == ["REM-KW"]


def test_payload_whitelist_and_no_network(
    items: list[Item], monkeypatch: pytest.MonkeyPatch
) -> None:
    library = RemediationLibrary.load(PACK)
    advice = suggest(library, items, _run(items, 1, Verdict.NON_COMPLIANT))[0]

    payload = build_payload(advice)
    assert set(payload) == set(PAYLOAD_FIELDS)
    for forbidden in (
        "evidence",
        "note",
        "result_text",
        "host",
        "hostname",
        "ip",
        "device_name",
        "log",
        "logs",
    ):
        assert forbidden not in payload
    assert "192.0.2.10" not in "".join(payload.values())

    def _boom(*args, **kwargs):
        raise AssertionError("默认润色不得发起网络调用")

    monkeypatch.setattr(socket, "socket", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)
    assert polish(advice) is advice


def _rule(**overrides) -> dict:
    data = {
        "id": "REM-T",
        "title": "标题",
        "applies_to": {"level": [3], "family": ["server"], "item_seqs": [1]},
        "priority": "高",
        "problem": "问题",
        "cause": "成因",
        "action": "动作",
        "clause": "GB/T 22239-2019 8.1.4.1 身份鉴别",
    }
    data.update(overrides)
    return data


def _write_library(tmp_path: Path, rules: list[dict]) -> None:
    data = {"version": "test", "status": "active", "rules": rules}
    (tmp_path / "remediation.yaml").write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def test_invalid_priority_raises(tmp_path: Path) -> None:
    _write_library(tmp_path, [_rule(priority="紧急")])
    with pytest.raises(RemediationError, match="规则字段非法"):
        RemediationLibrary.load(tmp_path)


def test_missing_required_field_raises(tmp_path: Path) -> None:
    broken = _rule()
    broken.pop("action")
    _write_library(tmp_path, [broken])
    with pytest.raises(RemediationError, match="规则字段非法"):
        RemediationLibrary.load(tmp_path)


def test_unknown_item_seq_raises(tmp_path: Path, items: list[Item]) -> None:
    _write_library(
        tmp_path,
        [
            _rule(
                applies_to={
                    "level": [3],
                    "family": ["server"],
                    "item_seqs": [999],
                }
            )
        ],
    )
    with pytest.raises(RemediationError, match="不存在的测评项"):
        RemediationLibrary.load(tmp_path, items)
