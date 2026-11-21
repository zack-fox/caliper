"""把项目 + 证据包 + pack 跑成判定矩阵。"""

from __future__ import annotations

from pathlib import Path

from core.checks.mapping import ChecksMap, index_blocks
from core.contracts.policy import Policy
from core.contracts.verdict import Verdict
from core.evidence.package import EvidenceError, load_package
from core.items.loader import Pack
from core.judge.synth import judge_item
from core.model.entities import Asset, AssetRun, CheckBlock, Item, ItemResult, ProjectConfig, RunResult


class RunError(Exception):
    """跑批失败（配置或证据不可用）。"""


def _empty_run(asset: Asset, items: list[Item], reason: str) -> AssetRun:
    results = []
    for item in items:
        if item.policy is Policy.NA:
            results.append(
                ItemResult(
                    item_id=item.item_id,
                    seq=item.seq,
                    control_point=item.control_point,
                    importance=item.importance,
                    verdict=Verdict.NOT_APPLICABLE,
                    result_text="默认不适用",
                )
            )
        else:
            results.append(
                ItemResult(
                    item_id=item.item_id,
                    seq=item.seq,
                    control_point=item.control_point,
                    importance=item.importance,
                    verdict=Verdict.UNCOLLECTED,
                    note=f"未采集：{reason}",
                )
            )
    return AssetRun(asset=asset, items=results)


def _judge_package(
    asset: Asset,
    items: list[Item],
    checks: ChecksMap,
    ruleset,
    package_root: Path,
    level: int,
) -> AssetRun:
    package = load_package(package_root)
    blocks: dict[str, CheckBlock] = index_blocks(
        package.blocks, checks, package.manifest.os_family
    )
    run = AssetRun(
        asset=asset,
        package_id=package.manifest.package_id,
        os_family=package.manifest.os_family,
        diagnostics=list(package.diagnostics),
    )
    if package.manifest.level != level:
        run.diagnostics.append(
            f"证据包标称等级 {package.manifest.level} 与项目等级 {level} 不一致"
        )
    for item in items:
        result = judge_item(
            item, ruleset, blocks, checks.points_for_item(item.seq, item.level)
        )
        run.items.append(result)
    return run


def run_project(project: ProjectConfig, pack: Pack, base_dir: Path | None = None) -> RunResult:
    base = Path(base_dir) if base_dir else Path.cwd()
    evidence_root = project.evidence_root if project.evidence_root.is_absolute() else base / project.evidence_root
    items = pack.items_for_level(project.level)
    if not project.assets:
        raise RunError("项目没有任何资产")

    result = RunResult(project=project)
    for asset in project.assets:
        if not asset.evidence_package:
            result.asset_runs.append(_empty_run(asset, items, "未关联证据包"))
            continue
        package_root = evidence_root / asset.evidence_package
        try:
            result.asset_runs.append(
                _judge_package(
                    asset, items, pack.checks, pack.rules, package_root, project.level
                )
            )
        except EvidenceError as exc:
            raise RunError(f"{asset.device_name}：{exc}") from exc
    return result
