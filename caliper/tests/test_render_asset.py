"""资产记录表：只补空白、不覆盖人工值、必填与 IP/指导书校验。"""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

from core.contracts.columns import ASSET_COLUMNS
from core.contracts.filenames import ASSET_FILENAME
from core.model.entities import Asset
from core.render.asset_record import (
    AssetRecordError,
    fill_asset_workbook,
    verify_asset_workbook,
)

GUIDES = ["二级-安全通用要求", "三级-安全通用要求"]


def _new_workbook(path: Path, rows: list[dict[str, str]] | None = None) -> Path:
    workbook = openpyxl.Workbook()
    ws = workbook.active
    ws.append(list(ASSET_COLUMNS))
    for values in rows or []:
        ws.append([values.get(column, "") for column in ASSET_COLUMNS])
    workbook.save(path)
    return path


def _asset(**overrides) -> Asset:
    data = {
        "device_name": "示例系统A-应用服务器",
        "ip": "192.0.2.10",
        "importance": "一般",
        "guide": "三级-安全通用要求",
    }
    data.update(overrides)
    return Asset(**data)


def test_fill_blank_without_overwriting(tmp_path: Path) -> None:
    source = _new_workbook(
        tmp_path / "asset.xlsx",
        [
            {
                "设备名称": "示例系统A-应用服务器",
                "IP地址": "192.0.2.10",
                "操作系统及版本": "人工填写的系统版本",
            }
        ],
    )
    asset = _asset(os_version="Ubuntu 24.04", business_system="示例系统A")
    report = fill_asset_workbook(source, [asset], GUIDES, tmp_path / "out")

    assert report.path == tmp_path / "out" / ASSET_FILENAME
    assert report.errors == []
    assert report.filled == 3  # 业务系统、重要程度、作业指导书
    assert any("不允许覆盖" in warning for warning in report.warnings)

    kept = openpyxl.load_workbook(source).active
    assert kept["D2"].value == "人工填写的系统版本"
    assert kept["K2"].value is None

    filled = openpyxl.load_workbook(report.path).active
    assert filled["K2"].value == "一般"
    assert filled["L2"].value == "三级-安全通用要求"
    assert filled["C2"].value == "示例系统A"
    assert filled["D2"].value == "人工填写的系统版本"
    assert verify_asset_workbook(report.path, GUIDES) == []


def test_append_asset_missing_from_sheet(tmp_path: Path) -> None:
    source = _new_workbook(tmp_path / "asset.xlsx")
    report = fill_asset_workbook(source, [_asset()], GUIDES, tmp_path / "out")

    assert report.errors == []
    assert report.appended == 1
    assert report.path is not None
    sheet = openpyxl.load_workbook(report.path).active
    assert sheet["A2"].value == "示例系统A-应用服务器"
    assert sheet["G2"].value == "192.0.2.10"


def test_duplicate_ip_blocks_export(tmp_path: Path) -> None:
    source = _new_workbook(
        tmp_path / "asset.xlsx",
        [
            {
                "设备名称": "设备A",
                "IP地址": "192.0.2.10",
                "重要程度": "一般",
                "作业指导书": "三级-安全通用要求",
            },
            {
                "设备名称": "设备B",
                "IP地址": "192.0.2.10",
                "重要程度": "一般",
                "作业指导书": "三级-安全通用要求",
            },
        ],
    )
    report = fill_asset_workbook(source, [], GUIDES, tmp_path / "out")

    assert report.path is None
    assert any("IP 重复" in error for error in report.errors)
    assert not (tmp_path / "out" / ASSET_FILENAME).exists()


def test_unregistered_guide_blocks_export(tmp_path: Path) -> None:
    source = _new_workbook(
        tmp_path / "asset.xlsx",
        [
            {
                "设备名称": "设备A",
                "IP地址": "192.0.2.10",
                "重要程度": "一般",
                "作业指导书": "四级-安全通用要求",
            }
        ],
    )
    report = fill_asset_workbook(source, [], GUIDES, tmp_path / "out")

    assert report.path is None
    assert any("不在注册列表" in error for error in report.errors)


def test_bad_header_is_rejected(tmp_path: Path) -> None:
    path = _new_workbook(tmp_path / "asset.xlsx")
    workbook = openpyxl.load_workbook(path)
    workbook.active["R1"] = "多余列"
    workbook.save(path)

    with pytest.raises(AssetRecordError, match="18 列口径"):
        fill_asset_workbook(path, [], GUIDES, tmp_path / "out")
