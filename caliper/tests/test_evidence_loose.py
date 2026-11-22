"""原始证据装载：无 manifest 的日志目录、单个文件与图片附件。"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.checks.mapping import ChecksMap
from core.evidence.package import load_evidence, media_files, text_evidence_files

SAMPLE_LOG = """\
# ===== Ubuntu/Debian baseline check v18 (run as root) =====
===== RESULTS (collected) =====
===== 1. SYSTEM =====

[01] Host info
  cmd: hostnamectl
  hostname: demo
    key: value

[02] Accounts
  cmd: grep -E 'x' /etc/passwd
  no duplicate uid

[03] Broken block
  cmd: cat /nonexistent

===== END OF REPORT =====
"""


def test_load_loose_directory_without_manifest(tmp_path: Path) -> None:
    logs = tmp_path / "device-logs"
    logs.mkdir()
    (logs / "session.log").write_text(SAMPLE_LOG, encoding="utf-8")
    package = load_evidence(logs, host="设备A", level=3)
    assert [block.status.value for block in package.blocks] == [
        "collected",
        "empty",
        "failed",
    ]
    assert package.manifest.host == "设备A"
    assert package.manifest.status == "collected"
    assert package.manifest.level == 3


def test_load_single_log_file(tmp_path: Path) -> None:
    log = tmp_path / "Arme Oracle_192.0.2.10.log"
    log.write_text(SAMPLE_LOG, encoding="utf-8")
    package = load_evidence(log, host="设备B", level=2)
    assert len(package.blocks) == 3
    assert package.manifest.package_id == log.name
    assert package.manifest.level == 2
    assert [entry.path for entry in package.evidence_files] == [log.name]
    assert package.evidence_files[0].analyzed is True


def test_nested_same_named_logs_have_unique_source_anchors(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    for folder, host in (("first", "host=first"), ("second", "host=second")):
        directory = root / folder
        directory.mkdir(parents=True)
        (directory / "session.log").write_text(
            SAMPLE_LOG.replace("hostname: demo", f"hostname: {host}"),
            encoding="utf-8",
        )
    package = load_evidence(root)
    sources = {block.source for block in package.blocks}
    assert sources == {"first/session.log", "second/session.log"}
    assert {entry.path for entry in package.evidence_files} == sources
    assert all(entry.analyzed for entry in package.evidence_files)


def test_unparsed_configuration_and_images_are_registered(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    root.mkdir()
    (root / "sshd.conf").write_text("PermitRootLogin no\n", encoding="utf-8")
    (root / "snippet.sh").write_text("sshd -T\n", encoding="utf-8")
    (root / "screenshot.png").write_bytes(b"\x89PNG\r\n")
    package = load_evidence(root)
    entries = {entry.path: entry for entry in package.evidence_files}
    assert entries["sshd.conf"].kind == "configuration"
    assert entries["snippet.sh"].kind == "code"
    assert entries["screenshot.png"].kind == "image"
    assert len(entries["screenshot.png"].sha256) == 64
    assert not entries["sshd.conf"].analyzed
    assert not entries["snippet.sh"].analyzed
    assert not entries["screenshot.png"].analyzed


def test_images_only_directory_is_attachment(tmp_path: Path) -> None:
    shots = tmp_path / "screens"
    shots.mkdir()
    (shots / "1.png").write_bytes(b"\x89PNG\r\n")
    (shots / "2.jpg").write_bytes(b"\xff\xd8\xff")
    package = load_evidence(shots)
    assert package.blocks == []
    assert any("图片 2 张" in text for text in package.diagnostics)
    assert any("未识别到检查块" in text for text in package.diagnostics)
    assert len(media_files(shots)) == 2
    assert text_evidence_files(shots) == []


def test_broken_manifest_falls_back_to_raw_logs(tmp_path: Path) -> None:
    package_dir = tmp_path / "pkg"
    package_dir.mkdir()
    (package_dir / "manifest.json").write_text("{broken", encoding="utf-8")
    (package_dir / "session.log").write_text(SAMPLE_LOG, encoding="utf-8")
    package = load_evidence(package_dir)
    assert len(package.blocks) == 3
    assert any("manifest 校验失败" in text for text in package.diagnostics)


@pytest.mark.parametrize("encoding", ["utf-16", "utf-16-le", "utf-16-be", "utf-32"])
def test_utf16_and_utf32_session_logs_are_decoded(tmp_path: Path, encoding: str) -> None:
    text = """\
[2026/11/03 09:00:00] [demo@example ~]# cat /etc/os-release
[2026/11/03 09:00:01] PRETTY_NAME="Rocky Linux"
[2026/11/03 09:00:02] [demo@example ~]#
"""
    log = tmp_path / f"session-{encoding}.log"
    log.write_bytes(text.encode(encoding))
    checks = ChecksMap.load(
        Path(__file__).resolve().parents[1] / "packs" / "linux_os" / "checks_map.yaml"
    )

    package = load_evidence(log, checks=checks)

    assert len(package.blocks) == 1
    assert package.blocks[0].status.value == "collected"
    assert package.blocks[0].os_family == "rhel"
    assert package.blocks[0].facts[0].anchors[0].line == 2
