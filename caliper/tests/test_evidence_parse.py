"""证据解析：状态判定、锚点、错误路径。"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.checks.mapping import ChecksMap
from core.evidence.logparse import ParseError, parse_log_text
from core.evidence.package import load_package

SAMPLE_LOG = """\
# ===== Ubuntu/Debian baseline check v18 (run as root) =====
ubuntu@demo:~$ echo "===== RESULTS (collected) ====="
===== RESULTS (collected) =====
===== 1. SYSTEM =====

[01] Host info
  cmd: hostnamectl
  file: /etc/os-release
  hostname: demo
    key: value

[02] Accounts
  cmd: grep -E 'x' /etc/passwd
  no duplicate uid
  no empty-password account

[03] Broken block
  cmd: cat /nonexistent

===== END OF REPORT =====
"""


def test_parse_status_and_anchors() -> None:
    outcome = parse_log_text(SAMPLE_LOG, "demo.log")
    assert [block.status.value for block in outcome.blocks] == ["collected", "empty", "failed"]
    first = outcome.blocks[0]
    assert first.title == "Host info"
    assert first.section == "1. SYSTEM"
    assert first.os_family == "debian"
    assert first.output[0].line == 9
    assert "hostname: demo" in first.text
    assert first.file_refs == ["/etc/os-release"]


def test_parse_requires_results_marker() -> None:
    with pytest.raises(ParseError, match="未找到结果段"):
        parse_log_text("# nothing here\n", "bad.log")


def test_manifest_and_sha256_are_verified(tmp_path: Path) -> None:
    package = tmp_path / "pkg-x"
    (package / "raw").mkdir(parents=True)
    log = package / "raw" / "session.log"
    log.write_text(SAMPLE_LOG, encoding="utf-8")
    manifest = {
        "package_id": "pkg-x",
        "asset_id": "asset-x",
        "collected_at": "2026-11-20T20:24:41+08:00",
        "collector": "demo",
        "host": "demo",
        "os_family": "debian",
        "level": 3,
        "files": {"raw/session.log": "0" * 64},
        "status": "ok",
    }
    import json

    (package / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(Exception, match="sha256"):
        load_package(package)


@pytest.mark.skipif(
    not Path("fixtures/evidence/pkg-A01/manifest.json").exists(),
    reason="样例证据包不在本地（已被 .gitignore 忽略）",
)
def test_sample_package_has_89_blocks() -> None:
    package = load_package(Path("fixtures/evidence/pkg-A01"))
    assert len(package.blocks) == 89
    sessions = {block.session for block in package.blocks}
    assert len(sessions) == 2


PACK = Path(__file__).resolve().parents[1] / "packs" / "linux_os"


def _session_checks() -> ChecksMap:
    return ChecksMap.load(PACK / "checks_map.yaml")


def test_securecrt_timestamps_empty_error_and_sensitive_input() -> None:
    text = """\
[2026/11/03 09:00:00] [demo@example ~]# cat /etc/os-release
[2026/11/03 09:00:01] PRETTY_NAME="Rocky Linux"
[2026/11/03 09:00:02] [demo@example ~]# grep -E 'TMOUT=' /etc/profile
[2026/11/03 09:00:03] [demo@example ~]# grep PASS_MAX_DAYS /etc/login.defs
[2026/11/03 09:00:04] [demo@example ~]# mysql --password=placeholder
[2026/11/03 09:00:05] [demo@example ~]#
"""
    outcome = parse_log_text(text, "securecrt.log", checks=_session_checks())
    blocks = {block.title: block for block in outcome.blocks}

    host = blocks["Host / OS / kernel / time"]
    assert host.status.value == "collected"
    assert host.os_family == "rhel"
    os_fact = next(fact for fact in host.facts if fact.text == "fact:os.family=rhel")
    assert os_fact.anchors[0].line == 2
    assert os_fact.anchors[0].snippet.startswith("[2026/11/03 09:00:01]")

    timeout = blocks["Session timeout TMOUT"]
    assert timeout.status.value == "empty"
    assert "fact:session.tmout.valid=false" in timeout.rule_lines
    assert timeout.facts[0].anchors[0].line == 3
    assert blocks["Password policy (login.defs)"].status.value == "failed"
    assert all("placeholder" not in command for block in outcome.blocks for command in block.commands)
    assert any("含凭据参数" in warning for warning in outcome.warnings)


def test_shell_file_errors_never_become_negative_evidence() -> None:
    text = """\
[demo@example ~]# cat /etc/os-release
cat: /etc/os-release: No such file or directory
[demo@example ~]#
"""
    outcome = parse_log_text(text, "error.log", checks=_session_checks())
    assert len(outcome.blocks) == 1
    assert outcome.blocks[0].status.value == "failed"
    assert outcome.blocks[0].facts == []


def test_mysql_tables_continuation_merged_commands_and_unknown_os() -> None:
    text = """\
mysql> SELECT
    -> VERSION();
+--------------------+
| VERSION()          |
+--------------------+
| 8.0.0-0ubuntu0.1   |
+--------------------+
1 row in set (0.00 sec)
mysql> SELECT User, Host FROM mysql.user WHERE User='';
Empty set (0.00 sec)
mysql> SELECT User, Host FROM mysql.user WHERE authentication_string='';
+------+-----------+
| User | Host      |
+------+-----------+
| demo | localhost |
+------+-----------+
1 row in set (0.00 sec)
mysql> SELECT User, Host, Super_priv FROM mysql.user;
+------+-----------+------------+
| User | Host      | Super_priv |
+------+-----------+------------+
| demo | localhost | N          |
+------+-----------+------------+
1 row in set (0.00 sec)
mysql> SHOW GLOBAL VARIABLES LIKE 'general_log';
+---------------+-------+
| Variable_name | Value |
+---------------+-------+
| general_log   | OFF   |
+---------------+-------+
1 row in set (0.00 sec)
mysql> SELECT PLUGIN_NAME, PLUGIN_STATUS FROM information_schema.PLUGINS
    -> WHERE PLUGIN_NAME LIKE '%audit%';
Empty set (0.00 sec)
mysql> SHOW GLOBAL VARIABLES LIKE 'log_bin';
+---------------+-------+
| Variable_name | Value |
+---------------+-------+
| log_bin       | ON    |
+---------------+-------+
1 row in set (0.00 sec)
mysql>
"""
    outcome = parse_log_text(text, "mysql.log", checks=_session_checks())
    blocks = {block.title: block for block in outcome.blocks}

    assert {block.os_family for block in outcome.blocks} == {"unknown"}
    version = blocks["MySQL 版本与运行状态"]
    assert version.status.value == "collected"
    assert any(fact.text.startswith("fact:mysql.variable.version=") for fact in version.facts)

    accounts = blocks["MySQL 空口令与匿名账户"]
    assert accounts.status.value == "collected"
    assert {
        "fact:mysql.account.anonymous.none=true",
        "fact:mysql.account.empty_password.none=false",
    } <= {fact.text for fact in accounts.facts}
    assert not any(fact.text == "fact:mysql.account.anonymous.none=false" for fact in accounts.facts)
    assert all(fact.anchors and fact.anchors[0].file == "mysql.log" for fact in accounts.facts)

    # 同一条账户 SQL 可进入多个块，但权限列不足时不得给出最小权限结论。
    assert blocks["MySQL 账户权限与最小化"].status.value == "failed"
    assert blocks["MySQL 远程访问限制"].status.value == "failed"

    audit = blocks["MySQL 审计日志"]
    assert audit.status.value == "collected"
    assert {
        "fact:mysql.plugin.audit_log.none=true",
        "fact:mysql.plugin.server_audit.none=true",
        "fact:mysql.audit.enabled=false",
    } <= {fact.text for fact in audit.facts}

    backup = blocks["MySQL 备份与恢复"]
    assert backup.status.value == "collected"
    assert "fact:mysql.backup.context_only=true" in backup.rule_lines
    assert not any("backup.enabled" in fact.text for fact in backup.facts)


def test_mysql_error_output_is_failed() -> None:
    text = """\
mysql> SHOW GLOBAL VARIABLES LIKE 'general_log';
ERROR 1045 (28000): Access denied
mysql>
"""
    outcome = parse_log_text(text, "mysql-error.log", checks=_session_checks())
    assert outcome.blocks[0].status.value == "failed"
    assert outcome.blocks[0].facts == []


def test_checks_json_keeps_raw_output_and_derived_facts_compatible(tmp_path: Path) -> None:
    import hashlib
    import json

    package = tmp_path / "pkg-json"
    (package / "checks").mkdir(parents=True)
    record = {
        "block_index": 11,
        "section": "2. IDENTIFICATION",
        "title": "Session timeout TMOUT",
        "os_family": "debian",
        "status": "collected",
        "cmd": ["grep -E 'TMOUT=' /etc/profile"],
        "output": [{"line": 17, "text": "TMOUT=600", "snippet": "raw: TMOUT=600"}],
    }
    payload = json.dumps({"blocks": [record]}, ensure_ascii=False).encode()
    (package / "checks" / "session.json").write_bytes(payload)
    manifest = {
        "package_id": "pkg-json",
        "asset_id": "asset-json",
        "collected_at": "2026-11-20T20:24:41+08:00",
        "collector": "synthetic",
        "host": "example",
        "os_family": "debian",
        "level": 3,
        "files": {"checks/session.json": hashlib.sha256(payload).hexdigest()},
        "status": "ok",
    }
    (package / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    loaded = load_package(package, checks=_session_checks())
    block = loaded.blocks[0]
    assert block.status.value == "collected"
    assert block.text_lines == ["TMOUT=600"]
    assert "fact:session.tmout.valid=true" in block.rule_lines
    fact = next(fact for fact in block.facts if fact.text.endswith("=true"))
    assert fact.anchors[0].file == "checks/session.json"
    assert fact.anchors[0].line == 17
    assert fact.anchors[0].snippet == "raw: TMOUT=600"


def test_pam_and_shadow_file_reads_feed_multiple_blocks() -> None:
    text = """\
[demo@example ~]# cat /etc/os-release
NAME="Rocky Linux"
[demo@example ~]# more /etc/pam.d/system-auth
auth        required      pam_faillock.so preauth
account     required      pam_unix.so
password    requisite     pam_pwquality.so try_first_pass
password    sufficient    pam_unix.so sha512 shadow
[demo@example ~]# more /etc/shadow
demo:$6$placeholder$abcdefghijklmnop:19000:0:99999:7:::
app:!:19000:0:99999:7:::
[demo@example ~]#
"""
    outcome = parse_log_text(text, "pam.log", checks=_session_checks())
    blocks = {block.title: block for block in outcome.blocks}

    assert blocks["Password hash algorithm"].status.value == "collected"
    assert blocks["Password complexity"].status.value == "collected"
    assert "fact:pam.password_complexity.enabled=true" in blocks["Password complexity"].rule_lines
    assert blocks["Login failure lockout (faillock)"].status.value == "failed"
    assert "fact:faillock.module=true" in blocks["Login failure lockout (faillock)"].rule_lines
    assert blocks["Empty / expired password"].status.value == "collected"
    assert "fact:empty_password.none=true" in blocks["Empty / expired password"].rule_lines
    shadow = next(
        fact
        for fact in blocks["Empty / expired password"].facts
        if fact.text == "fact:empty_password.none=true"
    )
    assert shadow.anchors[0].line == 9


def test_failed_command_does_not_discard_sibling_evidence() -> None:
    text = """\
[demo@example ~]# nginx -v
bash: nginx: command not found
[demo@example ~]# ps -ef | grep -i nginx
root 100 1 0 09:00 ? 00:00:00 nginx: master process nginx
[demo@example ~]# cat /etc/nginx/nginx.conf
cat: /etc/nginx/nginx.conf: Permission denied
[demo@example ~]#
"""
    outcome = parse_log_text(text, "nginx.log", checks=_session_checks())
    block = next(block for block in outcome.blocks if block.title == "Nginx version / run user")

    assert block.status.value == "collected"
    assert len(block.commands) == 3
    assert any("Permission denied" in line.text for line in block.output)
    assert all(anchor.line for anchor in block.command_anchors)


def test_block_with_only_failed_commands_stays_failed() -> None:
    text = """\
[demo@example ~]# cat /etc/nginx/nginx.conf
cat: /etc/nginx/nginx.conf: Permission denied
[demo@example ~]# nginx -v
bash: nginx: command not found
[demo@example ~]#
"""
    outcome = parse_log_text(text, "nginx-error.log", checks=_session_checks())
    block = outcome.blocks[0]

    assert block.title == "Nginx version / run user"
    assert block.status.value == "failed"

