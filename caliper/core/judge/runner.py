"""把项目 + 证据包 + pack 跑成判定矩阵。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from core.checks.mapping import ChecksMap, index_blocks
from core.contracts.policy import Policy
from core.contracts.verdict import Verdict
from core.evidence.package import EvidenceError, load_evidence
from core.items.loader import Pack
from core.judge.synth import judge_item
from core.model.entities import Asset, AssetRun, CheckBlock, Item, ItemResult, ProjectConfig, RunResult


class RunError(Exception):
    """跑批失败（配置或证据不可用）。"""


def _fingerprint(payload: object) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _assessment_fingerprint(items: list[Item], checks: ChecksMap, ruleset, level: int) -> str:
    return _fingerprint(
        {
            "level": level,
            "items": [item.model_dump(mode="json") for item in items],
            "checks": [
                check.model_dump(mode="json")
                for check in checks.checks
                if any(binding.level == level for binding in check.binds)
                or check.kind == "context"
            ],
            "rules": [
                rule.model_dump(mode="json")
                for rule in ruleset.rules
                if rule.level == level
            ],
        }
    )


def _empty_run(
    asset: Asset, items: list[Item], reason: str, assessment_fingerprint: str
) -> AssetRun:
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
    return AssetRun(
        asset=asset,
        items=results,
        basis_fingerprint=_fingerprint(
            {
                "assessment": assessment_fingerprint,
                "asset": asset.model_dump(mode="json", exclude={"evidence_package"}),
                "reason": reason,
            }
        ),
    )


def _judge_package(
    asset: Asset,
    items: list[Item],
    checks: ChecksMap,
    ruleset,
    package_root: Path,
    level: int,
    assessment_fingerprint: str,
) -> AssetRun:
    package = load_evidence(package_root, host=asset.device_name, level=level, checks=checks)
    blocks: dict[str, CheckBlock] = index_blocks(
        package.blocks, checks, package.manifest.os_family
    )
    run = AssetRun(
        asset=asset,
        package_id=package.manifest.package_id,
        os_family=package.manifest.os_family,
        diagnostics=list(package.diagnostics),
        basis_fingerprint=_fingerprint(
            {
                "assessment": assessment_fingerprint,
                "asset": asset.model_dump(mode="json", exclude={"evidence_package"}),
                "manifest": {
                    "os_family": package.manifest.os_family,
                    "level": package.manifest.level,
                    "host": package.manifest.host,
                },
                "files": [
                    {"path": entry.path, "sha256": entry.sha256}
                    for entry in package.evidence_files
                ],
            }
        ),
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

    configured_titles = set(checks.titles())
    judged_titles = {
        rule.block
        for item in items
        for rule in ruleset.for_item(item.seq, item.level)
    }
    judge_mapped_titles = {
        check.title
        for check in checks.checks
        if check.kind == "judge"
        and any(binding.level == level for binding in check.binds)
    }
    unmapped = [block for block in package.blocks if block.title not in configured_titles]
    if unmapped:
        details = "; ".join(
            f"{block.title}（{block.source}）" for block in unmapped
        )
        run.diagnostics.append(
            f"未映射：{len(unmapped)} 个检查块在 checks_map.yaml 中没有对应标题，"
            f"未参与自动判定：{details}"
        )

    unsupported = [
        block
        for block in package.blocks
        if block.title in configured_titles
        and block.os_family
        and checks.allowed_families(block.title)
        and block.os_family not in checks.allowed_families(block.title)
    ]
    if unsupported:
        details = "; ".join(
            f"{block.title}（{block.os_family}，{block.source}）" for block in unsupported
        )
        run.diagnostics.append(
            f"{len(unsupported)} 个检查块的系统类型与映射规则不符，未参与自动判定：{details}"
        )

    collected_only = [
        block
        for block in package.blocks
        if block.title in judge_mapped_titles
        and block.title not in judged_titles
        and block not in unsupported
    ]
    if collected_only:
        details = "; ".join(
            f"{block.title}（{block.source}）" for block in collected_only
        )
        run.diagnostics.append(
            f"{len(collected_only)} 个检查块虽有采集映射，但当前等级没有对应自动判定规则：{details}"
        )

    unimplemented = [
        result.seq
        for result in run.items
        if "规则库无对应条目" in result.note
    ]
    if unimplemented:
        run.diagnostics.append(
            f"{len(unimplemented)} 个自动测评项规则库无对应条目："
            + "、".join(map(str, unimplemented))
        )
    uncovered = [
        result.seq
        for result in run.items
        if "规则库缺少实施点" in result.note
    ]
    if uncovered:
        run.diagnostics.append(
            f"{len(uncovered)} 个自动测评项的实施点未被规则覆盖："
            + "、".join(map(str, uncovered))
        )

    by_title: dict[str, list[CheckBlock]] = {}
    for block in package.blocks:
        by_title.setdefault(block.title, []).append(block)
    duplicates = []
    for title, candidates in by_title.items():
        selected = blocks.get(title)
        if selected is not None and len(candidates) > 1:
            ignored = [block.source for block in candidates if block is not selected]
            if ignored:
                duplicates.append(f"{title}：采用 {selected.source}，忽略 {', '.join(ignored)}")
    if duplicates:
        run.diagnostics.append(
            "存在同名检查块；为避免重复证据被重复计分，当前只采用首个匹配块："
            + "; ".join(duplicates)
        )
    return run


def run_project(project: ProjectConfig, pack: Pack, base_dir: Path | None = None) -> RunResult:
    base = Path(base_dir) if base_dir else Path.cwd()
    evidence_root = project.evidence_root if project.evidence_root.is_absolute() else base / project.evidence_root
    items = pack.items_for_level(project.level)
    assessment_fingerprint = _assessment_fingerprint(
        items, pack.checks, pack.rules, project.level
    )
    if not project.assets:
        raise RunError("项目没有任何资产")

    result = RunResult(project=project)
    for asset in project.assets:
        if not asset.evidence_package:
            result.asset_runs.append(
                _empty_run(asset, items, "未关联证据包", assessment_fingerprint)
            )
            continue
        package_root = evidence_root / asset.evidence_package
        try:
            result.asset_runs.append(
                _judge_package(
                    asset,
                    items,
                    pack.checks,
                    pack.rules,
                    package_root,
                    project.level,
                    assessment_fingerprint,
                )
            )
        except EvidenceError as exc:
            raise RunError(f"{asset.device_name}：{exc}") from exc
    return result
