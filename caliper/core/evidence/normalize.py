"""把原始检查输出规范化为带原始锚点的派生事实。

本模块不改写原始 output；事实仅用于规则求值，不能替代现场原文。
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from core.model.entities import CheckBlock, CheckStatus, DerivedFact, EvidenceAnchor, OutputLine

if TYPE_CHECKING:
    from core.checks.mapping import ChecksMap


_NORMALIZERS = {
    "os",
    "duplicate_uid",
    "accounts",
    "empty_password",
    "password_complexity",
    "faillock",
    "tmout",
    "key_file_permissions",
    "auditd",
    "log_service",
    "log_retention",
    "log_archives",
    "log_forwarding",
    "security_agent",
    "selinux",
    "mysql_status",
    "mysql_accounts",
    "mysql_privileges",
    "mysql_connection_control",
    "mysql_password_policy",
    "mysql_audit",
    "mysql_remote_access",
    "mysql_backup",
    "h3c_config",
}

_MYSQL_VARIABLES = {
    "general_log",
    "bind_address",
    "skip_networking",
    "log_bin",
    "expire_logs_days",
    "max_connect_errors",
    "version",
    "version_comment",
    "validate_password_policy",
    "validate_password_length",
}
_MYSQL_PLUGINS = {"validate_password", "connection_control", "audit_log", "server_audit"}
_AGENT_RE = re.compile(r"aegis|yunjing|sangfor|falcon|clamd|osquery|wazuh|suricata|snort|edr|antivirus", re.I)
_ERROR_RE = re.compile(r"command not found|permission denied|operation not permitted|access denied|no such file or directory|cannot (?:access|stat|open)\b|^\s*ERROR\s+\d+", re.I)


def normalize_names() -> set[str]:
    return set(_NORMALIZERS)


def detect_os_family(text: str) -> str | None:
    if re.search(r"kylin|centos|red\s*hat|\brhel\b|rocky\s+linux|almalinux", text, re.I):
        return "rhel"
    if re.search(r"ubuntu|debian", text, re.I):
        return "debian"
    return None


def _anchors(block: CheckBlock, lines: list[OutputLine] | None = None) -> list[EvidenceAnchor]:
    selected = lines if lines else block.output[:1]
    anchors = [
        EvidenceAnchor(file=block.source, line=line.line, snippet=(line.snippet or line.text).strip())
        for line in (selected or [])[:3]
    ]
    if not anchors:
        anchors = list(block.command_anchors[:1])
    return anchors


def _fact(block: CheckBlock, text: str, lines: list[OutputLine] | None = None) -> DerivedFact | None:
    anchors = _anchors(block, lines)
    return DerivedFact(text=text, anchors=anchors) if anchors else None


def _add(facts: list[DerivedFact], fact: DerivedFact | None) -> None:
    if fact is not None and fact.text not in {entry.text for entry in facts}:
        facts.append(fact)


def _matching(block: CheckBlock, pattern: str) -> list[OutputLine]:
    regex = re.compile(pattern, re.I)
    return [line for line in block.output if regex.search(line.text)]


def _has_failed_output(block: CheckBlock) -> bool:
    return any(_ERROR_RE.search(line.text) for line in block.output)


def _normalize_os(block: CheckBlock) -> list[DerivedFact]:
    family = detect_os_family(block.text)
    if family is None and block.os_family in {"debian", "rhel"}:
        family = block.os_family
    return [fact] if family and (fact := _fact(block, f"fact:os.family={family}")) else []


def _normalize_duplicate_uid(block: CheckBlock) -> list[DerivedFact]:
    facts: list[DerivedFact] = []
    command = "\n".join(block.commands)
    no_duplicate = _matching(block, r"\bno duplicate uid\b")
    duplicate = [
        line for line in _matching(block, r"\bduplicate uid\b")
        if not re.search(r"\bno duplicate uid\b", line.text, re.I)
    ]
    if no_duplicate:
        _add(facts, _fact(block, "fact:duplicate_uid.none=true", no_duplicate))
    elif duplicate:
        _add(facts, _fact(block, "fact:duplicate_uid.none=false", duplicate))
    elif "uniq -d" in command:
        numeric = [line for line in block.output if re.fullmatch(r"\s*\d+\s*", line.text)]
        if block.status is CheckStatus.EMPTY:
            _add(facts, _fact(block, "fact:duplicate_uid.none=true"))
        elif numeric:
            _add(facts, _fact(block, "fact:duplicate_uid.none=false", numeric))
        elif block.output:
            _add(facts, _fact(block, "fact:duplicate_uid.none=true"))

    uid_lines = _matching(block, r"\bUID=0\s*:")
    names: list[str] = []
    anchors: list[OutputLine] = []
    for line in uid_lines:
        value = line.text.split(":", 1)[1].strip()
        names.extend(part.strip() for part in value.split(",") if part.strip())
        anchors.append(line)
    if not uid_lines and re.search(r"\$3\s*==\s*0", command):
        for line in block.output:
            value = line.text.strip()
            if value and not value.isdigit() and not value.lower().startswith("no "):
                names.append(value.split()[0])
                anchors.append(line)
        if block.status is CheckStatus.EMPTY:
            _add(facts, _fact(block, "fact:uid0.only_root=false"))
    if names:
        only_root = set(names) == {"root"}
        _add(facts, _fact(block, f"fact:uid0.only_root={str(only_root).lower()}", anchors))
    return facts


def _normalize_accounts(block: CheckBlock) -> list[DerivedFact]:
    facts: list[DerivedFact] = []
    expiry = _matching(block, r"\bexpire=")
    if expiry:
        values = [re.search(r"\bexpire=([^\s]*)", line.text).group(1) for line in expiry]
        if all(value in {"", "0"} for value in values):
            _add(facts, _fact(block, "fact:account.expired.none=true", expiry))
    never = _matching(block, r"Account expires\s*:\s*never")
    account_expires = _matching(block, r"Account expires\s*:")
    if account_expires and len(never) == len(account_expires):
        _add(facts, _fact(block, "fact:account.expired.none=true", account_expires))
    explicitly_expired = [
        line for line in _matching(block, r"\bexpired\b")
        if not re.search(r"\bno(?:t)?\s+expired\b", line.text, re.I)
    ]
    if explicitly_expired:
        facts = [fact for fact in facts if fact.text != "fact:account.expired.none=true"]
        _add(facts, _fact(block, "fact:account.expired.none=false", explicitly_expired))
    return facts


def _normalize_empty_password(block: CheckBlock) -> list[DerivedFact]:
    facts: list[DerivedFact] = []
    shadow_rows = [
        line
        for line in block.output
        if len(line.text.strip().split(":")) >= 7 and not line.text.lstrip().startswith("#")
    ]
    if shadow_rows:
        empty = [line for line in shadow_rows if line.text.strip().split(":")[1] == ""]
        _add(facts, _fact(block, f"fact:empty_password.none={str(not empty).lower()}", empty or shadow_rows))
        return facts
    none = _matching(block, r"no empty-password account|empty-password:\s*none")
    present = [
        line for line in _matching(block, r"empty-password")
        if not re.search(r"no empty-password|empty-password:\s*none", line.text, re.I)
    ]
    if none:
        _add(facts, _fact(block, "fact:empty_password.none=true", none))
    elif present:
        _add(facts, _fact(block, "fact:empty_password.none=false", present))
    elif '$2==""' in "".join(block.commands).replace(" ", "") and block.status in {
        CheckStatus.COLLECTED,
        CheckStatus.EMPTY,
    }:
        _add(facts, _fact(block, "fact:empty_password.none=true"))
    return facts


def _normalize_password_complexity(block: CheckBlock) -> list[DerivedFact]:
    module = [
        line for line in _matching(block, r"pam_(?:pwquality|cracklib)\.so")
        if not re.search(r"absent|not found|^\s*#", line.text, re.I)
    ]
    params = [
        line for line in _matching(block, r"\b(?:minlen|minclass|[dlou]credit|retry)\s*=")
        if not line.text.lstrip().startswith("#")
    ]
    enabled = bool(module) or bool(params)
    evidence = [*module, *params] or block.output[:1]
    fact = _fact(block, f"fact:pam.password_complexity.enabled={str(enabled).lower()}", evidence)
    return [fact] if fact else []


def _normalize_faillock(block: CheckBlock) -> list[DerivedFact]:
    facts: list[DerivedFact] = []
    module = [
        line for line in _matching(block, r"pam_(?:faillock|tally\d*)\.so")
        if not re.search(r"absent|not found|^\s*#", line.text, re.I)
    ]
    deny = _matching(block, r"\bdeny\s*=\s*[1-9]\d*")
    unlock = _matching(block, r"\bunlock_time\s*=\s*[1-9]\d*")
    if module or block.output or block.status is CheckStatus.EMPTY:
        _add(facts, _fact(block, f"fact:faillock.module={str(bool(module)).lower()}", module))
    if deny or unlock or block.status is CheckStatus.EMPTY:
        _add(facts, _fact(block, f"fact:faillock.policy={str(bool(deny and unlock)).lower()}", [*deny, *unlock]))
    return facts


def _normalize_tmout(block: CheckBlock) -> list[DerivedFact]:
    lines = _matching(block, r"\bTMOUT\s*=")
    if not lines and re.search(r"\|\s*grep\b", "\n".join(block.commands)) and not re.search(
        r"\bTMOUT\b", "\n".join(block.commands)
    ):
        return []
    valid = [line for line in lines if (match := re.search(r"\bTMOUT\s*=\s*[\"']?(\d+)", line.text)) and int(match.group(1)) > 0]
    if not lines and block.status is not CheckStatus.EMPTY:
        return []
    fact = _fact(block, f"fact:session.tmout.valid={str(bool(valid)).lower()}", valid or lines)
    return [fact] if fact else []


def _ls_mode(permissions: str) -> int | None:
    if len(permissions) < 10:
        return None
    value = 0
    for index, char in enumerate(permissions[1:10]):
        bit = 1 << (8 - index)
        if char in "rwxstST":
            if char in "ST" and index % 3 != 2:
                continue
            if char in "st" or index % 3 != 2:
                value |= bit
    return value


def _permission_rows(block: CheckBlock) -> list[tuple[str, int, str, str, OutputLine]]:
    rows = []
    stat_re = re.compile(r"\b(?P<mode>\d{3,4})\s+(?P<owner>[^\s:]+):(?P<group>[^\s]+)\s+(?P<path>/\S+)")
    ls_re = re.compile(r"^(?P<perms>[bcdlps-][rwxStTs-]{9})\+?\s+\d+\s+(?P<owner>\S+)\s+(?P<group>\S+)\s+.*\s(?P<path>/\S+)\s*$")
    for line in block.output:
        text = line.text.strip()
        if match := stat_re.search(text):
            rows.append((match.group("path"), int(match.group("mode")[-3:], 8), match.group("owner"), match.group("group"), line))
        elif match := ls_re.match(text):
            mode = _ls_mode(match.group("perms"))
            if mode is not None:
                rows.append((match.group("path"), mode, match.group("owner"), match.group("group"), line))
    return rows


def _normalize_key_file_permissions(block: CheckBlock) -> list[DerivedFact]:
    facts: list[DerivedFact] = []
    rows = _permission_rows(block)
    for path, mode, owner, group, line in rows:
        if path == "/etc/passwd":
            secure = owner == "root" and not (mode & 0o022)
            _add(facts, _fact(block, f"fact:file_permissions.passwd.secure={str(secure).lower()}", [line]))
        elif path == "/etc/shadow":
            secure = owner == "root" and group in {"root", "shadow"} and mode in {0, 0o400, 0o600, 0o640}
            _add(facts, _fact(block, f"fact:file_permissions.shadow.secure={str(secure).lower()}", [line]))
    return facts


def _active_fact(block: CheckBlock, name: str) -> list[DerivedFact]:
    active = _matching(block, r"^\s*active\s*$|Active:\s+active\s+\(running\)|\bservice active\b")
    inactive = _matching(block, r"^\s*(?:inactive|failed)\s*$|Active:\s+(?:inactive|failed)|\bservice inactive\b")
    if not active and not inactive and block.status is not CheckStatus.EMPTY:
        return []
    fact = _fact(block, f"fact:{name}.active={str(bool(active)).lower()}", active or inactive)
    return [fact] if fact else []


def _normalize_auditd(block: CheckBlock) -> list[DerivedFact]:
    facts = _active_fact(block, "auditd")
    loaded = _matching(block, r"^\s*-[aAwWdDS]\b")
    no_rules = _matching(block, r"^\s*No rules\s*$|\bno rule loaded\b")
    if loaded or no_rules or ("auditctl" in "\n".join(block.commands) and block.status is CheckStatus.EMPTY):
        _add(facts, _fact(block, f"fact:auditd.rules_loaded={str(bool(loaded)).lower()}", loaded or no_rules))
    return facts


def _duration_seconds(value: str, unit: str | None) -> int | None:
    try:
        number = int(value)
    except ValueError:
        return None
    factors = {None: 1, "s": 1, "sec": 1, "second": 1, "seconds": 1, "day": 86400, "days": 86400, "week": 604800, "weeks": 604800, "month": 2592000, "months": 2592000, "year": 31536000, "years": 31536000}
    factor = factors.get((unit or "").lower() or None)
    return number * factor if factor is not None else None


def _normalize_log_retention(block: CheckBlock) -> list[DerivedFact]:
    period: str | None = None
    rotates: list[int] = []
    evidence: list[OutputLine] = []
    assessments: list[bool] = []
    for line in block.output:
        if line.text.lstrip().startswith("#"):
            continue
        text = line.text.split(":", 1)[-1] if line.text.startswith("/") and ":" in line.text else line.text
        for candidate in ("daily", "weekly", "monthly"):
            if re.search(rf"(?:^|\s){candidate}(?:\s|$)", text.strip()):
                period = candidate
                evidence.append(line)
        if match := re.search(r"\brotate\s+(\d+)", text):
            rotates.append(int(match.group(1)))
            evidence.append(line)
        if match := re.search(r"\bmaxage\s+(\d+)", text):
            evidence.append(line)
            assessments.append(int(match.group(1)) >= 180)
        if match := re.search(r"\bMaxRetentionSec\s*=\s*(\d+)\s*([A-Za-z]+)?", text, re.I):
            evidence.append(line)
            seconds = _duration_seconds(match.group(1), match.group(2))
            if seconds is not None:
                assessments.append(seconds >= 180 * 86400)
    if period and rotates:
        required = {"daily": 180, "weekly": 26, "monthly": 6}[period]
        assessments.append(all(value >= required for value in rotates))
    if not assessments:
        return []
    fact = _fact(block, f"fact:log.retention.six_months={str(all(assessments)).lower()}", evidence)
    return [fact] if fact else []


def _normalize_log_archives(block: CheckBlock) -> list[DerivedFact]:
    archives = _matching(block, r"(?:^|\s)\S+\.(?:gz|zst|xz)(?:\s|$)|\bcompressed\b")
    none = _matching(block, r"\bno archives\b|\bnone\b")
    if not archives and not none and block.status is not CheckStatus.EMPTY:
        return []
    fact = _fact(block, f"fact:log.archives.present={str(bool(archives)).lower()}", archives or none)
    return [fact] if fact else []


def _normalize_log_forwarding(block: CheckBlock) -> list[DerivedFact]:
    configured = [line for line in _matching(block, r"\*\.\*.*@@?") if not line.text.lstrip().startswith("#")]
    none = _matching(block, r"^\s*none\s*$|\bno forwarding\b")
    if not configured and not none and block.status is not CheckStatus.EMPTY:
        return []
    fact = _fact(block, f"fact:log.forwarding.enabled={str(bool(configured)).lower()}", configured or none)
    return [fact] if fact else []


def _normalize_security_agent(block: CheckBlock) -> list[DerivedFact]:
    facts: list[DerivedFact] = []
    command = "\n".join(block.commands)
    agent_lines = [line for line in block.output if _AGENT_RE.search(line.text) and not re.search(r"no security|not found", line.text, re.I)]
    if re.search(r"\bpgrep\b|\bps\s+-(?:efH?|aux)\b", command) or _matching(block, r"no security agent process"):
        present = [line for line in agent_lines if not re.search(r"\bii\s+", line.text)]
        absent = _matching(block, r"no security agent process")
        if present or absent or block.status is CheckStatus.EMPTY:
            _add(facts, _fact(block, f"fact:security_agent.process.present={str(bool(present)).lower()}", present or absent))
    if re.search(r"dpkg|rpm", command) or _matching(block, r"no security package"):
        absent = _matching(block, r"no security package")
        if agent_lines or absent or block.status is CheckStatus.EMPTY:
            _add(facts, _fact(block, f"fact:security_agent.package.present={str(bool(agent_lines)).lower()}", agent_lines or absent))
    return facts


def _normalize_selinux(block: CheckBlock) -> list[DerivedFact]:
    labels = _matching(block, r"\b(?:system|user|staff|root|unconfined)_[ur]:\w+_r:\w+_t(?::\S+)?\b")
    if not labels:
        return []
    command = "\n".join(block.commands)
    facts: list[DerivedFact] = []
    if re.search(r"\bps\s+-[a-z]*Z[a-z]*\b", command):
        _add(facts, _fact(block, "fact:security_labels.subject=true", labels))
    if re.search(r"\bls\s+-[a-z]*Z[a-z]*\b", command):
        _add(facts, _fact(block, "fact:security_labels.object=true", labels))
    existing = {fact.text for fact in [*block.facts, *facts]}
    if {"fact:security_labels.subject=true", "fact:security_labels.object=true"} <= existing:
        _add(facts, _fact(block, "fact:security_labels.configured=true", labels))
    return facts


def _mysql_rows(block: CheckBlock) -> list[tuple[list[str], OutputLine]]:
    rows: list[tuple[list[str], OutputLine]] = []
    for line in block.output:
        text = line.text.strip()
        if not text or text.startswith("+") or re.match(r"^(?:Empty set|Query OK|ERROR|\d+ rows? in set)", text, re.I):
            continue
        cells = [cell.strip() for cell in text.strip("|").split("|")] if text.startswith("|") else text.split("\t")
        if not cells:
            continue
        lowered = {cell.strip("`").lower() for cell in cells}
        if lowered & {"variable_name", "plugin_name", "user", "host", "super_priv", "version()"}:
            continue
        rows.append((cells, line))
    return rows


def _canonical_plugin(value: str) -> str:
    name = value.strip().strip("`").lower()
    for candidate in _MYSQL_PLUGINS:
        if candidate in name:
            return candidate
    return name


def _mysql_common_facts(block: CheckBlock) -> tuple[list[DerivedFact], dict[str, str], dict[str, str]]:
    facts: list[DerivedFact] = []
    variables: dict[str, str] = {}
    plugins: dict[str, str] = {}
    command = "\n".join(block.commands)
    for cells, line in _mysql_rows(block):
        if len(cells) == 1:
            value = cells[0].strip()
            if _query_has(command, "SELECT VERSION()") and re.fullmatch(r"\d+(?:\.\d+)+[0-9A-Za-z._+-]*", value):
                variables["version"] = value
                _add(facts, _fact(block, f"fact:mysql.variable.version={value}", [line]))
            continue
        name = cells[0].strip().strip("`").lower()
        value = cells[1].strip()
        if name in _MYSQL_VARIABLES:
            variables[name] = value
            _add(facts, _fact(block, f"fact:mysql.variable.{name}={value}", [line]))
        plugin = _canonical_plugin(cells[0])
        if plugin in _MYSQL_PLUGINS and value.upper() in {"ACTIVE", "INACTIVE", "DISABLED", "NOT INSTALLED", "DELETED"}:
            plugins[plugin] = value.upper()
            _add(facts, _fact(block, f"fact:mysql.plugin.{plugin}.status={value.upper()}", [line]))
    return facts, variables, plugins


def _query_has(command: str, expression: str) -> bool:
    compact = re.sub(r"\s+", "", command).lower()
    return re.sub(r"\s+", "", expression).lower() in compact


def _mysql_account_facts(block: CheckBlock) -> list[DerivedFact]:
    facts, _, _ = _mysql_common_facts(block)
    command = "\n".join(block.commands)
    legacy_anonymous = _matching(block, r"no anonymous|anonymous:\s*none|anonymous account\s*:\s*none")
    legacy_anonymous_present = [
        line for line in _matching(block, r"anonymous account\s*:")
        if not re.search(r"\bnone\b", line.text, re.I)
    ]
    legacy_empty = _matching(block, r"no empty-password|empty-password\s*:\s*none")
    legacy_empty_present = [
        line for line in _matching(block, r"empty-password\s*:")
        if not re.search(r"\bnone\b", line.text, re.I)
    ]
    if legacy_anonymous:
        _add(facts, _fact(block, "fact:mysql.account.anonymous.none=true", legacy_anonymous))
    elif legacy_anonymous_present:
        _add(facts, _fact(block, "fact:mysql.account.anonymous.none=false", legacy_anonymous_present))
    if legacy_empty:
        _add(facts, _fact(block, "fact:mysql.account.empty_password.none=true", legacy_empty))
    elif legacy_empty_present:
        _add(facts, _fact(block, "fact:mysql.account.empty_password.none=false", legacy_empty_present))
    if "mysql.user" not in command.lower():
        return facts
    anonymous_query = _query_has(command, "User=''") or _query_has(command, "user = ''")
    empty_query = _query_has(command, "authentication_string=''") or _query_has(command, "authentication_string = ''")
    if block.status in {CheckStatus.COLLECTED, CheckStatus.EMPTY} and not _has_failed_output(block):
        result = "false" if _mysql_rows(block) else "true"
        existing = {fact.text for fact in [*block.facts, *facts]}
        if anonymous_query and not any(text.startswith("fact:mysql.account.anonymous.none=") for text in existing):
            _add(facts, _fact(block, f"fact:mysql.account.anonymous.none={result}"))
        if empty_query and not any(text.startswith("fact:mysql.account.empty_password.none=") for text in existing):
            _add(facts, _fact(block, f"fact:mysql.account.empty_password.none={result}"))
    return facts


def _selected_user_columns(commands: list[str]) -> list[str]:
    for command in commands:
        match = re.search(r"\bselect\s+(.+?)\s+from\s+mysql\.user\b", command, re.I | re.S)
        if match:
            return [part.strip().strip("`").lower() for part in match.group(1).split(",")]
    return []


def _mysql_privilege_facts(block: CheckBlock) -> list[DerivedFact]:
    columns = _selected_user_columns(block.commands)
    required = {"user", "host", "super_priv", "grant_priv", "file_priv", "process_priv"}
    if not required <= set(columns):
        return []
    rows = [cells for cells, _ in _mysql_rows(block) if len(cells) == len(columns)]
    if block.status is not CheckStatus.EMPTY and not rows:
        return []
    host_index = columns.index("host")
    super_index = columns.index("super_priv")
    offending = [cells for cells in rows if cells[host_index] == "%" and cells[super_index].upper() == "Y"]
    facts: list[DerivedFact] = []
    _add(facts, _fact(block, "fact:mysql.privileges.complete=true"))
    _add(facts, _fact(block, f"fact:mysql.privileges.no_wildcard_super={str(not offending).lower()}"))
    return facts


def _mysql_plugin_facts(block: CheckBlock, plugin: str) -> list[DerivedFact]:
    facts, _, _ = _mysql_common_facts(block)
    if block.status is CheckStatus.EMPTY and plugin in "\n".join(block.commands).lower():
        _add(facts, _fact(block, f"fact:mysql.plugin.{plugin}.none=true"))
    return facts


def _mysql_audit_facts(block: CheckBlock) -> list[DerivedFact]:
    facts, variables, plugins = _mysql_common_facts(block)
    command = "\n".join(block.commands)
    if (
        block.status is CheckStatus.EMPTY
        and re.search(r"\bplugin", command, re.I)
        and re.search(r"\blike\s+['\"]%audit%['\"]", command, re.I)
    ):
        for plugin in ("audit_log", "server_audit"):
            _add(facts, _fact(block, f"fact:mysql.plugin.{plugin}.none=true"))
    existing = {fact.text for fact in [*block.facts, *facts]}
    audit_absent = bool({
        "fact:mysql.plugin.audit_log.none=true",
        "fact:mysql.plugin.server_audit.none=true",
    } & existing)
    active = variables.get("general_log", "").upper() == "ON" or any(
        plugins.get(plugin) == "ACTIVE" for plugin in ("audit_log", "server_audit")
    )
    audit_observed = audit_absent or any(plugin in plugins for plugin in ("audit_log", "server_audit"))
    if active:
        _add(facts, _fact(block, "fact:mysql.audit.enabled=true"))
    elif variables.get("general_log", "").upper() == "OFF" and audit_observed:
        _add(facts, _fact(block, "fact:mysql.audit.enabled=false"))
    return facts


def _mysql_remote_facts(block: CheckBlock) -> list[DerivedFact]:
    facts, variables, _ = _mysql_common_facts(block)
    bind = variables.get("bind_address", "").strip()
    skip = variables.get("skip_networking", "").upper()
    if skip == "ON" or bind.lower() in {"localhost", "127.0.0.1"}:
        _add(facts, _fact(block, "fact:mysql.remote_access.restricted=true"))
    elif bind and skip == "OFF":
        _add(facts, _fact(block, "fact:mysql.remote_access.restricted=false"))
    return facts


def _normalize_mysql_backup(block: CheckBlock) -> list[DerivedFact]:
    facts, _, _ = _mysql_common_facts(block)
    if facts:
        _add(facts, _fact(block, "fact:mysql.backup.context_only=true"))
    return facts


_H3C_DEFAULT_ACCOUNTS = {
    "admin",
    "administrator",
    "h3c",
    "root",
    "test",
    "guest",
    "public",
}
_H3C_ANONYMOUS_ACCOUNTS = {"anonymous", "guest", "public"}


def _h3c_value(block: CheckBlock, pattern: str) -> int | None:
    match = re.search(pattern, block.text, re.I)
    if not match:
        return None
    try:
        return int(match.group(1))
    except (IndexError, TypeError, ValueError):
        return None


def _normalize_h3c_config(block: CheckBlock) -> list[DerivedFact]:
    """把 H3C 运行配置与状态回显归一为厂商事实；规则只读事实，不直接拼命令。"""
    facts: list[DerivedFact] = []

    def add(pattern: str, text: str) -> None:
        lines = _matching(block, pattern)
        if lines:
            _add(facts, _fact(block, text, lines))

    names: list[str] = []
    users: dict[str, dict[str, object]] = {}
    current: str | None = None
    password_seen = False
    for line in block.output:
        raw = line.text
        match = re.search(r"^\s*local-user\s+(\S+)", raw, re.I)
        if match:
            current = match.group(1)
            names.append(current)
            users.setdefault(current, {"password": "", "disabled": False, "roles": []})
            continue
        match = re.search(r"^\s*Username:\s*(\S+)", raw, re.I)
        if match:
            current = match.group(1)
            names.append(current)
            users.setdefault(current, {"password": "", "disabled": False, "roles": []})
            continue
        if current is None:
            continue
        user = users[current]
        if re.search(r"^\s+password\s+", raw, re.I):
            user["password"] = raw.strip()
            password_seen = True
        elif re.search(r"^\s+Password:\s*", raw, re.I):
            user["password"] = raw.strip()
            password_seen = True
        if re.search(r"service-type\s+none\b", raw, re.I):
            user["disabled"] = True
        role = re.search(r"authorization-attribute\s+user-role\s+(\S+)", raw, re.I)
        if role:
            user["roles"].append(role.group(1))
        level = re.search(r"authorization-attribute\s+level\s+(\d+)", raw, re.I)
        if level:
            user["roles"].append(f"level-{level.group(1)}")

    if names:
        user_lines = _matching(block, r"^\s*(?:local-user|Username:)\s")
        password_lines = _matching(block, r"^\s*(?:password|Password:)\s")
        role_lines = _matching(
            block, r"user-role|authorization-attribute\s+level"
        )
        _add(
            facts,
            _fact(
                block,
                f"fact:h3c.users.unique={str(len(names) == len(set(names))).lower()}",
                user_lines,
            ),
        )
        if password_seen:
            empty = any(
                not str(user["password"]).strip()
                or re.search(r"not configured|none|^\s*Password:\s*$", str(user["password"]), re.I)
                for user in users.values()
            )
            _add(
                facts,
                _fact(
                    block,
                    f"fact:h3c.users.empty_password={'present' if empty else 'none'}",
                    password_lines,
                ),
            )
        default_present = any(
            name.lower() in _H3C_DEFAULT_ACCOUNTS
            and not bool(users[name]["disabled"])
            for name in users
        )
        _add(
            facts,
            _fact(
                block,
                f"fact:h3c.users.default_account={'present' if default_present else 'none'}",
                user_lines,
            ),
        )
        anonymous_present = any(
            name.lower() in _H3C_ANONYMOUS_ACCOUNTS for name in users
        )
        _add(
            facts,
            _fact(
                block,
                f"fact:h3c.users.anonymous={'present' if anonymous_present else 'none'}",
                user_lines,
            ),
        )
        roles = {role for user in users.values() for role in user["roles"]}
        if roles:
            _add(
                facts,
                _fact(
                    block,
                    "fact:h3c.roles.privilege_distinct="
                    f"{str(len(roles) >= 2).lower()}",
                    role_lines,
                ),
            )

    control = None
    if _matching(block, r"^\s*password-control\s+enable\b"):
        control = True
    if _matching(block, r"^\s*undo\s+password-control\s+enable\b"):
        control = False
    status = re.search(
        r"password\s+control\s*:\s*(enabled|disabled)", block.text, re.I
    )
    if status:
        control = status.group(1).lower() == "enabled"
    if control is not None:
        add(
            r"password[\s-]*control",
            f"fact:h3c.password_control.enabled={str(control).lower()}",
        )

    aging = (
        _h3c_value(block, r"password-control\s+aging\s+(\d+)")
        or _h3c_value(block, r"password\s+aging[^\n]*?(\d+)\s*days?")
        or _h3c_value(block, r"口令老化[^\n]*?(\d+)\s*天")
    )
    if aging is not None:
        add(r"aging", f"fact:h3c.password_control.aging_days={aging}")

    length = (
        _h3c_value(block, r"password-control\s+length\s+(\d+)")
        or _h3c_value(block, r"password\s+length[^\n]*?(\d+)\s*characters?")
        or _h3c_value(block, r"口令长度[^\n]*?(\d+)")
    )
    if length is not None:
        add(r"length", f"fact:h3c.password_control.length={length}")

    composition = (
        _h3c_value(block, r"password-control\s+composition\s+type-number\s+(\d+)")
        or _h3c_value(block, r"password\s+composition[^\n]*?(\d+)\s*types?")
        or _h3c_value(block, r"口令组成[^\n]*?(\d+)\s*种")
    )
    if composition is not None:
        add(
            r"composition",
            f"fact:h3c.password_control.composition_types={composition}",
        )

    login_attempt = (
        _h3c_value(block, r"password-control\s+login-attempt\s+(\d+)")
        or _h3c_value(block, r"login\s+attempt\s+limit\s*:\s*(\d+)")
        or _h3c_value(block, r"登录失败次数[^\n]*?(\d+)")
    )
    if login_attempt is not None:
        add(
            r"login.attempt|login-attempt",
            f"fact:h3c.password_control.login_attempt={login_attempt}",
        )

    lock_seconds = _h3c_value(block, r"lock-time\s+(\d+)") or _h3c_value(
        block, r"lock\s+time\s*:\s*(\d+)\s*seconds?"
    )
    if lock_seconds is not None:
        add(
            r"lock-time|lock\s+time",
            f"fact:h3c.password_control.lock_minutes={max(1, round(lock_seconds / 60))}",
        )
    lock_minutes = _h3c_value(block, r"锁定时间[^\n]*?(\d+)\s*分钟")
    if lock_minutes is not None:
        add(
            r"锁定时间",
            f"fact:h3c.password_control.lock_minutes={lock_minutes}",
        )

    idle = (
        _h3c_value(block, r"idle-timeout\s+(\d+)")
        or _h3c_value(block, r"idle\s+timeout\s*:\s*(\d+)\s*minutes?")
        or _h3c_value(block, r"空闲超时[^\n]*?(\d+)\s*分钟")
    )
    if idle is not None:
        add(r"idle-timeout|idle\s+timeout", f"fact:h3c.timeout.idle_minutes={idle}")

    remote: dict[str, bool] = {}
    for key, pattern in {
        "ssh": r"^\s*ssh\s+server\s+(enable|disable)\b",
        "telnet": r"^\s*telnet\s+server\s+(enable|disable)\b",
        "https": r"^\s*ip\s+https\s+(enable|disable)\b",
        "http": r"^\s*ip\s+http\s+(enable|disable)\b",
    }.items():
        match = re.search(pattern, block.text, re.I | re.M)
        if match:
            remote[key] = match.group(1).lower() == "enable"
    for key, label in {
        "ssh": "SSH",
        "telnet": "Telnet",
        "https": "HTTPS",
        "http": "HTTP",
    }.items():
        match = re.search(
            rf"{label}\s+server\s*:\s*(enable|disable)", block.text, re.I
        )
        if match:
            remote[key] = match.group(1).lower() == "enable"
    for key, value in remote.items():
        add(
            rf"{key}",
            f"fact:h3c.remote.{key}_enabled={str(value).lower()}",
        )
    if remote:
        any_enabled = any(remote.values())
        add(
            r"server|https|http",
            f"fact:h3c.remote.any={str(any_enabled).lower()}",
        )
        complete = {"ssh", "telnet", "https", "http"} <= set(remote)
        encrypted = (
            complete
            and (remote["ssh"] or remote["https"])
            and not (remote["telnet"] or remote["http"])
        )
        add(
            r"server|https|http",
            f"fact:h3c.remote.encrypted={str(encrypted).lower()}",
        )

    if _matching(block, r"^\s*info-center\s+enable\b"):
        add(r"info-center", "fact:h3c.audit.info_center=true")
    if _matching(block, r"^\s*undo\s+info-center\s+enable\b"):
        add(r"undo\s+info-center", "fact:h3c.audit.info_center=false")
    center_status = re.search(
        r"information\s+center\s*:\s*(enabled|disabled)", block.text, re.I
    )
    if center_status:
        add(
            r"information\s+center",
            f"fact:h3c.audit.info_center={str(center_status.group(1).lower() == 'enabled').lower()}",
        )
    if _matching(block, r"logging\s+buffer[^\n]*enabled|日志缓冲区[^\n]*启用"):
        add(
            r"logging\s+buffer|日志缓冲区",
            "fact:h3c.audit.logbuffer=true",
        )
    if _matching(block, r"logging\s+buffer[^\n]*disabled|日志缓冲区[^\n]*关闭"):
        add(
            r"logging\s+buffer[^\n]*disabled|日志缓冲区[^\n]*关闭",
            "fact:h3c.audit.logbuffer=false",
        )
    if _matching(block, r"^\s*info-center\s+loghost\s+\S+|log\s+host\s*:\s*\S+"):
        add(
            r"loghost|log\s+host",
            "fact:h3c.audit.loghost=true",
        )
    elif "fact:h3c.audit.info_center=true" in {fact.text for fact in facts}:
        add(r"information\s+center|info-center", "fact:h3c.audit.loghost=false")

    acl_lines = _matching(block, r"^\s*acl\s+(?:number|basic|advanced)\s+\d+")
    inbound = _matching(block, r"^\s*acl\s+\d+\s+inbound\b")
    if acl_lines or inbound:
        add(
            r"^\s*acl\s+",
            f"fact:h3c.acl.vty_restricted={str(bool(inbound)).lower()}",
        )

    if _matching(block, r"^\s*password\s+(?:irreversible-cipher|cipher|hash)\b"):
        add(r"password\s+(?:irreversible-cipher|cipher|hash)", "fact:h3c.secret_storage.cipher=true")
    if _matching(block, r"^\s*password\s+simple\b"):
        add(r"password\s+simple", "fact:h3c.secret_storage.cipher=false")

    return facts


def _dispatch(normalize: str, block: CheckBlock) -> list[DerivedFact]:
    if not normalize or block.status in {CheckStatus.FAILED, CheckStatus.SKIPPED}:
        return []
    if normalize == "os":
        return _normalize_os(block)
    if normalize == "duplicate_uid":
        return _normalize_duplicate_uid(block)
    if normalize == "accounts":
        return _normalize_accounts(block)
    if normalize == "empty_password":
        return _normalize_empty_password(block)
    if normalize == "password_complexity":
        return _normalize_password_complexity(block)
    if normalize == "faillock":
        return _normalize_faillock(block)
    if normalize == "tmout":
        return _normalize_tmout(block)
    if normalize == "key_file_permissions":
        return _normalize_key_file_permissions(block)
    if normalize == "auditd":
        return _normalize_auditd(block)
    if normalize == "log_service":
        return _active_fact(block, "log_service")
    if normalize == "log_retention":
        return _normalize_log_retention(block)
    if normalize == "log_archives":
        return _normalize_log_archives(block)
    if normalize == "log_forwarding":
        return _normalize_log_forwarding(block)
    if normalize == "security_agent":
        return _normalize_security_agent(block)
    if normalize == "selinux":
        return _normalize_selinux(block)
    if normalize == "mysql_status":
        return _mysql_common_facts(block)[0]
    if normalize == "mysql_accounts":
        return _mysql_account_facts(block)
    if normalize == "mysql_privileges":
        return _mysql_privilege_facts(block)
    if normalize == "mysql_connection_control":
        return _mysql_plugin_facts(block, "connection_control")
    if normalize == "mysql_password_policy":
        return _mysql_plugin_facts(block, "validate_password")
    if normalize == "mysql_audit":
        return _mysql_audit_facts(block)
    if normalize == "mysql_remote_access":
        return _mysql_remote_facts(block)
    if normalize == "mysql_backup":
        return _normalize_mysql_backup(block)
    if normalize == "h3c_config":
        return _normalize_h3c_config(block)
    raise ValueError(f"未知 normalize 标识：{normalize}")


def _sufficient(normalize: str, facts: list[DerivedFact]) -> bool:
    texts = {fact.text for fact in facts}
    requirements = {
        "duplicate_uid": ({"fact:duplicate_uid.none=true", "fact:duplicate_uid.none=false"}, {"fact:uid0.only_root=true", "fact:uid0.only_root=false"}),
        "empty_password": ({"fact:empty_password.none=true", "fact:empty_password.none=false"},),
        "accounts": ({"fact:account.expired.none=true", "fact:account.expired.none=false"},),
        "faillock": ({"fact:faillock.module=true", "fact:faillock.module=false"}, {"fact:faillock.policy=true", "fact:faillock.policy=false"}),
        "security_agent": ({"fact:security_agent.process.present=true", "fact:security_agent.process.present=false"}, {"fact:security_agent.package.present=true", "fact:security_agent.package.present=false"}),
        "key_file_permissions": ({"fact:file_permissions.passwd.secure=true", "fact:file_permissions.passwd.secure=false"}, {"fact:file_permissions.shadow.secure=true", "fact:file_permissions.shadow.secure=false"}),
        "auditd": ({"fact:auditd.active=true", "fact:auditd.active=false"}, {"fact:auditd.rules_loaded=true", "fact:auditd.rules_loaded=false"}),
        "mysql_accounts": ({"fact:mysql.account.anonymous.none=true", "fact:mysql.account.anonymous.none=false"}, {"fact:mysql.account.empty_password.none=true", "fact:mysql.account.empty_password.none=false"}),
        "mysql_privileges": ({"fact:mysql.privileges.complete=true"},),
        "mysql_connection_control": ({"fact:mysql.plugin.connection_control.none=true"},),
        "mysql_password_policy": ({"fact:mysql.plugin.validate_password.none=true"},),
        "mysql_audit": ({"fact:mysql.audit.enabled=true", "fact:mysql.audit.enabled=false"},),
        "mysql_remote_access": ({"fact:mysql.remote_access.restricted=true", "fact:mysql.remote_access.restricted=false"},),
        "selinux": ({"fact:security_labels.configured=true"},),
    }
    if normalize in {"mysql_connection_control", "mysql_password_policy"}:
        plugin = "connection_control" if normalize == "mysql_connection_control" else "validate_password"
        return any(text.startswith(f"fact:mysql.plugin.{plugin}.status=") or text == f"fact:mysql.plugin.{plugin}.none=true" for text in texts)
    if normalize not in requirements:
        return bool(facts)
    return all(any(text in texts for text in alternatives) for alternatives in requirements[normalize])


def normalize_block(block: CheckBlock, normalize: str) -> list[DerivedFact]:
    return _dispatch(normalize, block)


def normalize_session_command(
    normalize: str,
    kind: str,
    command: str,
    output: list[OutputLine],
    status: CheckStatus,
    source: str,
    line: int,
    snippet: str = "",
) -> list[DerivedFact]:
    anchor = EvidenceAnchor(file=source, line=line, snippet=snippet or command)
    block = CheckBlock(
        session=1,
        block_index=1,
        section="",
        title="session-command",
        status=status,
        commands=[command],
        command_anchors=[anchor],
        output=output,
        source=source,
    )
    facts = _dispatch(normalize, block)
    if status is CheckStatus.EMPTY and kind == "mysql":
        lowered = command.lower()
        if normalize == "mysql_audit" and "plugin" in lowered and "audit" in lowered:
            for plugin in ("audit_log", "server_audit"):
                if plugin in lowered:
                    _add(facts, _fact(block, f"fact:mysql.plugin.{plugin}.none=true"))
    return facts


def normalize_blocks(blocks: list[CheckBlock], checks: "ChecksMap | None", warnings: list[str] | None = None) -> None:
    """统一处理 uniTerm 与会话块，并把证据结构不足的块转为不可用。"""
    detected = next(
        (
            family
            for block in blocks
            if block.os_family != "unknown" and (family := detect_os_family(block.text))
        ),
        None,
    )
    for block in blocks:
        if detected and block.os_family in {None, "unknown"}:
            block.os_family = detected
        binding = checks.binding(block) if checks else None
        if not binding or not binding.normalize:
            continue
        new_facts = normalize_block(block, binding.normalize)
        existing = {fact.text for fact in block.facts}
        block.facts.extend(fact for fact in new_facts if fact.text not in existing)
        if block.status in {CheckStatus.COLLECTED, CheckStatus.EMPTY} and not _sufficient(binding.normalize, block.facts):
            block.status = CheckStatus.FAILED
            if warnings is not None:
                message = f"{block.source}：{block.title} 证据结构不足，按未采集处理"
                if message not in warnings:
                    warnings.append(message)
