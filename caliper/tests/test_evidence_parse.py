"""证据解析：状态判定、锚点、错误路径。"""

from __future__ import annotations

from pathlib import Path

import pytest

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
