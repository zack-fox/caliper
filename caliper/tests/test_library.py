"""六库清单与加载器。"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.rules.library import LibraryError, RuleLibrary

PACK = Path(__file__).resolve().parents[1] / "packs" / "linux_os"


def test_loads_six_libraries() -> None:
    library = RuleLibrary.load(PACK)
    assert [entry.key for entry in library.entries] == [
        "capture",
        "record",
        "judge",
        "remediation",
        "high_risk",
        "major",
    ]
    assert library.entry("judge").status == "active"
    assert library.entry("judge").rule_count > 0
    assert library.entry("capture").status == "active"
    assert library.entry("capture").rule_count > 0
    assert library.entry("record").status == "active"
    assert library.entry("record").rule_count == 5
    assert library.entry("high_risk").rule_count > 0
    assert library.total_rules() >= library.entry("judge").rule_count


def test_missing_manifest(tmp_path: Path) -> None:
    with pytest.raises(LibraryError, match="缺少六库清单"):
        RuleLibrary.load(tmp_path)


def test_missing_library_and_missing_file(tmp_path: Path) -> None:
    (tmp_path / "library.yaml").write_text("version: '1'\nlibraries: {}\n", encoding="utf-8")
    with pytest.raises(LibraryError, match="缺少规则库"):
        RuleLibrary.load(tmp_path)

    manifest = tmp_path / "library.yaml"
    manifest.write_text(
        "version: '1'\n"
        "libraries:\n"
        + "".join(
            f"  {key}:\n    title: {key}\n    status: scaffold\n    path: {key}.yaml\n"
            for key in ("capture", "record", "judge", "remediation", "high_risk", "major")
        ),
        encoding="utf-8",
    )
    with pytest.raises(LibraryError, match="规则文件不存在"):
        RuleLibrary.load(tmp_path)


def test_active_without_rules(tmp_path: Path) -> None:
    names = ("capture", "record", "judge", "remediation", "high_risk", "major")
    for key in names:
        (tmp_path / f"{key}.yaml").write_text("version: '1'\nrules: []\n", encoding="utf-8")
    (tmp_path / "library.yaml").write_text(
        "version: '1'\n"
        "libraries:\n"
        + "".join(
            f"  {key}:\n    title: {key}\n    status: {'active' if key == 'judge' else 'scaffold'}\n"
            f"    path: {key}.yaml\n"
            for key in names
        ),
        encoding="utf-8",
    )
    with pytest.raises(LibraryError, match="没有规则"):
        RuleLibrary.load(tmp_path)
