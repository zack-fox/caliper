"""证据包装载：manifest 校验、sha256 校验、日志/JSON 解析。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import ValidationError

from core.evidence.logparse import ParseOutcome, parse_log_text
from core.model.entities import CheckBlock, CheckStatus, EvidencePackage, OutputLine, PackageManifest

REQUIRED_MANIFEST_FIELDS = (
    "package_id",
    "asset_id",
    "collected_at",
    "collector",
    "host",
    "os_family",
    "level",
    "files",
    "status",
)


class EvidenceError(Exception):
    """证据包不可用。"""


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_manifest(root: Path) -> PackageManifest:
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        raise EvidenceError(f"{root}：缺少 manifest.json")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"{manifest_path}：JSON 无法解析：{exc}") from exc
    missing = [key for key in REQUIRED_MANIFEST_FIELDS if key not in data]
    if missing:
        raise EvidenceError(f"{manifest_path}：缺少必需字段 {', '.join(missing)}")
    try:
        return PackageManifest.model_validate(data)
    except ValidationError as exc:
        raise EvidenceError(f"{manifest_path}：字段非法：{exc}") from exc


def _verify_files(root: Path, manifest: PackageManifest) -> None:
    for name, expected in manifest.files.items():
        path = root / name
        if not path.exists():
            raise EvidenceError(f"{root}：manifest 登记的文件不存在：{name}")
        actual = sha256_of(path)
        if actual.lower() != str(expected).lower():
            raise EvidenceError(
                f"{root}：{name} 的 sha256 不一致（期望 {expected}，实际 {actual}）"
            )


def _json_blocks(root: Path, warnings: list[str]) -> list[CheckBlock]:
    blocks: list[CheckBlock] = []
    session = 1
    for path in sorted((root / "checks").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        records = data if isinstance(data, list) else data.get("blocks", [])
        if not records:
            raise EvidenceError(f"{path}：没有 blocks")
        for record in records:
            try:
                output = [
                    OutputLine(line=int(item.get("line", index)), text=str(item["text"]))
                    if isinstance(item, dict)
                    else OutputLine(line=index, text=str(item))
                    for index, item in enumerate(record.get("output", []), 1)
                ]
                block = CheckBlock(
                    session=session,
                    block_index=int(record["block_index"]),
                    section=str(record.get("section", "")),
                    title=str(record["title"]),
                    os_family=record.get("os_family"),
                    status=CheckStatus(record.get("status", "collected")),
                    commands=list(record.get("cmd", [])),
                    file_refs=list(record.get("file", [])),
                    output=output,
                    source=path.name,
                )
            except (KeyError, ValueError) as exc:
                raise EvidenceError(f"{path}：检查块字段非法：{exc}") from exc
            blocks.append(block)
            session += 1
    warnings.append(f"{root}：使用 checks/*.json（推荐路径）")
    return blocks


def _log_blocks(root: Path, warnings: list[str]) -> list[CheckBlock]:
    logs = sorted((root / "raw").glob("*.log"))
    if not logs:
        raise EvidenceError(f"{root}：既没有 checks/*.json，也没有 raw/*.log")
    blocks: list[CheckBlock] = []
    session = 0
    for path in logs:
        outcome: ParseOutcome = parse_log_text(
            path.read_text(encoding="utf-8", errors="replace"), path.name, session_start=session
        )
        blocks.extend(outcome.blocks)
        warnings.extend(outcome.warnings)
        session = blocks[-1].session if blocks else session
    return blocks


def load_package(root: Path) -> EvidencePackage:
    """按 manifest → checks/*.json → raw/*.log 的顺序装载。任何结构问题都抛错。"""
    root = Path(root)
    if not root.is_dir():
        raise EvidenceError(f"证据包目录不存在：{root}")
    manifest = _load_manifest(root)
    _verify_files(root, manifest)

    warnings: list[str] = []
    registered = {str(name) for name in manifest.files}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            relative = path.relative_to(root).as_posix()
            if relative not in registered:
                warnings.append(f"{root}：文件未在 manifest 登记：{relative}")

    if (root / "checks").is_dir() and any((root / "checks").glob("*.json")):
        blocks = _json_blocks(root, warnings)
    else:
        blocks = _log_blocks(root, warnings)

    if manifest.status not in {"ok", "collected"}:
        warnings.append(f"{manifest.package_id}：采集状态为 {manifest.status}，全部检查块按未采集处理")
        for block in blocks:
            block.status = CheckStatus.FAILED

    return EvidencePackage(
        root=root, manifest=manifest, blocks=blocks, diagnostics=warnings
    )


def summarize(blocks: list[CheckBlock]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for block in blocks:
        counts[block.status.value] = counts.get(block.status.value, 0) + 1
    return counts
