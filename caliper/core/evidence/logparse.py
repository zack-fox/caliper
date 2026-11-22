"""raw/*.log 解析：结果段 → 检查块 → 带行号的输出。

只做逐行状态机，禁止对整份日志做正则匹配。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from core.evidence.normalize import normalize_blocks
from core.model.entities import CheckBlock, CheckStatus, EvidenceAnchor, OutputLine

if TYPE_CHECKING:
    from core.checks.mapping import ChecksMap

RESULTS_MARKER = "===== RESULTS (collected) ====="
END_MARKER = "===== END OF REPORT ====="

_SECTION_RE = re.compile(r"^=====\s*(.+?)\s*=====$")
_BLOCK_RE = re.compile(r"^\[(\d+)\]\s*(.+)$")
_OS_RE = re.compile(r"baseline check", re.IGNORECASE)


class ParseError(Exception):
    """日志结构不符合约定。"""


@dataclass
class ParseOutcome:
    blocks: list[CheckBlock] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _os_family(header: str) -> str | None:
    """按脚本标识判断系统类型；CentOS/RHEL 脚本优先，避免提示符里的 ubuntu 干扰。"""
    lower = header.lower()
    if "centos" in lower or "rhel" in lower or "red hat" in lower:
        return "rhel"
    if "ubuntu" in lower or "debian" in lower:
        return "debian"
    return None


def classify_output(lines: list[str]) -> CheckStatus:
    """确认不存在（全部是 `no ...`）才算 empty；无任何输出算 failed。"""
    if not lines:
        return CheckStatus.FAILED
    if all(line.strip().lower().startswith("no ") for line in lines):
        return CheckStatus.EMPTY
    return CheckStatus.COLLECTED


def parse_log_text(
    text: str,
    filename: str,
    session_start: int = 0,
    checks: "ChecksMap | None" = None,
) -> ParseOutcome:
    outcome = ParseOutcome()
    lines = text.splitlines()

    in_results = False
    seen_results = False
    session = session_start
    section = ""
    os_family: str | None = None
    pending_os: str | None = None

    current: CheckBlock | None = None
    buffer: list[OutputLine] = []

    def flush() -> None:
        nonlocal current, buffer
        if current is None:
            return
        current.output = buffer
        current.status = classify_output([line.text for line in buffer])
        outcome.blocks.append(current)
        current = None
        buffer = []

    for number, raw in enumerate(lines, 1):
        line = raw.rstrip("\r")
        stripped = line.strip()

        if not in_results:
            if _OS_RE.search(line):
                pending_os = _os_family(line)
            if stripped == RESULTS_MARKER:
                flush()
                in_results = True
                seen_results = True
                session += 1
                os_family = pending_os
                section = ""
            continue

        if stripped == END_MARKER:
            flush()
            in_results = False
            continue

        section_match = _SECTION_RE.match(stripped)
        if section_match:
            flush()
            section = section_match.group(1)
            continue

        block_match = _BLOCK_RE.match(stripped)
        if block_match:
            flush()
            current = CheckBlock(
                session=session,
                block_index=int(block_match.group(1)),
                section=section,
                title=block_match.group(2).strip(),
                os_family=os_family,
                source=filename,
            )
            continue

        if current is None:
            continue

        if line.startswith("  cmd:"):
            current.commands.append(line[len("  cmd:") :].strip())
            current.command_anchors.append(
                EvidenceAnchor(file=filename, line=number, snippet=line.strip())
            )
            continue
        if line.startswith("  file:"):
            current.file_refs.append(line[len("  file:") :].strip())
            continue
        if line.startswith("  "):
            buffer.append(OutputLine(line=number, text=line[2:].rstrip()))
            continue

    flush()

    if not seen_results:
        if checks is not None:
            from core.evidence.sessionparse import SessionParseError, parse_session_text

            try:
                session = parse_session_text(text, filename, checks, session_start=session_start)
            except SessionParseError as exc:
                raise ParseError(str(exc)) from exc
            normalize_blocks(session.blocks, checks, session.warnings)
            return ParseOutcome(blocks=session.blocks, warnings=session.warnings)
        raise ParseError(f"{filename}：未找到结果段 `{RESULTS_MARKER}`")
    if not outcome.blocks:
        raise ParseError(f"{filename}：结果段内没有任何 `[NN] 标题` 检查块")

    if os_family is None:
        outcome.warnings.append(f"{filename}：未识别系统类型，仅按标题匹配检查块")
    normalize_blocks(outcome.blocks, checks, outcome.warnings)
    return outcome


def read_evidence_text(path: Path) -> str:
    """按 BOM/UTF-16 NUL 分布解码终端日志，避免 UTF-16 被替换成乱码。"""
    data = Path(path).read_bytes()
    if data.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
        return data.decode("utf-32", errors="replace")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    sample = data[:65536]
    even_nuls = sample[0::2].count(0)
    odd_nuls = sample[1::2].count(0)
    if odd_nuls > max(4, even_nuls * 2):
        return data.decode("utf-16-le", errors="replace")
    if even_nuls > max(4, odd_nuls * 2):
        return data.decode("utf-16-be", errors="replace")
    return data.decode("utf-8-sig", errors="replace")


def parse_log_file(path, session_start: int = 0, checks: "ChecksMap | None" = None) -> ParseOutcome:
    text = read_evidence_text(path)
    return parse_log_text(text, path.name, session_start=session_start, checks=checks)
