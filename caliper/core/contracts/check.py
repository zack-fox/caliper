"""契约检查：母版逐格比对 + pack 口径自检。任何不一致都抛错并退出非零。"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import openpyxl
import yaml

from core.contracts.columns import ASSET_COLUMNS, ISSUE_COLUMNS, MAJOR_COLUMNS, RESULT_COLUMNS
from core.contracts.layout import (
    COLUMN_WIDTHS,
    DATA_START_ROW,
    HEADER_CELLS,
    HEADER_HEIGHTS,
    HEADER_ROW,
    LEVEL2_ROW_COUNT,
    LEVEL3_ROW_COUNT,
    MERGED_RANGES,
    SECTION_ROW,
    SECTION_TITLE,
)
from core.contracts.policy import Policy


class ContractError(Exception):
    """契约不一致。"""


def _norm(value: object) -> str:
    if value is None:
        return ""
    return str(value).replace("_x000D_", "").replace("\r\n", "\n").replace("\r", "\n")


def _load_yaml(path: Path) -> object:
    with path.open(encoding="utf-8") as fp:
        return yaml.safe_load(fp)


def _load_items(path: Path) -> list[dict]:
    data = _load_yaml(path)
    if not isinstance(data, list) or not data:
        raise ContractError(f"{path.name} 应为非空列表")
    return data


def _check_columns(workbook: Path, columns: tuple[str, ...], name: str) -> None:
    ws = openpyxl.load_workbook(workbook).worksheets[0]
    actual = tuple(_norm(ws.cell(row=1, column=i + 1).value) for i in range(ws.max_column))
    if actual != columns:
        raise ContractError(
            f"{name} 列名/列序与契约不一致：期望 {len(columns)} 列，实际 {len(actual)} 列"
        )
    print(f"[OK] {name}：{len(columns)} 列，列名与列序逐字一致")


def _check_template_layout(ws) -> None:
    actual_merges = {str(rng) for rng in ws.merged_cells.ranges}
    if actual_merges != set(MERGED_RANGES):
        raise ContractError(f"结果记录表合并区不一致：{sorted(actual_merges)}")
    for col, width in COLUMN_WIDTHS.items():
        actual = ws.column_dimensions[col].width
        if actual is None or abs(actual - width) > 0.01:
            raise ContractError(f"结果记录表列宽不一致：{col} 期望 {width}，实际 {actual}")
    for row, height in HEADER_HEIGHTS.items():
        actual = ws.row_dimensions[row].height
        if actual is None or abs(actual - height) > 0.01:
            raise ContractError(f"结果记录表行高不一致：第 {row} 行期望 {height}，实际 {actual}")
    for addr, label in HEADER_CELLS:
        if _norm(ws[addr].value) != label:
            raise ContractError(f"结果记录表表头字段不一致：{addr} 期望 {label!r}，实际 {ws[addr].value!r}")
    header = tuple(_norm(ws.cell(row=HEADER_ROW, column=c).value) for c in range(1, 10))
    if header != RESULT_COLUMNS:
        raise ContractError(f"结果记录表第 7 行列名不一致：{header}")
    if _norm(ws.cell(row=SECTION_ROW, column=1).value) != SECTION_TITLE:
        raise ContractError("结果记录表 A8 应为安全通用要求")
    print(
        f"[OK] 结果记录表版式：合并区 {len(MERGED_RANGES)} 处 / 列宽 {len(COLUMN_WIDTHS)} 列 / "
        f"表头行高 {len(HEADER_HEIGHTS)} 行 / 表头字段 {len(HEADER_CELLS)} 个"
    )


def _check_l3_rows(ws, items: list[dict]) -> None:
    if len(items) != LEVEL3_ROW_COUNT:
        raise ContractError(f"items_L3.yaml 应为 {LEVEL3_ROW_COUNT} 项，实际 {len(items)}")
    if ws.max_row != DATA_START_ROW + LEVEL3_ROW_COUNT - 1:
        raise ContractError(f"结果记录表数据行应为 {LEVEL3_ROW_COUNT} 行，实际 {ws.max_row - DATA_START_ROW + 1}")
    fields = ((2, "控制点"), (3, "控制项"), (7, "重要程度"), (8, "检查内容"), (9, "判断标准"))
    for seq, item in enumerate(items, 1):
        if item.get("seq") != seq or item.get("unit_no") != seq:
            raise ContractError(f"items_L3.yaml 第 {seq} 项序号不连续")
        row = DATA_START_ROW + seq - 1
        if _norm(ws.cell(row=row, column=1).value) != str(seq):
            raise ContractError(f"结果记录表第 {row} 行序号应为 {seq}")
        for column, field in fields:
            actual = _norm(ws.cell(row=row, column=column).value)
            expected = _norm(item.get(field)).strip()
            if actual.strip() != expected:
                label = "控制项文本与母版不一致" if field == "控制项" else f"{field}与母版不一致"
                raise ContractError(f"{label}：第 {seq} 项")
        for key in ("item_id", "policy", "mode", "binary", "optional_clause"):
            if key not in item:
                raise ContractError(f"items_L3.yaml 第 {seq} 项缺少字段 {key}")
        Policy(item["policy"])
    print(f"[OK] 结果记录表 34 行文本：控制点/控制项/重要程度/检查内容/判断标准 与 items_L3.yaml 逐字一致")


def _check_items_l3(items: list[dict]) -> None:
    binary = {item["seq"] for item in items if item["binary"]}
    expected_binary = {3, 6, 10, 13, 15, 18, 29, 30, 31, 32}
    if binary != expected_binary:
        raise ContractError(f"三级二值单元应为 {sorted(expected_binary)}，实际 {sorted(binary)}")
    na = {item["seq"] for item in items if item["policy"] == Policy.NA.value}
    if na != {19, 33, 34}:
        raise ContractError(f"三级默认不适用项应为 19/33/34，实际 {sorted(na)}")
    optional = {item["seq"] for item in items if item["optional_clause"]}
    if optional != {23}:
        raise ContractError(f"三级可选条款应仅 item 23，实际 {sorted(optional)}")
    for item in items:
        if item["policy"] == Policy.NA.value and item["binary"]:
            raise ContractError(f"item {item['seq']} 同时为不适用与二值单元")
    print("[OK] items_L3.yaml：34 项 / 二值 10 项 / 默认不适用 19/33/34 / 可选条款 23")


def _check_items_l2(items: list[dict]) -> None:
    if len(items) != LEVEL2_ROW_COUNT:
        raise ContractError(f"items_L2.yaml 应为 {LEVEL2_ROW_COUNT} 项，实际 {len(items)}")
    ids = [item.get("item_id") for item in items]
    expected_ids = [f"L2-CES1-{seq:02d}" for seq in range(1, LEVEL2_ROW_COUNT + 1)]
    if ids != expected_ids:
        raise ContractError("items_L2.yaml 编号应为 L2-CES1-01..23 连续")
    distribution = Counter(item["控制点"] for item in items)
    expected_distribution = {
        "身份鉴别": 3,
        "访问控制": 4,
        "安全审计": 3,
        "入侵防范": 5,
        "恶意代码防范": 1,
        "可信验证": 1,
        "数据完整性": 1,
        "数据备份恢复": 2,
        "剩余信息保护": 1,
        "个人信息保护": 2,
    }
    if dict(distribution) != expected_distribution:
        raise ContractError(f"二级控制点分布不一致：{dict(distribution)}")
    binary = {item["seq"] for item in items if item["binary"]}
    expected_binary = {3, 5, 9, 13, 14, 18, 20, 21}
    if binary != expected_binary:
        raise ContractError(f"二级二值单元应为 {sorted(expected_binary)}，实际 {sorted(binary)}")
    optional = {item["seq"] for item in items if item["optional_clause"]}
    if optional != {17}:
        raise ContractError(f"二级可选条款应仅 L2-CES1-17，实际 {sorted(optional)}")
    for item in items:
        Policy(item["policy"])
        if item["binary"] and item["policy"] == Policy.MIXED_PARTIAL.value:
            raise ContractError(f"{item['item_id']} 是二值单元，不许 mixed_partial")
    print("[OK] items_L2.yaml：23 项 / 控制点分布符合口径 / 二值 8 项 / 可选条款 17")


def _check_high_risk(rows: list[dict], l3_items: list[dict]) -> None:
    if len(rows) != 16:
        raise ContractError(f"high_risk.yaml 应为 16 条，实际 {len(rows)}")
    seqs = {item["seq"] for item in l3_items}
    required = (
        "hr_id",
        "level_min",
        "问题简述",
        "标准要求",
        "适用范围",
        "问题描述",
        "缓解措施",
        "风险评价",
        "整改建议",
        "可降风险",
        "降风险前提",
        "binds_items",
    )
    for index, row in enumerate(rows, 1):
        for key in required:
            if key == "可降风险":
                if not isinstance(row.get(key), bool):
                    raise ContractError(f"high_risk.yaml 第 {index} 条可降风险应为布尔值")
                continue
            if key == "降风险前提":
                if not isinstance(row.get(key), str):
                    raise ContractError(f"high_risk.yaml 第 {index} 条降风险前提应为字符串")
                continue
            if not row.get(key):
                raise ContractError(f"high_risk.yaml 第 {index} 条缺少 {key}")
        if row["可降风险"] and not row["降风险前提"].strip():
            raise ContractError(f"high_risk.yaml 第 {index} 条可降风险为 true 但缺少前提")
        if row["hr_id"] != f"HR-{index:02d}":
            raise ContractError(f"high_risk.yaml 编号不连续：期望 HR-{index:02d}，实际 {row['hr_id']}")
        if not set(row["binds_items"]) <= seqs:
            raise ContractError(f"{row['hr_id']} 绑定了不存在的测评项")
    if rows[13]["level_min"] != 4:
        raise ContractError("HR-14 应为 level_min 4（二/三级永不触发）")
    print("[OK] high_risk.yaml：16 条 / 绑定项均存在 / HR-14 限定四级")


def _check_checks_map(rows: list[dict], l3_items: list[dict], l2_items: list[dict]) -> None:
    seqs = {
        3: {item["seq"] for item in l3_items},
        2: {item["seq"] for item in l2_items},
    }
    seen: set[tuple] = set()
    mapped_l2: set[int] = set()
    for row in rows:
        key = (tuple(row["os_family"]), row["section"], row["title"])
        if key in seen:
            raise ContractError(f"checks_map.yaml 重复项：{key}")
        seen.add(key)
        for bind in row["binds"]:
            level = bind.get("level", 3)
            if level not in seqs:
                raise ContractError(f"checks_map.yaml 绑定等级非法：{level}")
            if bind["item"] not in seqs[level]:
                raise ContractError(
                    f"checks_map.yaml 引用了不存在的 {level} 级测评项 {bind['item']}"
                )
            if level == 2:
                mapped_l2.add(bind["item"])
    ubuntu = [row for row in rows if "debian" in row["os_family"]]
    # Ubuntu 系统基线仍按 44 块校验；中间件/数据库分区属于本期新增的可选扩展，
    # 单独计数，避免扩展映射稀释基线覆盖约束。
    extension_sections = {
        "0. DETECT",
        "1. NGINX",
        "2. APACHE",
        "3. TOMCAT",
        "1. MYSQL BASELINE",
    }
    baseline = [row for row in ubuntu if row["section"] not in extension_sections]
    if len(baseline) != 44:
        raise ContractError(
            f"checks_map.yaml Ubuntu 系统基线检查块应为 44，实际 {len(baseline)}"
        )
    print(
        f"[OK] checks_map.yaml：{len(rows)} 条映射 / Ubuntu 系统基线 44 块全覆盖"
        f"（中间件与数据库扩展 {len(ubuntu) - 44} 块）/ "
        f"三级与二级引用项均存在 / 二级映射 {len(mapped_l2)} 项"
    )


def _check_library(texts: list[dict]) -> None:
    if len(texts) != 321:
        raise ContractError(f"文案库应为 321 条，实际 {len(texts)}")
    for index, row in enumerate(texts, 1):
        for key in ("control_point", "control_item", "issue_summary", "issue_detail", "hazard", "remediation"):
            if key not in row:
                raise ContractError(f"文案库第 {index} 条缺少 {key}")
    print("[OK] texts/library.yaml：321 条文案 / 必需键齐全")


def run(templates: Path, pack: Path) -> None:
    _check_columns(templates / "asset_record.xlsx", ASSET_COLUMNS, "资产记录表")
    _check_columns(templates / "issue_summary.xlsx", ISSUE_COLUMNS, "安全问题汇总")
    _check_columns(templates / "major_risk.xlsx", MAJOR_COLUMNS, "重大安全隐患")

    l3 = _load_items(pack / "items_L3.yaml")
    l2 = _load_items(pack / "items_L2.yaml")
    ws = openpyxl.load_workbook(templates / "result_record.xlsx").worksheets[0]
    _check_template_layout(ws)
    _check_l3_rows(ws, l3)
    _check_items_l3(l3)
    _check_items_l2(l2)

    _check_high_risk(_load_yaml(pack / "high_risk.yaml"), l3)
    checks = _load_yaml(pack / "checks_map.yaml")
    _check_checks_map(checks["checks"], l3, l2)
    _check_library(_load_yaml(pack / "texts" / "library.yaml")["texts"])
    print("全部契约检查通过")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="caliper-contracts", description="四表契约与母版逐格比对")
    parser.add_argument("--templates", required=True, type=Path)
    parser.add_argument("--pack", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        run(args.templates, args.pack)
    except ContractError as exc:
        print(f"契约检查失败：{exc}", file=sys.stderr)
        return 1
    except (KeyError, TypeError) as exc:
        print(f"契约检查失败：pack 结构不完整（{exc}）", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
