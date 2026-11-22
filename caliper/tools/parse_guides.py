"""解析等保测评指导书，产出规范化记录与质量报告。

三份指导书共用 17 列模板，按「等级 × 测评对象」拆成多个工作表：

* 网络设备（安全设备）：H3C / HUAWEI / Cisco / 中兴 ZTE / 安全设备通用模板；
* 数据库：MySQL / Oracle / SQL Server；
* 操作系统：Windows / Linux / AIX / ESXi / Solaris / Ubuntu(Debian)。

同一个工作表内的「单元编号」是该等级测评项的唯一标识。跨厂商同编号即同一
测评主题，但操作指导、结果模板、整改建议各不相同，因此本工具只做解析与质量
核查，不合并厂商命令。

用法::

    python tools/parse_guides.py \
        --source network=/path/网络设备.xlsx \
        --source database=/path/数据库.xlsx \
        --source os=/path/操作系统.xlsx \
        --out-dir guides
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

import openpyxl

HEADER = [
    "序号",
    "单元编号",
    "控制点",
    "测评项",
    "操作指导",
    "结果记录（符合）",
    "结果记录（部分符合）",
    "结果记录（不符合）",
    "结果判定（不适用）",
    "备注",
    "问题描述（不符合情形）",
    "关联威胁",
    "危害分析",
    "高风险判例（第一层）",
    "重大风险隐患（第二层）",
    "风险值",
    "整改建议",
]

DOMAINS = {
    "network": "网络设备（安全设备）",
    "database": "数据库",
    "os": "操作系统",
}

_LEVEL_TEXT = {"二": 2, "三": 3, "四": 4}
_NETWORK_SHEET = re.compile(r"^(?P<object>.+?)（(?P<level>[二三四])级）$")
_PRODUCT_SHEET = re.compile(r"^【(?P<level>[二三四])级】(?P<object>.+?)(?:数据库|操作系统)$")

# 判断「同一条款」时忽略标点与编号差异，例如句末「；」与「。」、
# 全角括号与半角括号、「a）」「a)」。
_TRAILING_PUNCT = re.compile(r"[\s;:.,]+$")
_CLAUSE_PREFIX = re.compile(r"^[a-z][).]")


class GuideError(Exception):
    """指导书不可解析。"""


@dataclass
class GuideRecord:
    domain: str
    level: int
    object: str
    object_kind: str
    sheet: str
    excel_row: int
    seq: str
    unit_no: str
    control_point: str
    item_text: str
    operation_guide: str
    result_pass: str
    result_partial: str
    result_fail: str
    result_na: str
    note: str
    problem: str
    threat: str
    harm: str
    high_risk_case: str
    major_risk: str
    risk_value: str
    remediation: str
    missing_fields: list[str] = field(default_factory=list)

    def text(self, key: str) -> str:
        return str(getattr(self, key))


@dataclass
class ParsedGuide:
    domain: str
    source: Path
    sheets: list[dict]
    records: list[GuideRecord]


def _clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _object_kind(domain: str, name: str) -> str:
    if domain == "network":
        return "generic_template" if "通用模板" in name else "vendor"
    if domain == "database":
        return "db_engine"
    return "os_family"


def parse_sheet_name(domain: str, sheet: str) -> tuple[int, str]:
    """从工作表名解析等级与测评对象。"""
    name = re.sub(r"\s+", "", sheet)
    pattern = _NETWORK_SHEET if domain == "network" else _PRODUCT_SHEET
    match = pattern.fullmatch(name)
    if not match:
        raise GuideError(f"无法从工作表名解析等级与对象：{sheet!r}")
    return _LEVEL_TEXT[match.group("level")], match.group("object")


def _row_headers(header: list[str]) -> dict[str, int]:
    index = {name: i for i, name in enumerate(header)}
    missing = [name for name in HEADER if name not in index]
    if missing:
        raise GuideError(f"缺少列：{missing}")
    return index


def _source_label(path: Path) -> str:
    """去掉上传工具附加的 UUID 前缀，只保留指导书名称。"""
    return path.name.rsplit("_", 1)[-1]


def parse_workbook(domain: str, path: Path) -> ParsedGuide:
    path = Path(path)
    if not path.exists():
        raise GuideError(f"指导书不存在：{path}")
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheets: list[dict] = []
    records: list[GuideRecord] = []
    try:
        for worksheet in workbook.worksheets:
            rows = list(worksheet.iter_rows(values_only=True))
            if not rows:
                continue
            header = [_clean(cell) for cell in rows[0]]
            index = _row_headers(header)
            level, obj = parse_sheet_name(domain, worksheet.title)
            body = 0
            for offset, row in enumerate(rows[1:], start=2):
                if not any(_clean(cell) for cell in row):
                    continue
                values = {name: _clean(row[i]) if i < len(row) else "" for name, i in index.items()}
                if not values["单元编号"]:
                    raise GuideError(f"{worksheet.title} 第 {offset} 行缺少单元编号")
                record = GuideRecord(
                    domain=domain,
                    level=level,
                    object=obj,
                    object_kind=_object_kind(domain, obj),
                    sheet=worksheet.title,
                    excel_row=offset,
                    seq=values["序号"],
                    unit_no=values["单元编号"],
                    control_point=values["控制点"],
                    item_text=values["测评项"],
                    operation_guide=values["操作指导"],
                    result_pass=values["结果记录（符合）"],
                    result_partial=values["结果记录（部分符合）"],
                    result_fail=values["结果记录（不符合）"],
                    result_na=values["结果判定（不适用）"],
                    note=values["备注"],
                    problem=values["问题描述（不符合情形）"],
                    threat=values["关联威胁"],
                    harm=values["危害分析"],
                    high_risk_case=values["高风险判例（第一层）"],
                    major_risk=values["重大风险隐患（第二层）"],
                    risk_value=values["风险值"],
                    remediation=values["整改建议"],
                    missing_fields=missing_fields(values),
                )
                records.append(record)
                body += 1
            sheets.append(
                {
                    "sheet": worksheet.title,
                    "level": level,
                    "object": obj,
                    "object_kind": _object_kind(domain, obj),
                    "rows": body,
                }
            )
    finally:
        workbook.close()
    if not records:
        raise GuideError(f"{path}：没有解析到任何测评记录")
    return ParsedGuide(domain=domain, source=path, sheets=sheets, records=records)


def missing_fields(values: dict[str, str]) -> list[str]:
    """列出真正为空的关键字段；「—」表示指导书已明确标注不适用，不算缺失。"""
    required = {
        "操作指导": values["操作指导"],
        "结果记录（符合）": values["结果记录（符合）"],
        "结果记录（不符合）": values["结果记录（不符合）"],
        "问题描述（不符合情形）": values["问题描述（不符合情形）"],
        "危害分析": values["危害分析"],
        "整改建议": values["整改建议"],
    }
    return [name for name, value in required.items() if not value.strip()]


def _normalize_clause(text: str) -> str:
    text = (
        text.replace("（", "(")
        .replace("）", ")")
        .replace("；", ";")
        .replace("：", ":")
        .replace("，", ",")
        .replace("。", ".")
        .replace("、", ",")
    )
    text = re.sub(r"\s+", "", text)
    text = _CLAUSE_PREFIX.sub("", text)
    return _TRAILING_PUNCT.sub("", text)


def find_duplicate_units(records: list[GuideRecord]) -> list[dict]:
    """同一工作表内重复出现的单元编号（真正的重复录入）。"""
    duplicates = []
    counter = Counter((r.domain, r.level, r.object, r.unit_no) for r in records)
    for (domain, level, obj, unit_no), count in sorted(counter.items()):
        if count > 1:
            duplicates.append(
                {
                    "domain": domain,
                    "level": level,
                    "object": obj,
                    "unit_no": unit_no,
                    "count": count,
                }
            )
    return duplicates


def find_shared_units(records: list[GuideRecord]) -> dict:
    """跨测评对象共享的单元编号数量；共享本身是设计意图，不是错误。"""
    grouped: dict[tuple[str, int], set[str]] = defaultdict(set)
    objects: dict[tuple[str, int], set[str]] = defaultdict(set)
    for record in records:
        key = (record.domain, record.level)
        grouped[key].add(record.unit_no)
        objects[key].add(record.object)
    return {
        f"{domain}-L{level}": {
            "objects": sorted(objects[(domain, level)]),
            "shared_units": len(grouped[(domain, level)]),
        }
        for domain, level in sorted(grouped)
    }


def find_missing_units(records: list[GuideRecord]) -> list[dict]:
    """按单元编号的数字后缀检查编号断层。"""
    findings = []
    grouped: dict[tuple[str, int], set[str]] = defaultdict(set)
    for record in records:
        grouped[(record.domain, record.level)].add(record.unit_no)
    for (domain, level), units in sorted(grouped.items()):
        numbers = sorted(_unit_number(unit) for unit in units)
        numbers = [number for number in numbers if number is not None]
        if not numbers:
            continue
        gaps = [number for number in range(numbers[0], numbers[-1] + 1) if number not in numbers]
        if gaps:
            findings.append(
                {
                    "domain": domain,
                    "level": level,
                    "expected_range": f"{numbers[0]}..{numbers[-1]}",
                    "actual_count": len(numbers),
                    "missing_numbers": gaps,
                }
            )
    return findings


def _unit_number(unit_no: str) -> int | None:
    match = re.search(r"(\d+)$", unit_no)
    return int(match.group(1)) if match else None


def find_conflicts(records: list[GuideRecord]) -> list[dict]:
    """同等级同单元编号在不同测评对象间的控制点或条款文本不一致。"""
    grouped: dict[tuple[str, int, str], list[GuideRecord]] = defaultdict(list)
    for record in records:
        grouped[(record.domain, record.level, record.unit_no)].append(record)

    conflicts = []
    for (domain, level, unit_no), entries in sorted(grouped.items()):
        if len(entries) < 2:
            continue
        base = entries[0]
        for other in entries[1:]:
            for field_name, label in (("control_point", "控制点"), ("item_text", "测评项")):
                left = _normalize_clause(base.text(field_name))
                right = _normalize_clause(other.text(field_name))
                if left != right:
                    conflicts.append(
                        {
                            "domain": domain,
                            "level": level,
                            "unit_no": unit_no,
                            "field": label,
                            "left_object": base.object,
                            "left_text": base.text(field_name),
                            "right_object": other.object,
                            "right_text": other.text(field_name),
                        }
                    )
    return conflicts


def field_fill_rates(records: list[GuideRecord]) -> dict[str, dict[str, float]]:
    fields = [
        "operation_guide",
        "result_pass",
        "result_partial",
        "result_fail",
        "result_na",
        "problem",
        "threat",
        "harm",
        "high_risk_case",
        "major_risk",
        "risk_value",
        "remediation",
    ]
    result: dict[str, dict[str, float]] = {}
    for domain in sorted({record.domain for record in records}):
        subset = [record for record in records if record.domain == domain]
        result[domain] = {
            name: round(
                sum(1 for record in subset if getattr(record, name) not in {"", "—"})
                / len(subset),
                4,
            )
            for name in fields
        }
    return result


def theme_distribution(records: list[GuideRecord]) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for domain in sorted({record.domain for record in records}):
        counter = Counter(
            record.control_point for record in records if record.domain == domain
        )
        result[domain] = dict(sorted(counter.items()))
    return result


def summarize(parsed: list[ParsedGuide]) -> dict:
    records = [record for guide in parsed for record in guide.records]
    return {
        "domains": {
            guide.domain: {
                "source": _source_label(guide.source),
                "sheets": len(guide.sheets),
                "records": len(guide.records),
                "by_sheet": guide.sheets,
            }
            for guide in parsed
        },
        "totals": {
            "sheets": sum(len(guide.sheets) for guide in parsed),
            "records": len(records),
        },
        "shared_units": find_shared_units(records),
        "duplicate_units": find_duplicate_units(records),
        "missing_units": find_missing_units(records),
        "conflicts": find_conflicts(records),
        "fill_rates": field_fill_rates(records),
        "themes": theme_distribution(records),
        "field_stats": field_stats(records),
        "empty_records": [
            {
                "domain": record.domain,
                "level": record.level,
                "object": record.object,
                "unit_no": record.unit_no,
                "fields": record.missing_fields,
            }
            for record in records
            if record.missing_fields
        ],
    }


_REPORT_FIELDS = {
    "operation_guide": "操作指导",
    "result_pass": "结果记录（符合）",
    "result_partial": "结果记录（部分符合）",
    "result_fail": "结果记录（不符合）",
    "result_na": "结果判定（不适用）",
    "problem": "问题描述（不符合情形）",
    "threat": "关联威胁",
    "harm": "危害分析",
    "high_risk_case": "高风险判例（第一层）",
    "major_risk": "重大风险隐患（第二层）",
    "risk_value": "风险值",
    "remediation": "整改建议",
}


def field_stats(records: list[GuideRecord]) -> dict[str, dict[str, dict[str, int]]]:
    """按领域统计每个字段的「真空」与「显式不适用（—）」数量。"""
    result: dict[str, dict[str, dict[str, int]]] = {}
    for domain in sorted({record.domain for record in records}):
        subset = [record for record in records if record.domain == domain]
        result[domain] = {}
        for name in _REPORT_FIELDS:
            result[domain][name] = {
                "empty": sum(1 for record in subset if not getattr(record, name).strip()),
                "not_applicable": sum(
                    1 for record in subset if getattr(record, name).strip() == "—"
                ),
            }
    return result


def render_report(summary: dict) -> str:
    lines = ["# 等保测评指导书解析报告", ""]
    totals = summary["totals"]
    lines += [
        f"- 工作表：{totals['sheets']}",
        f"- 原始测评记录：{totals['records']}",
        "",
        "## 1. 解析概览",
        "",
        "| 领域 | 工作表 | 记录数 | 来源文件 |",
        "| --- | ---: | ---: | --- |",
    ]
    for domain, info in summary["domains"].items():
        lines.append(
            f"| {DOMAINS.get(domain, domain)} | {info['sheets']} | {info['records']} | {info['source']} |"
        )

    lines += ["", "## 2. 单元编号共享情况", "", "同一等级下，各测评对象共用同一套单元编号；这是「共同测评主题 + 多采集适配器」的基础。", ""]
    lines += ["| 领域/等级 | 测评对象 | 共享单元数 |", "| --- | --- | ---: |"]
    for key, info in summary["shared_units"].items():
        lines.append(f"| {key} | {'、'.join(info['objects'])} | {info['shared_units']} |")

    lines += ["", "## 3. 重复项", ""]
    if summary["duplicate_units"]:
        lines += ["| 领域 | 等级 | 测评对象 | 单元编号 | 次数 |", "| --- | ---: | --- | --- | ---: |"]
        for item in summary["duplicate_units"]:
            lines.append(
                f"| {item['domain']} | {item['level']} | {item['object']} | {item['unit_no']} | {item['count']} |"
            )
    else:
        lines.append("未发现同一工作表内重复的单元编号。")

    lines += ["", "## 4. 缺失项", ""]
    if summary["missing_units"]:
        lines += ["| 领域 | 等级 | 编号范围 | 实际条数 | 缺失编号 |", "| --- | ---: | --- | ---: | --- |"]
        for item in summary["missing_units"]:
            lines.append(
                f"| {item['domain']} | {item['level']} | {item['expected_range']} | "
                f"{item['actual_count']} | {item['missing_numbers']} |"
            )
        lines.append("")
        lines.append("编号断层需回查指导书原文，不能自行补齐测评项。")
        missing_by_domain = {item["domain"] for item in summary["missing_units"]}
        if len(missing_by_domain) > 1:
            lines.append("")
            lines.append(
                "多个领域在同一等级出现相同断层，提示可能是编号规范而非漏项；"
                "仍以指导书原文为准，不得自行补号。"
            )
    else:
        lines.append("各等级单元编号连续。")

    empty = summary["empty_records"]
    lines += ["", "### 关键字段真空", ""]
    if empty:
        lines += ["| 领域 | 等级 | 测评对象 | 单元编号 | 空字段 |", "| --- | ---: | --- | --- | --- |"]
        for item in empty:
            lines.append(
                f"| {item['domain']} | {item['level']} | {item['object']} | {item['unit_no']} | "
                f"{'、'.join(item['fields'])} |"
            )
        lines.append("")
        lines.append("真空字段意味着该测评对象缺少可直接复用的结果模板或整改依据，生成规则时必须显式标记人工核查，不得套用其他对象文本。")
    else:
        lines.append("关键字段均有内容。")

    lines += ["", "### 显式不适用（—）", "", "| 领域 | 字段 | 不适用条数 |", "| --- | --- | ---: |"]
    for domain, fields in summary["field_stats"].items():
        for name, stat in fields.items():
            if stat["not_applicable"]:
                lines.append(
                    f"| {domain} | {_REPORT_FIELDS[name]} | {stat['not_applicable']} |"
                )

    lines += ["", "## 5. 冲突项", ""]
    if summary["conflicts"]:
        lines += [
            "| 领域 | 等级 | 单元编号 | 字段 | 对象 A | 对象 B |",
            "| --- | ---: | --- | --- | --- | --- |",
        ]
        for item in summary["conflicts"]:
            lines.append(
                f"| {item['domain']} | {item['level']} | {item['unit_no']} | {item['field']} | "
                f"{item['left_object']}：{_short(item['left_text'])} | "
                f"{item['right_object']}：{_short(item['right_text'])} |"
            )
        lines.append("")
        lines.append("冲突项必须人工确认后再生成规则，不得按多数派自动覆盖。")
    else:
        lines.append("未发现控制点或测评项文本冲突。")

    lines += ["", "## 6. 字段填充率", "", "| 领域 | 字段 | 填充率 | 真空 | 不适用 |", "| --- | --- | ---: | ---: | ---: |"]
    for domain, fields in summary["fill_rates"].items():
        for name, rate in fields.items():
            stat = summary["field_stats"][domain][name]
            lines.append(
                f"| {domain} | {_REPORT_FIELDS[name]} | {rate:.0%} | "
                f"{stat['empty']} | {stat['not_applicable']} |"
            )

    lines += ["", "## 7. 业务主题分布", ""]
    for domain, themes in summary["themes"].items():
        lines.append(f"### {DOMAINS.get(domain, domain)}")
        lines.append("")
        lines.append("| 控制点 | 记录数 |")
        lines.append("| --- | ---: |")
        for theme, count in themes.items():
            lines.append(f"| {theme} | {count} |")
        lines.append("")
    return "\n".join(lines) + "\n"


def _short(text: str, limit: int = 60) -> str:
    text = re.sub(r"\s+", " ", text)
    return text if len(text) <= limit else text[:limit] + "…"


def write_outputs(parsed: list[ParsedGuide], out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    reports_dir = out_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize(parsed)

    for guide in parsed:
        payload = {
            "domain": guide.domain,
            "source": _source_label(guide.source),
            "sheets": guide.sheets,
            "records": [asdict(record) for record in guide.records],
        }
        name = f"{guide.domain}.json"
        (out_dir / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    (reports_dir / "guide_review.md").write_text(
        render_report(summary), encoding="utf-8"
    )
    (reports_dir / "guide_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def _parse_source(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("--source 需写成 domain=path")
    domain, path = value.split("=", 1)
    domain = domain.strip()
    if domain not in DOMAINS:
        raise argparse.ArgumentTypeError(f"未知领域 {domain!r}，可选 {sorted(DOMAINS)}")
    return domain, Path(path).expanduser()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="解析等保测评指导书并生成质量报告")
    parser.add_argument(
        "--source",
        action="append",
        type=_parse_source,
        required=True,
        metavar="DOMAIN=PATH",
        help="network=网络设备.xlsx / database=数据库.xlsx / os=操作系统.xlsx",
    )
    parser.add_argument("--out-dir", default="guides", help="输出目录，默认 guides")
    args = parser.parse_args(argv)

    parsed = [parse_workbook(domain, path) for domain, path in args.source]
    summary = write_outputs(parsed, Path(args.out_dir))
    totals = summary["totals"]
    print(
        f"解析完成：{totals['sheets']} 个工作表，{totals['records']} 条记录；"
        f"重复 {len(summary['duplicate_units'])}，缺失 {len(summary['missing_units'])}，"
        f"冲突 {len(summary['conflicts'])}，空字段记录 {len(summary['empty_records'])}"
    )
    print(f"报告：{Path(args.out_dir) / 'reports' / 'guide_review.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
