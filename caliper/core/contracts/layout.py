"""结果记录表版式常量：sheet 名、表头块、合并区、列宽、行高、数据起始行。"""

from __future__ import annotations

SHEET_NAME_TEMPLATE = "{device}-{guide}"

SECTION_TITLE = "安全通用要求"

HEADER_ROW = 7
SECTION_ROW = 8
DATA_START_ROW = 9

HEADER_CELLS: tuple[tuple[str, str], ...] = (
    ("B2", "项目编号："),
    ("E2", "系统名称："),
    ("B3", "核查对象："),
    ("E3", "安全层面/安全类："),
    ("B4", "IP地址："),
    ("E4", "资产类别："),
    ("B5", "核查时间："),
    ("E5", "测评作业指导书："),
)

MERGED_RANGES: tuple[str, ...] = (
    "C2:D2",
    "F2:G2",
    "C3:D3",
    "F3:G3",
    "C4:D4",
    "F4:G4",
    "C5:D5",
    "F5:G5",
    "A8:I8",
)

COLUMN_WIDTHS: dict[str, float] = {
    "A": 9.5,
    "B": 28.5,
    "C": 38.0,
    "D": 33.1640625,
    "E": 28.5,
    "F": 33.1640625,
    "G": 14.1640625,
}

HEADER_HEIGHTS: dict[int, float] = {2: 16.0, 3: 16.0, 4: 16.0, 5: 16.0, 7: 16.0}

LEVEL3_ROW_COUNT = 34
LEVEL2_ROW_COUNT = 23

# 结果记录与备注的未采集写法
UNCOLLECTED_NOTE_PREFIX = "未采集："
