"""采集命令库：真实 pack 装载、两族脚本渲染与回解析。"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from core.evidence.capture import CaptureError, load_capture, render_script
from core.evidence.package import load_evidence

PACK = Path(__file__).resolve().parents[1] / "packs" / "linux_os"
IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
MYSQL_TITLES = [
    "MySQL 版本与运行状态",
    "MySQL 空口令与匿名账户",
    "MySQL 账户权限与最小化",
    "MySQL 登录失败处理",
    "MySQL 口令复杂度策略",
    "MySQL 审计日志",
    "MySQL 远程访问限制",
    "MySQL 备份与恢复",
]


def _write_pack(tmp_path: Path, rules: list[dict]) -> Path:
    data = {"version": "0.1.0", "status": "active", "asset_family": "server", "rules": rules}
    (tmp_path / "capture.yaml").write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return tmp_path


def _rule(**overrides) -> dict:
    rule = {
        "section": "1. SYSTEM",
        "title": "示例检查",
        "command": "true",
        "levels": [2, 3],
        "families": ["server"],
    }
    rule.update(overrides)
    return rule


def test_loads_real_pack_after_activation() -> None:
    library = load_capture(PACK)
    assert library.status == "active"
    families = {family for rule in library.rules for family in rule.families}
    assert families == {"server", "database"}
    database = [rule.title for rule in library.rules if "database" in rule.families]
    assert database == MYSQL_TITLES


def test_server_titles_stay_mappable() -> None:
    library = load_capture(PACK)
    checks = yaml.safe_load((PACK / "checks_map.yaml").read_text(encoding="utf-8"))["checks"]
    mapped = {check["title"] for check in checks}
    server_titles = {rule.title for rule in library.rules if "server" in rule.families}
    assert server_titles <= mapped


@pytest.mark.parametrize("family", ["server", "database"])
@pytest.mark.parametrize("level", [2, 3])
def test_render_script_reparses_to_same_blocks(family: str, level: int, tmp_path: Path) -> None:
    library = load_capture(PACK)
    script = render_script(library, family, level)
    assert "仅供已授权环境使用" in script
    assert not IPV4.search(script)
    assert "root" not in script.lower()

    expected = library.rules_for(family, level)
    path = tmp_path / f"capture-{family}-L{level}.out"
    path.write_text(script, encoding="utf-8")
    package = load_evidence(path)

    assert [block.title for block in package.blocks] == [rule.title for rule in expected]
    assert len(package.blocks) == len(expected)
    assert package.diagnostics == []


def test_rejects_duplicate_title(tmp_path: Path) -> None:
    pack = _write_pack(tmp_path, [_rule(), _rule(section="2. IDENTIFICATION")])
    with pytest.raises(CaptureError, match="title 重复"):
        load_capture(pack)


@pytest.mark.parametrize(
    "overrides",
    [
        {"families": ["network"]},
        {"levels": [4]},
        {"levels": []},
        {"command": ""},
    ],
)
def test_rejects_invalid_entry(tmp_path: Path, overrides: dict) -> None:
    pack = _write_pack(tmp_path, [_rule(**overrides)])
    with pytest.raises(CaptureError, match="采集条目非法"):
        load_capture(pack)


def test_render_rejects_unknown_family_and_empty_selection(tmp_path: Path) -> None:
    library = load_capture(_write_pack(tmp_path, [_rule(levels=[3])]))
    with pytest.raises(CaptureError, match="family"):
        render_script(library, "middleware", 3)
    with pytest.raises(CaptureError, match="没有适用于"):
        render_script(library, "database", 3)
