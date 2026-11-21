"""资产记录表：读入 18 列 → 校验 → 用项目配置补空白 → 另存副本。

原始文件永不修改；人工已填值不覆盖，只在不一致时提示。
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl
from openpyxl.worksheet.worksheet import Worksheet

from core.contracts.columns import ASSET_COLUMNS
from core.contracts.filenames import ASSET_FILENAME
from core.model.entities import Asset

REQUIRED_COLUMNS = ("设备名称", "IP地址", "重要程度", "作业指导书")

# 18 列 → 项目资产字段
FIELD_BY_COLUMN = {
    "设备名称": "device_name",
    "是否虚拟设备": "is_virtual",
    "所属业务应用系统/平台名称": "business_system",
    "操作系统及版本": "os_version",
    "数据库管理系统及版本": "db_version",
    "中间件及版本": "middleware_version",
    "IP地址": "ip",
    "数量（台/套）": "count",
    "是否热备": "hot_standby",
    "物理/逻辑区域": "zone",
    "重要程度": "importance",
    "作业指导书": "guide",
    "测评对象": "test_object",
    "备注": "note",
    "扫描对象类型": "scan_object_type",
    "行标注色": "row_color",
    "扫描地址": "scan_address",
    "是否为测试环境": "is_test_env",
}


class AssetRecordError(Exception):
    """资产表不可读或不可导出。"""


@dataclass
class AssetReport:
    rows: int = 0
    filled: int = 0
    appended: int = 0
    path: Path | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _header(ws: Worksheet) -> tuple[str, ...]:
    values = [_text(cell.value) for cell in ws[1]]
    while values and not values[-1]:
        values.pop()
    return tuple(values)


def _row_values(ws: Worksheet, row: int) -> dict[str, str]:
    return {
        column: _text(ws.cell(row=row, column=index).value)
        for index, column in enumerate(ASSET_COLUMNS, start=1)
    }


def _read_rows(ws: Worksheet) -> list[tuple[int, dict[str, str]]]:
    rows: list[tuple[int, dict[str, str]]] = []
    for row in range(2, ws.max_row + 1):
        values = _row_values(ws, row)
        if any(values.values()):
            rows.append((row, values))
    return rows


def _first_empty_row(ws: Worksheet) -> int:
    for row in range(2, ws.max_row + 1):
        if not any(_row_values(ws, row).values()):
            return row
    return ws.max_row + 1


def _asset_value(asset: Asset, column: str) -> str:
    value = getattr(asset, FIELD_BY_COLUMN[column], "")
    if hasattr(value, "value"):
        value = value.value
    return _text(value)


def _write_row(ws: Worksheet, row: int, values: dict[str, str]) -> None:
    for index, column in enumerate(ASSET_COLUMNS, start=1):
        if values[column]:
            ws.cell(row=row, column=index, value=values[column])


def _validate(
    rows: list[tuple[int, dict[str, str]]], guides: list[str], errors: list[str]
) -> None:
    seen_ip: dict[str, int] = {}
    for row, values in rows:
        for column in REQUIRED_COLUMNS:
            if not values[column]:
                errors.append(f"第 {row} 行：必填项「{column}」为空")
        ip = values["IP地址"]
        if ip:
            try:
                ipaddress.ip_address(ip)
            except ValueError:
                errors.append(f"第 {row} 行：IP 地址不合法「{ip}」")
            else:
                if ip in seen_ip:
                    errors.append(f"第 {row} 行与第 {seen_ip[ip]} 行 IP 重复：{ip}")
                else:
                    seen_ip[ip] = row
        guide = values["作业指导书"]
        if guide and guide not in guides:
            errors.append(f"第 {row} 行：作业指导书「{guide}」不在注册列表 {guides}")


def fill_asset_workbook(
    source: Path, assets: list[Asset], guides: list[str], output_dir: Path
) -> AssetReport:
    """生成补全版资产表；有校验错误时不写文件。"""
    source = Path(source)
    if not source.exists():
        raise AssetRecordError(f"原始资产表不存在：{source}")
    if not guides:
        raise AssetRecordError("pack 未注册任何作业指导书，无法校验「作业指导书」列")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / ASSET_FILENAME
    if target.resolve() == source.resolve():
        raise AssetRecordError("输出路径不能与原始资产表相同（原文件永不修改）")

    workbook = openpyxl.load_workbook(source)
    ws = workbook.worksheets[0]
    header = _header(ws)
    if header != ASSET_COLUMNS:
        missing = [column for column in ASSET_COLUMNS if column not in header]
        extra = [column for column in header if column not in ASSET_COLUMNS]
        raise AssetRecordError(
            f"资产表表头必须与 18 列口径一致；缺少 {missing}，多出 {extra}"
        )

    report = AssetReport()
    rows = _read_rows(ws)
    by_name = {asset.device_name: asset for asset in assets}
    by_ip = {asset.ip: asset for asset in assets}
    matched: set[str] = set()

    for row, values in rows:
        asset = by_name.get(values["设备名称"])
        if asset is None and not values["设备名称"] and values["IP地址"]:
            asset = by_ip.get(values["IP地址"])
        if asset is None:
            continue
        matched.add(asset.device_name)
        for column in ASSET_COLUMNS:
            source_value = _asset_value(asset, column)
            if not source_value:
                continue
            current = values[column]
            if not current:
                ws.cell(row=row, column=ASSET_COLUMNS.index(column) + 1, value=source_value)
                values[column] = source_value
                report.filled += 1
            elif current != source_value:
                report.warnings.append(
                    f"第 {row} 行「{column}」：人工值 {current!r} 与项目配置 "
                    f"{source_value!r} 不一致，不允许覆盖，已保留人工值"
                )

    next_row = _first_empty_row(ws)
    for asset in assets:
        if asset.device_name in matched:
            continue
        values = {column: _asset_value(asset, column) for column in ASSET_COLUMNS}
        _write_row(ws, next_row, values)
        rows.append((next_row, values))
        report.appended += 1
        next_row += 1

    _validate(rows, guides, report.errors)
    report.rows = len(rows)
    if report.errors:
        return report

    workbook.save(target)
    report.path = target
    return report


def verify_asset_workbook(path: Path, guides: list[str]) -> list[str]:
    """导出后自检：表头、必填、IP、重复 IP、作业指导书。"""
    workbook = openpyxl.load_workbook(path)
    ws = workbook.worksheets[0]
    problems: list[str] = []
    if _header(ws) != ASSET_COLUMNS:
        problems.append("表头与 18 列口径不一致")
    _validate(_read_rows(ws), guides, problems)
    return problems
