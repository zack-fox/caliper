"""原始证据装载：无 manifest 的日志目录、单个文件与图片附件。"""

from __future__ import annotations

from pathlib import Path

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
