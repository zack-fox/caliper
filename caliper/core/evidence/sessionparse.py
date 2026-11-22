"""SecureCRT/终端/MySQL 交互会话的逐行只读解析。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.checks.mapping import CheckBinding, ChecksMap, SessionBinding
from core.evidence.normalize import detect_os_family, normalize_session_command
from core.model.entities import CheckBlock, CheckStatus, DerivedFact, EvidenceAnchor, OutputLine

_TIMESTAMP_RE = re.compile(r"^\[\d{4}/\d{1,2}/\d{1,2}\s+\d{1,2}:\d{2}:\d{2}\]\s?")
_MYSQL_PROMPT_RE = re.compile(r"^mysql(?:\s+[^>]*)?>\s?(.*)$", re.I)
_MYSQL_CONT_RE = re.compile(r"^\s*->\s?(.*)$")
_SHELL_PROMPTS = [
    re.compile(r"^\[[^\]\s]+@[^\]]+\][#$]\s?(.*)$"),
    re.compile(r"^[^\s@]+@[^\s:]+:[^#$]*[#$]\s?(.*)$"),
    re.compile(r"^(?:bash|sh)-\d+(?:\.\d+)*[#$]\s?(.*)$"),
    re.compile(r"^(?:~|/)[^#$]*[#$]\s?(.*)$"),
]
# H3C/HUAWEI/ZTE 常见用户视图 <H3C> 与系统视图 [H3C]、[~HUAWEI]、[H3C-GE1/0/1]。
_NETWORK_PROMPTS = [
    re.compile(r"^<([A-Za-z][\w.-]*)>\s?(.*)$"),
    re.compile(r"^\[(?:~)?([A-Za-z][\w.-]*)(?:-[^\]]*)?\]\s?(.*)$"),
]
# Cisco IOS 提示符：Router#、Switch#、Router(config)#、hostname>。
_CISCO_PROMPTS = [
    re.compile(r"^([A-Za-z][\w.-]*)\([^)]*\)#\s?(.*)$"),
    re.compile(r"^([A-Za-z][\w.-]*)[#>]\s?(.*)$"),
]
_SENSITIVE_RE = re.compile(
    r"(?:--password(?:=|\s)|\bpasswd\s+-|\bpassword\s*\(|\bIDENTIFIED\s+|\bmysql(?:native|admin)?\b[^\n]*\s-p\S)",
    re.I,
)
_ERROR_RE = re.compile(
    r"command not found|permission denied|operation not permitted|access denied|no such file or directory|cannot (?:access|stat|open)\b|^\s*ERROR\s+\d+|^\s*ERROR\s*:\s*|^\s*Error:\s*|^\s*%\s*(?:Invalid|Unrecognized|Incomplete)\b|^\s*Unrecognized command\b",
    re.I,
)
_NETWORK_WRITE_RE = re.compile(
    r"^\s*(?:system-view|sys\b|undo\b|save\b|reset\b|reboot\b|delete\b|format\b|startup\b|shutdown\b|no\b|configure\b|conf\s+t\b|write\b|erase\b|copy\b)",
    re.I,
)
_EMPTY_SET_RE = re.compile(r"^\s*Empty set(?:\s*\([^)]*\))?\s*$", re.I)
_ROWS_STATUS_RE = re.compile(r"^\s*\d+\s+rows?\s+in\s+set(?:\s*\([^)]*\))?\s*$", re.I)


class SessionParseError(Exception):
    """不是可识别的交互会话，或没有任何命令命中映射。"""


@dataclass
class _Command:
    kind: str
    text: str
    line: int
    snippet: str
    output: list[OutputLine] = field(default_factory=list)
    empty_set: bool = False
    failed: bool = False
    closed: bool = False


@dataclass
class SessionOutcome:
    blocks: list[CheckBlock] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _without_timestamp(line: str) -> str:
    return _TIMESTAMP_RE.sub("", line, count=1)


def _prompt(line: str) -> tuple[str, str, bool] | None:
    if match := _MYSQL_PROMPT_RE.match(line):
        return "mysql", match.group(1).strip(), False
    if match := _MYSQL_CONT_RE.match(line):
        return "mysql", match.group(1).strip(), True
    for pattern in _SHELL_PROMPTS:
        if match := pattern.match(line):
            return "shell", match.group(1).strip(), False
    for pattern in _NETWORK_PROMPTS:
        if match := pattern.match(line):
            return "network", (match.group(2) or "").strip(), False
    for pattern in _CISCO_PROMPTS:
        if match := pattern.match(line):
            return "network", (match.group(2) or "").strip(), False
    return None


def _read_only_mysql(command: str) -> bool:
    statements = [part.strip() for part in command.split(";") if part.strip()]
    return bool(statements) and all(re.match(r"^(?:SELECT|SHOW)\b", part, re.I) for part in statements)


def _read_only_network(command: str) -> bool:
    if not re.match(r"^\s*(?:display|show)\b", command, re.I):
        return False
    return not _NETWORK_WRITE_RE.search(command)


def _meaningful_output(command: _Command) -> list[OutputLine]:
    return [
        line for line in command.output
        if not _EMPTY_SET_RE.match(line.text) and not _ROWS_STATUS_RE.match(line.text)
    ]


def _command_status(command: _Command, binding: SessionBinding) -> CheckStatus:
    if command.failed:
        return CheckStatus.FAILED
    meaningful = _meaningful_output(command)
    if meaningful:
        return CheckStatus.COLLECTED
    if command.kind == "mysql" and command.empty_set:
        return CheckStatus.EMPTY
    if command.closed and binding.empty == "success":
        return CheckStatus.EMPTY
    return CheckStatus.FAILED


def _match_bindings(command: _Command, checks: ChecksMap) -> list[tuple[CheckBinding, SessionBinding]]:
    matches: list[tuple[CheckBinding, SessionBinding]] = []
    for binding in checks.checks:
        for session in binding.session:
            if session.kind != command.kind:
                continue
            if re.search(session.pattern, command.text, re.I):
                matches.append((binding, session))
    return matches


def _safe_line_numbers(lines: list[int]) -> str:
    values = sorted(set(lines))
    if len(values) > 12:
        return ",".join(map(str, values[:12])) + "…"
    return ",".join(map(str, values))


def parse_session_text(
    text: str,
    filename: str,
    checks: ChecksMap,
    session_start: int = 0,
) -> SessionOutcome:
    outcome = SessionOutcome()
    records: list[_Command] = []
    current: _Command | None = None
    prompt_seen = False

    def flush() -> None:
        nonlocal current
        if current is not None:
            current.closed = True
            records.append(current)
            current = None

    for number, raw in enumerate(text.splitlines(), 1):
        original = raw.rstrip("\r")
        line = _without_timestamp(original)
        prompt = _prompt(line)
        if prompt:
            kind, command_text, continuation = prompt
            prompt_seen = True
            if continuation:
                if current is not None and current.kind == "mysql" and command_text:
                    current.text = f"{current.text} {command_text}".strip()
                continue
            if not command_text:
                flush()
                continue
            flush()
            current = _Command(
                kind=kind,
                text=command_text,
                line=number,
                snippet=original,
            )
            continue
        if current is None:
            continue
        if current.kind == "mysql" and _EMPTY_SET_RE.match(line):
            current.empty_set = True
        if _ERROR_RE.search(line):
            current.failed = True
        if line.strip():
            current.output.append(OutputLine(line=number, text=line.rstrip(), snippet=original))

    flush()
    if not prompt_seen:
        raise SessionParseError(
            f"{filename}：未识别到高置信 shell/MySQL/网络设备提示符"
        )

    sensitive_lines: list[int] = []
    ignored_lines: list[int] = []
    grouped: dict[str, dict] = {}
    shell_mapped = False
    for command in records:
        if _SENSITIVE_RE.search(command.text):
            sensitive_lines.append(command.line)
            continue
        if command.kind == "mysql" and not _read_only_mysql(command.text):
            ignored_lines.append(command.line)
            continue
        if command.kind == "network" and not _read_only_network(command.text):
            ignored_lines.append(command.line)
            continue
        matches = _match_bindings(command, checks)
        if not matches:
            ignored_lines.append(command.line)
            continue
        shell_mapped = shell_mapped or command.kind == "shell"
        for binding, session in matches:
            group = grouped.setdefault(binding.title, {"binding": binding, "commands": []})
            group["commands"].append((command, session))

    if not grouped:
        raise SessionParseError(f"{filename}：交互会话中没有任何命令命中 checks_map")

    family = "unknown"
    if shell_mapped:
        for command in records:
            if command.kind != "shell":
                continue
            detected = detect_os_family("\n".join(line.text for line in command.output))
            if detected:
                family = detected
                break
    session_no = session_start + 1
    for title, group in grouped.items():
        binding: CheckBinding = group["binding"]
        entries: list[tuple[_Command, SessionBinding]] = group["commands"]
        outputs: list[OutputLine] = []
        facts: list[DerivedFact] = []
        commands: list[str] = []
        anchors: list[EvidenceAnchor] = []
        statuses: list[CheckStatus] = []
        seen_output: set[tuple[int, str]] = set()
        for command, session in entries:
            status = _command_status(command, session)
            statuses.append(status)
            if command.text not in commands:
                commands.append(command.text)
            anchor = EvidenceAnchor(file=filename, line=command.line, snippet=command.snippet)
            if all((existing.line, existing.snippet) != (anchor.line, anchor.snippet) for existing in anchors):
                anchors.append(anchor)
            for line in command.output:
                identity = (line.line, line.text)
                if identity not in seen_output:
                    seen_output.add(identity)
                    outputs.append(line)
            for fact in normalize_session_command(
                binding.normalize,
                command.kind,
                command.text,
                command.output,
                status,
                filename,
                command.line,
                command.snippet,
            ):
                if fact.text not in {existing.text for existing in facts}:
                    facts.append(fact)

        outputs.sort(key=lambda line: line.line)
        if any(status is CheckStatus.COLLECTED for status in statuses):
            status = CheckStatus.COLLECTED
        elif all(status is CheckStatus.EMPTY for status in statuses):
            status = CheckStatus.EMPTY
        else:
            status = CheckStatus.FAILED
        outcome.blocks.append(
            CheckBlock(
                session=session_no,
                block_index=binding.block_index,
                section=binding.section,
                title=title,
                os_family=family,
                status=status,
                commands=commands,
                command_anchors=anchors,
                output=outputs,
                facts=facts,
                source=filename,
            )
        )

    outcome.blocks.sort(key=lambda block: (binding_order(checks, block.title), block.title))
    if sensitive_lines:
        outcome.warnings.append(
            f"{filename}：忽略含凭据参数的输入 {len(sensitive_lines)} 条（行号：{_safe_line_numbers(sensitive_lines)}）"
        )
    if ignored_lines:
        outcome.warnings.append(
            f"{filename}：忽略未映射或非只读命令 {len(ignored_lines)} 条（行号：{_safe_line_numbers(ignored_lines)}）"
        )
    outcome.warnings.append(f"{filename}：按交互会话解析 {len(outcome.blocks)} 个检查块")
    return outcome


def binding_order(checks: ChecksMap, title: str) -> int:
    for index, binding in enumerate(checks.checks):
        if binding.title == title:
            return index
    return len(checks.checks)
