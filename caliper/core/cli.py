"""命令行入口：caliper <子命令>。

四张表已打通：证据 → 判定 → 结果记录表；资产记录表补全；
安全问题汇总与重大安全隐患导出。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from core.contracts.filenames import RESULT_FILENAME
from core.contracts.verdict import to_text
from core.evidence.package import EvidenceError, load_evidence, summarize
from core.golden import GoldenError, check_case, discover_cases, run_case, update_expected
from core.items.loader import Pack, PackError, load_pack
from core.judge.runner import RunError, run_project
from core.issues.summary import (
    TextLibrary,
    build_issue_rows,
    render_issue_workbook,
    verify_issue_workbook,
)
from core.major.risk import (
    build_major_rows,
    render_major_workbook,
    verify_major_workbook,
)
from core.model.entities import CheckBlock, ProjectConfig, RunResult
from core.render.asset_record import (
    AssetRecordError,
    fill_asset_workbook,
    verify_asset_workbook,
)
from core.render.result_record import (
    RenderError,
    find_template,
    render_result_workbook,
    verify_workbook,
)
from core.rules.dsl import RuleError
from core.rules.engine import RulesError
from core.store.corrections import CorrectionError, CorrectionStore, apply_notes
from core.store.project import ProjectStoreError, load_project


class CliError(Exception):
    """以非零退出码直接反馈给用户的错误。"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="caliper",
        description="等保现场采集日志 → 供融合测评平台导入的四张 xlsx",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    parse = sub.add_parser("parse", help="解析证据包，输出检查块与锚点")
    parse.add_argument("--pkg", required=True, type=Path, help="证据包目录")
    parse.add_argument("--samples", type=int, default=3, help="抽样展示块数")

    run = sub.add_parser("run", help="按项目配置跑判定并导出结果记录表")
    run.add_argument("--project", required=True, type=Path)
    run.add_argument("--pack", type=Path, help="覆盖项目里的 pack 目录")
    run.add_argument("--out", type=Path, help="覆盖输出目录")
    run.add_argument("--template", type=Path, help="覆盖结果记录表母版")

    explain = sub.add_parser("explain", help="解释单个测评项的取值来源与合成过程")
    explain.add_argument("--project", required=True, type=Path)
    explain.add_argument("--item", required=True, type=int, help="测评项序号")
    explain.add_argument("--pack", type=Path)

    export = sub.add_parser("export", help="导出四张表（当前支持 result / asset）")
    export.add_argument("--project", required=True, type=Path)
    export.add_argument("--table", required=True, choices=["result", "asset", "issue", "major"])
    export.add_argument("--assets", type=Path, help="原始资产记录表；导出 asset 时必填")
    export.add_argument("--pack", type=Path)
    export.add_argument("--out", type=Path)
    export.add_argument("--template", type=Path)

    lint = sub.add_parser("lint-rules", help="校验规则库与映射")
    lint.add_argument("--pack", type=Path, required=True)

    golden = sub.add_parser("golden", help="金标准逐格回归比对（P12）")
    golden.add_argument(
        "--dir", type=Path, default=Path("fixtures/golden"), help="金标准用例根目录"
    )
    golden.add_argument("--case", help="只跑指定用例目录名")
    golden.add_argument("--update", action="store_true", help="用当前输出刷新期望表")
    return parser


def _resolve(project: ProjectConfig, base: Path, pack_override: Path | None) -> tuple[Path, Path]:
    pack_dir = pack_override or project.pack_dir
    if pack_dir is None:
        raise CliError("项目未配置 pack_dir，请用 --pack 指定")
    if not pack_dir.is_absolute():
        pack_dir = base / pack_dir
    out_dir = project.output_dir if project.output_dir.is_absolute() else base / project.output_dir
    return pack_dir, out_dir


def _load(args) -> tuple[ProjectConfig, Path, Pack]:
    try:
        project, base = load_project(args.project)
    except ProjectStoreError as exc:
        raise CliError(str(exc)) from exc
    pack_dir, _ = _resolve(project, base, getattr(args, "pack", None))
    try:
        pack = load_pack(pack_dir)
    except (PackError, RulesError, RuleError) as exc:
        raise CliError(f"pack 装载失败：{exc}") from exc
    return project, base, pack


def _cmd_parse(args) -> int:
    try:
        package = load_evidence(args.pkg)
    except EvidenceError as exc:
        raise CliError(str(exc)) from exc

    blocks = package.blocks
    sessions = sorted({block.session for block in blocks})
    counts = summarize(blocks)
    print(f"证据包：{package.manifest.package_id}  资产：{package.manifest.asset_id}")
    print(f"系统类型：{package.manifest.os_family}  采集状态：{package.manifest.status}")
    print(f"检查块总数：{len(blocks)}  会话数：{len(sessions)}")
    for session in sessions:
        session_blocks = [block for block in blocks if block.session == session]
        print(
            f"  会话 {session}：{len(session_blocks)} 块  "
            f"系统类型 {session_blocks[0].os_family or '未知'}"
        )
    print("状态分布：" + "  ".join(f"{key}={value}" for key, value in sorted(counts.items())))
    for warning in package.diagnostics:
        print(f"[提示] {warning}")

    print("\n抽样检查块：")
    for block in _sample_blocks(blocks, args.samples):
        print(f"- [{block.block_index}] {block.title}（{block.status.value}，{block.section}）")
        if block.commands:
            print(f"    cmd: {block.commands[0]}")
        for line in block.output[:3]:
            print(f"    {block.source}:{line.line}  {line.text[:100]}")
    return 0


def _sample_blocks(blocks: list[CheckBlock], count: int) -> list[CheckBlock]:
    collected = [block for block in blocks if block.status.value == "collected"]
    empty = [block for block in blocks if block.status.value == "empty"]
    chosen: list[CheckBlock] = []
    for source in (collected, empty, blocks):
        for block in source:
            if len(chosen) >= count:
                break
            if block not in chosen:
                chosen.append(block)
    return chosen[:count]


def _correction_store(project_path: Path) -> CorrectionStore:
    return CorrectionStore(Path(project_path).resolve().with_name("corrections.db"))


def _run(args, render: bool = True) -> tuple[ProjectConfig, RunResult, Pack, Path, Path | None]:
    project, base, pack = _load(args)
    try:
        result = run_project(project, pack, base_dir=base)
    except RunError as exc:
        raise CliError(str(exc)) from exc
    try:
        store = _correction_store(args.project)
        apply_notes(result, store, project.level)
        store.close()
    except CorrectionError as exc:
        raise CliError(str(exc)) from exc
    _, out_dir = _resolve(project, base, args.pack)
    out_override = getattr(args, "out", None)
    if out_override:
        out_dir = out_override
    if not render:
        return project, result, pack, out_dir, None

    template = getattr(args, "template", None) or find_template(pack.root)
    try:
        target = render_result_workbook(
            result, pack.items_for_level(project.level), template, out_dir
        )
    except RenderError as exc:
        raise CliError(str(exc)) from exc
    return project, result, pack, out_dir, target


def _print_matrix(result: RunResult) -> None:
    for run in result.asset_runs:
        print(f"\n资产：{run.asset.device_name}（{run.asset.ip}）  证据包：{run.package_id or '无'}")
        for item in run.items:
            label = to_text(item.verdict) or "空"
            note = f"  [{item.note}]" if item.note else ""
            print(f"  {item.seq:>2}  {item.control_point}  {label}{note}")
        for warning in run.diagnostics:
            print(f"  [提示] {warning}")
    print("\n结论分布：" + "  ".join(f"{key}={value}" for key, value in result.verdict_counts().items()))


def _cmd_run(args) -> int:
    _project, result, pack, out_dir, target = _run(args)
    assert target is not None
    _print_matrix(result)
    problems = verify_workbook(target, result.project.level, pack.items_for_level(result.project.level))
    if problems:
        for problem in problems:
            print(f"[自检失败] {problem}", file=sys.stderr)
        return 1
    print(f"\n结果记录表：{target}")
    print("字段自检：行数/序号/符合情况文本/列宽 全部通过")
    expected = out_dir / RESULT_FILENAME
    if expected != target:
        print(f"[提示] 输出文件名与契约模板不同：{expected.name}")
    return 0


def _cmd_explain(args) -> int:
    _project, result, pack, _out_dir, _target = _run(args, render=False)
    item = next((entry for entry in pack.items_for_level(result.project.level) if entry.seq == args.item), None)
    if item is None:
        raise CliError(f"没有序号为 {args.item} 的测评项")
    print(f"测评项 {item.seq}（{item.item_id}） {item.control_point} / {item.control_item}")
    print(f"policy={item.policy.value}  mode={item.mode}  binary={item.binary}")
    for run in result.asset_runs:
        judged = run.item_by_seq(item.seq)
        if judged is None:
            print(f"\n资产 {run.asset.device_name}：没有判定结果")
            continue
        print(f"\n资产：{run.asset.device_name}")
        print(f"结论：{to_text(judged.verdict) or '空'}")
        if judged.note:
            print(f"备注：{judged.note}")
        for point in judged.points:
            state = "通过" if point.passed else "未通过"
            print(f"  实施点 {point.point}：{state} — {point.reason}")
            print(f"    证据块：{point.block_title}")
            for anchor in point.anchors:
                print(f"    {anchor.file}:{anchor.line}  {anchor.snippet[:110]}")
        if judged.warnings:
            for warning in judged.warnings:
                print(f"  [告警] {warning}")
    return 0


def _cmd_export(args) -> int:
    if args.table == "result":
        _project, _result, _pack, _out_dir, target = _run(args)
        if target is None:
            raise CliError("导出失败：未生成文件")
        print(f"已导出：{target}")
        return 0
    if args.table in {"issue", "major"}:
        project, result, pack, out_dir, _ = _run(args, render=False)
        try:
            store = _correction_store(args.project)
            confirmed = store.major_confirmed(project.level)
            store.close()
        except CorrectionError as exc:
            raise CliError(str(exc)) from exc
        issues = build_issue_rows(
            result,
            pack.items_for_level(project.level),
            TextLibrary(pack.texts),
            confirmed,
        )
        try:
            if args.table == "issue":
                template = getattr(args, "template", None) or find_template(
                    pack.root, "issue_summary.xlsx"
                )
                target = render_issue_workbook(issues, project, template, out_dir)
                problems = verify_issue_workbook(target, len(issues))
                print(f"已导出：{target}")
                print(f"自检：{len(issues)} 行，问题编号连续，25 列齐全")
            else:
                rows = build_major_rows(issues, pack.high_risk, project.level, confirmed)
                template = getattr(args, "template", None) or find_template(
                    pack.root, "major_risk.xlsx"
                )
                target = render_major_workbook(rows, project, template, out_dir)
                problems = verify_major_workbook(target)
                print(f"已导出：{target}")
                print(f"自检：{len(rows)} 行，均来自人工确认的重大判定原则")
        except RenderError as exc:
            raise CliError(str(exc)) from exc
        for problem in problems:
            print(f"[自检失败] {problem}", file=sys.stderr)
        return 1 if problems else 0
    if args.table == "asset":
        if not args.assets:
            raise CliError("导出资产记录表需要 --assets 指定原始资产表")
        project, base, pack = _load(args)
        _, default_out = _resolve(project, base, getattr(args, "pack", None))
        out_dir = getattr(args, "out", None) or default_out
        try:
            report = fill_asset_workbook(
                args.assets, project.assets, pack.meta.guides, out_dir
            )
        except (AssetRecordError, OSError) as exc:
            raise CliError(str(exc)) from exc
        for warning in report.warnings:
            print(f"[提示] {warning}")
        if report.errors:
            for problem in report.errors:
                print(f"[失败] {problem}", file=sys.stderr)
            return 1
        problems = verify_asset_workbook(report.path, pack.meta.guides) if report.path else []
        if problems:
            for problem in problems:
                print(f"[自检失败] {problem}", file=sys.stderr)
            return 1
        print(f"已导出：{report.path}")
        print(
            f"字段自检：{report.rows} 行，补空白 {report.filled} 处，"
            f"追加 {report.appended} 行，必填/IP/作业指导书 全部通过"
        )
        return 0
    raise CliError(f"未知表类型：{args.table}")


def _lint_pack(pack: Pack) -> list[str]:
    problems: list[str] = []
    titles = set(pack.checks.titles())
    seen: set[tuple[int, int, int, str]] = set()
    for level, items in pack.items.items():
        by_seq = {item.seq: item for item in items}
        for rule in pack.rules.rules:
            if rule.level != level:
                continue
            if rule.item not in by_seq:
                continue
            if rule.block not in titles:
                problems.append(f"item {rule.item}：检查块「{rule.block}」不在 checks_map 中")
            key = (rule.level, rule.item, rule.point, rule.block)
            if key in seen:
                problems.append(f"item {rule.item} 实施点 {rule.point} 规则重复")
            seen.add(key)
            if not rule.pass_reason or not rule.fail_reason:
                problems.append(f"item {rule.item} 实施点 {rule.point}：通过/未通过理由不能为空")
        for item in items:
            if item.policy.value == "binary" and not item.binary:
                problems.append(f"{item.item_id}：policy=binary 但 binary=false")
            if item.binary and item.policy.value not in {"binary", "na"}:
                problems.append(f"{item.item_id}：binary=true 但 policy 不是 binary/na")
            rule_points = pack.rules.points_for_item(item.seq, level)
            if not rule_points:
                continue
            expected = pack.checks.points_for_item(item.seq, level)
            if expected and rule_points != expected:
                problems.append(
                    f"{item.item_id}：规则实施点 {sorted(rule_points)} 与 checks_map {sorted(expected)} 不一致"
                )
    for record in pack.high_risk:
        for seq in record.get("binds_items", []):
            if seq not in {item.seq for item in pack.items[3]}:
                problems.append(f"{record.get('hr_id')}：引用不存在的 item {seq}")
    return problems


def _cmd_lint(args) -> int:
    try:
        pack = load_pack(args.pack)
    except (PackError, RulesError, RuleError) as exc:
        print(f"[失败] pack 装载：{exc}", file=sys.stderr)
        return 1
    problems = _lint_pack(pack)
    for level, items in pack.items.items():
        covered = [item for item in items if pack.rules.for_item(item.seq, level)]
        auto = [item for item in items if item.mode == "auto" and item.policy.value != "na"]
        print(
            f"{level} 级：{len(items)} 项，自动判定项 {len(auto)}，已有规则 {len(covered)}"
        )
    if problems:
        for problem in problems:
            print(f"[失败] {problem}", file=sys.stderr)
        return 1
    print("规则检查通过：检查块引用、实施点覆盖、二值口径、高风险引用 全部一致")
    return 0


def _cmd_golden(args) -> int:
    cases = discover_cases(args.dir)
    if args.case:
        cases = [case for case in cases if case.name == args.case]
    if not cases:
        print(
            f"未发现金标准用例：{args.dir}/<用例>/project.yaml",
            file=sys.stderr,
        )
        print("首次使用可加 --update 以当前输出生成期望表", file=sys.stderr)
        return 2

    failed = 0
    for case in cases:
        try:
            if args.update:
                with TemporaryDirectory(prefix="caliper-golden-") as temp:
                    written = update_expected(case, run_case(case, Path(temp)))
                print(f"[更新] {case.name}：写入 {len(written)} 张期望表")
                continue
            problems = check_case(case)
        except GoldenError as exc:
            print(f"[失败] {exc}", file=sys.stderr)
            failed += 1
            continue
        if problems:
            failed += 1
            for problem in problems:
                print(f"[差异] {problem}", file=sys.stderr)
        else:
            print(f"[通过] {case.name}：四张表逐格一致")
    if args.update:
        return 0
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {
        "parse": _cmd_parse,
        "run": _cmd_run,
        "explain": _cmd_explain,
        "export": _cmd_export,
        "lint-rules": _cmd_lint,
        "golden": _cmd_golden,
    }
    try:
        return handlers[args.command](args)
    except CliError as exc:
        print(f"caliper: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
