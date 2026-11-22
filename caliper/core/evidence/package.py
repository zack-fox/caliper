"""证据装载：结构化证据包（manifest）与原始证据目录（日志/截图）两种模式。"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from core.evidence.logparse import ParseError, ParseOutcome, parse_log_text, read_evidence_text
from core.evidence.normalize import normalize_blocks

if TYPE_CHECKING:
    from core.checks.mapping import ChecksMap
from core.model.entities import (
    CheckBlock,
    CheckStatus,
    EvidenceFile,
    EvidencePackage,
    OutputLine,
    PackageManifest,
)

TEXT_SUFFIXES = {".log", ".txt", ".out", ".cmd", ".json"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".heic"}
SHEET_SUFFIXES = {".xlsx", ".xls", ".csv", ".tsv"}
CONFIG_SUFFIXES = {".conf", ".cfg", ".ini", ".yaml", ".yml", ".xml", ".toml"}
CODE_SUFFIXES = {".py", ".sh", ".sql", ".ps1", ".js", ".ts", ".php"}

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


def _json_blocks(
    root: Path, warnings: list[str], checks: "ChecksMap | None" = None
) -> list[CheckBlock]:
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
                    OutputLine(
                        line=int(item.get("line", index)),
                        text=str(item["text"]),
                        snippet=str(item.get("snippet", "")),
                    )
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
                    commands=list(record.get("cmd", record.get("commands", []))),
                    command_anchors=list(record.get("command_anchors", [])),
                    file_refs=list(record.get("file", record.get("file_refs", []))),
                    output=output,
                    facts=list(record.get("facts", [])),
                    source=path.relative_to(root).as_posix(),
                )
            except (KeyError, ValueError) as exc:
                raise EvidenceError(f"{path}：检查块字段非法：{exc}") from exc
            blocks.append(block)
            session += 1
    warnings.append(f"{root}：使用 checks/*.json（推荐路径）")
    normalize_blocks(blocks, checks, warnings)
    return blocks


def _log_blocks(root: Path, warnings: list[str], checks: "ChecksMap | None" = None) -> list[CheckBlock]:
    logs = sorted((root / "raw").glob("*.log"))
    if not logs:
        raise EvidenceError(f"{root}：既没有 checks/*.json，也没有 raw/*.log")
    blocks: list[CheckBlock] = []
    session = 0
    for path in logs:
        outcome: ParseOutcome = parse_log_text(
            read_evidence_text(path),
            path.relative_to(root).as_posix(),
            session_start=session,
            checks=checks,
        )
        blocks.extend(outcome.blocks)
        warnings.extend(outcome.warnings)
        session = blocks[-1].session if blocks else session
    return blocks


def load_package(root: Path, checks: "ChecksMap | None" = None) -> EvidencePackage:
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
        blocks = _json_blocks(root, warnings, checks=checks)
    else:
        blocks = _log_blocks(root, warnings, checks=checks)

    if manifest.status not in {"ok", "collected"}:
        warnings.append(f"{manifest.package_id}：采集状态为 {manifest.status}，全部检查块按未采集处理")
        for block in blocks:
            block.status = CheckStatus.FAILED

    evidence_files = _inventory_files(root, blocks)

    return EvidencePackage(
        root=root,
        manifest=manifest,
        blocks=blocks,
        evidence_files=evidence_files,
        diagnostics=warnings,
    )


def _inventory_files(root: Path, blocks: list[CheckBlock]) -> list[EvidenceFile]:
    """登记所有原始材料，并用相对路径区分目录内的同名文件。"""
    parsed = {block.source for block in blocks}
    inventory: list[EvidenceFile] = []
    paths = [root] if root.is_file() else [item for item in root.rglob("*") if item.is_file()]
    for path in sorted(paths):
        if path.name == "manifest.json":
            continue
        relative = path.name if root.is_file() else path.relative_to(root).as_posix()
        suffix = path.suffix.lower()
        kind = (
            "image" if suffix in IMAGE_SUFFIXES else
            "spreadsheet" if suffix in SHEET_SUFFIXES else
            "configuration" if suffix in CONFIG_SUFFIXES else
            "code" if suffix in CODE_SUFFIXES else
            "text" if suffix in TEXT_SUFFIXES else
            "file"
        )
        inventory.append(
            EvidenceFile(
                path=relative,
                kind=kind,
                size=path.stat().st_size,
                sha256=sha256_of(path),
                analyzed=relative in parsed,
            )
        )
    return inventory


def summarize(blocks: list[CheckBlock]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for block in blocks:
        counts[block.status.value] = counts.get(block.status.value, 0) + 1
    return counts


def text_evidence_files(root: Path) -> list[Path]:
    """可解析的文本证据：单文件本身或目录下递归查找。"""
    root = Path(root)
    if root.is_file():
        return [root] if root.suffix.lower() in TEXT_SUFFIXES else []
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES
    )


def media_files(root: Path) -> list[Path]:
    """截图/照片：只作附件，不参与自动判定。"""
    root = Path(root)
    if root.is_file():
        return [root] if root.suffix.lower() in IMAGE_SUFFIXES else []
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )


def load_evidence(
    root: Path,
    host: str = "",
    level: int = 3,
    checks: "ChecksMap | None" = None,
) -> EvidencePackage:
    """装载证据：有 manifest.json 走结构化校验，没有则按原始证据目录解析。

    原始证据可以是单个 .log/.txt 文件，也可以是包含任意日志、命令输出、
    txt、截图的目录；图片计入诊断信息但不参与自动判定。
    """
    root = Path(root)
    if not root.exists():
        raise EvidenceError(f"证据目录不存在：{root}")
    if root.is_dir() and (root / "manifest.json").is_file():
        try:
            return load_package(root, checks=checks)
        except EvidenceError as exc:
            warnings = [f"manifest 校验失败，改按原始证据解析：{exc}"]
    else:
        warnings = []

    blocks: list[CheckBlock] = []
    session = 0
    for path in text_evidence_files(root):
        try:
            source = path.name if root.is_file() else path.relative_to(root).as_posix()
            outcome: ParseOutcome = parse_log_text(
                read_evidence_text(path),
                source,
                session_start=session,
                checks=checks,
            )
        except ParseError as exc:
            warnings.append(f"{path.name}：{exc}")
            continue
        blocks.extend(outcome.blocks)
        warnings.extend(outcome.warnings)
        session = blocks[-1].session if blocks else session

    images = media_files(root)
    if images:
        warnings.append(f"图片 {len(images)} 张：仅作证据附件，不参与自动判定")
    if not text_evidence_files(root):
        warnings.append("未发现可解析的文本证据（.log / .txt / .out / .cmd）")
    if not blocks:
        warnings.append("未识别到检查块，全部测评项将按未采集处理")

    os_family = next(
        (block.os_family for block in blocks if block.os_family in {"debian", "rhel"}),
        "unknown",
    )
    manifest = PackageManifest(
        package_id=root.name,
        asset_id="",
        collected_at=datetime.now(),
        collector="manual-evidence",
        host=host or root.stem,
        os_family=os_family,
        level=level,
        files={},
        status="collected" if blocks else "empty",
        note="原始证据（无 manifest）",
    )
    evidence_files = _inventory_files(root, blocks)
    return EvidencePackage(
        root=root,
        manifest=manifest,
        blocks=blocks,
        evidence_files=evidence_files,
        diagnostics=warnings,
    )
