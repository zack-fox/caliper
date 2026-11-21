"""界面与 core 之间的装配层：只调用 core，不自己造判定。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from core.contracts.filenames import RESULT_FILENAME
from core.evidence.package import EvidenceError, load_evidence, media_files, summarize
from core.issues.summary import (
    IssueRow,
    TextLibrary,
    build_issue_rows,
    render_issue_workbook,
    verify_issue_workbook,
)
from core.items.loader import Pack, PackError, load_pack
from core.judge.runner import RunError, run_project
from core.major.risk import build_major_rows, render_major_workbook, verify_major_workbook
from core.model.entities import Asset, Item, ProjectConfig, RunResult
from core.render.asset_record import AssetRecordError, fill_asset_workbook, verify_asset_workbook
from core.render.result_record import (
    RenderError,
    find_template,
    render_result_workbook,
    verify_workbook,
)
from core.rules.dsl import RuleError
from core.rules.engine import RulesError
from core.store.corrections import (
    CorrectionError,
    CorrectionStore,
    apply_notes,
    apply_record_overrides,
)
from core.store.project import ProjectStoreError, load_project, save_project

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACK_DIR = REPO_ROOT / "packs" / "linux_os"


class ControllerError(Exception):
    """界面层可直接展示的错误。"""


@dataclass(frozen=True)
class EvidencePreview:
    """证据包解析预览：界面只读这里，不关心 manifest 细节。"""

    ok: bool
    message: str
    host: str = ""
    os_family: str = ""
    level: int = 0
    blocks: int = 0
    images: int = 0


class AppController:
    def __init__(self) -> None:
        self.project = ProjectConfig(
            check_date=date.today(),
            pack_dir=DEFAULT_PACK_DIR,
            evidence_root=REPO_ROOT / "fixtures" / "evidence",
            output_dir=REPO_ROOT / "out",
        )
        self.base_dir = REPO_ROOT
        self.pack: Pack | None = None
        self.run_result: RunResult | None = None
        self.source_path: Path | None = None

    # ---- 项目 ----
    def load_project(self, path: Path) -> ProjectConfig:
        try:
            project, base = load_project(path)
        except ProjectStoreError as exc:
            raise ControllerError(str(exc)) from exc
        self.project = project
        self.base_dir = base
        self.source_path = path
        self.run_result = None
        return project

    def save_project(self, project: ProjectConfig, path: Path) -> Path:
        try:
            saved = save_project(project, path)
        except OSError as exc:
            raise ControllerError(f"保存项目失败：{exc}") from exc
        self.project = project
        self.source_path = saved
        if path.parent:
            self.base_dir = path.parent
        return saved

    def load_pack(self) -> Pack:
        pack_dir = self.project.pack_dir or DEFAULT_PACK_DIR
        if not pack_dir.is_absolute():
            pack_dir = self.base_dir / pack_dir
        try:
            self.pack = load_pack(pack_dir)
        except (PackError, RulesError, RuleError) as exc:
            raise ControllerError(f"规则包装载失败：{exc}") from exc
        return self.pack

    def items(self) -> list[Item]:
        pack = self.pack or self.load_pack()
        return pack.items_for_level(self.project.level)

    def guides(self) -> list[str]:
        """作业指导书清单；规则包装载失败时返回空列表，由界面给默认值。"""
        try:
            pack = self.pack or self.load_pack()
        except ControllerError:
            return []
        return list(pack.meta.guides)

    # ---- 证据包 ----
    def evidence_root_path(self) -> Path:
        root = self.project.evidence_root
        return root if root.is_absolute() else self.base_dir / root

    def evidence_path(self, package: str) -> Path:
        path = Path(package)
        return path if path.is_absolute() else self.evidence_root_path() / path

    def display_package_path(self, path: Path) -> str:
        """根目录内的证据包保存相对路径，项目整体迁移后仍可用。"""
        try:
            relative = path.resolve().relative_to(self.evidence_root_path().resolve())
        except ValueError:
            return str(path.resolve())
        return relative.as_posix()

    def inspect_evidence(
        self, package: str | None, device_name: str = ""
    ) -> EvidencePreview:
        if not package:
            return EvidencePreview(False, "未关联证据包")
        root = self.evidence_path(package)
        if not root.exists():
            return EvidencePreview(False, f"证据目录不存在：{root}")
        try:
            loaded = load_evidence(
                root, host=device_name, level=self.project.level
            )
        except (EvidenceError, OSError) as exc:
            return EvidencePreview(False, str(exc))
        images = len(media_files(root))
        counts = summarize(loaded.blocks)
        if not loaded.blocks:
            message = "未识别到检查块"
            if images:
                message += f"；图片 {images} 张仅作附件"
            return EvidencePreview(False, message, images=images)
        detail = " / ".join(f"{key} {value}" for key, value in sorted(counts.items()))
        manifest = loaded.manifest
        message = (
            f"{manifest.host}（{manifest.os_family}，{manifest.level} 级）"
            f"· {len(loaded.blocks)} 块：{detail}"
        )
        if images:
            message += f"；图片 {images} 张仅作附件"
        return EvidencePreview(
            True,
            message,
            host=manifest.host,
            os_family=manifest.os_family,
            level=manifest.level,
            blocks=len(loaded.blocks),
            images=images,
        )

    # ---- 跑批 ----
    def run(self) -> RunResult:
        pack = self.load_pack()
        try:
            result = run_project(self.project, pack, base_dir=self.base_dir)
        except RunError as exc:
            raise ControllerError(str(exc)) from exc
        store = self._store()
        try:
            apply_notes(result, store, self.project.level)
            apply_record_overrides(result, store, self.project.level)
        finally:
            store.close()
        self.run_result = result
        return result

    # ---- 校正 ----
    def _store(self) -> CorrectionStore:
        try:
            if self.source_path is not None:
                path = self.source_path.resolve().with_name("corrections.db")
            else:
                path = REPO_ROOT / "fixtures" / "samples" / "corrections.db"
            return CorrectionStore(path)
        except (CorrectionError, sqlite3.Error) as exc:
            raise ControllerError(str(exc)) from exc

    def save_note(self, item_id: str, asset_type: str, note: str) -> None:
        store = self._store()
        try:
            store.set(self.project.level, item_id, asset_type, "note", note)
        finally:
            store.close()

    def save_record_override(
        self,
        item_id: str,
        asset_key: str,
        result_text: str,
        verdict: str,
        note: str,
        reason: str,
    ) -> str:
        store = self._store()
        try:
            return store.save_record_override(
                self.project.level,
                item_id,
                asset_key,
                result_text,
                verdict,
                note,
                reason,
            )
        except (CorrectionError, sqlite3.Error) as exc:
            raise ControllerError(str(exc)) from exc
        finally:
            store.close()

    def clear_record_override(self, item_id: str, asset_key: str) -> None:
        store = self._store()
        try:
            store.clear_record_override(self.project.level, item_id, asset_key)
        except (CorrectionError, sqlite3.Error) as exc:
            raise ControllerError(str(exc)) from exc
        finally:
            store.close()

    def confirm_record(self, item_id: str, asset_key: str) -> str:
        store = self._store()
        try:
            return store.confirm_record(self.project.level, item_id, asset_key)
        except (CorrectionError, sqlite3.Error) as exc:
            raise ControllerError(str(exc)) from exc
        finally:
            store.close()

    def set_major_confirmed(
        self, item_id: str, asset_type: str, confirmed: bool
    ) -> None:
        store = self._store()
        try:
            store.set(
                self.project.level,
                item_id,
                asset_type,
                "major",
                "1" if confirmed else "",
            )
        finally:
            store.close()

    def confirmations(self) -> set[tuple[str, str]]:
        store = self._store()
        try:
            return store.major_confirmed(self.project.level)
        finally:
            store.close()

    def issue_rows(self) -> list[IssueRow]:
        if self.run_result is None:
            return []
        pack = self.pack or self.load_pack()
        return build_issue_rows(
            self.run_result,
            pack.items_for_level(self.project.level),
            TextLibrary(pack.texts),
            self.confirmations(),
        )

    # ---- 导出 ----
    def export_dir(self) -> Path:
        output = self.project.output_dir
        return output if output.is_absolute() else self.base_dir / output

    def export_issue(self) -> tuple[Path, list[str]]:
        pack = self.pack or self.load_pack()
        rows = self.issue_rows()
        try:
            template = find_template(pack.root, "issue_summary.xlsx")
            target = render_issue_workbook(rows, self.project, template, self.export_dir())
        except RenderError as exc:
            raise ControllerError(str(exc)) from exc
        return target, verify_issue_workbook(target, len(rows))

    def export_major(self) -> tuple[Path, list[str]]:
        pack = self.pack or self.load_pack()
        rows = build_major_rows(
            self.issue_rows(), pack.high_risk, self.project.level, self.confirmations()
        )
        try:
            template = find_template(pack.root, "major_risk.xlsx")
            target = render_major_workbook(rows, self.project, template, self.export_dir())
        except RenderError as exc:
            raise ControllerError(str(exc)) from exc
        return target, verify_major_workbook(target)

    def export_result(self) -> tuple[Path, list[str]]:
        if self.run_result is None:
            raise ControllerError("请先运行判定")
        pack = self.pack or self.load_pack()
        try:
            template = find_template(pack.root)
            target = render_result_workbook(
                self.run_result, pack.items_for_level(self.project.level), template, self.export_dir()
            )
        except RenderError as exc:
            raise ControllerError(str(exc)) from exc
        problems = verify_workbook(target, self.project.level, pack.items_for_level(self.project.level))
        return target, problems

    def export_asset(self, source: Path) -> tuple[Path | None, list[str], list[str]]:
        """返回 (输出路径, 错误, 提示)；错误非空时未生成文件。"""
        pack = self.pack or self.load_pack()
        try:
            report = fill_asset_workbook(
                source, self.project.assets, pack.meta.guides, self.export_dir()
            )
        except (AssetRecordError, OSError) as exc:
            raise ControllerError(str(exc)) from exc
        problems = (
            verify_asset_workbook(report.path, pack.meta.guides) if report.path else []
        )
        return report.path, [*report.errors, *problems], report.warnings

    def add_asset(self, asset: Asset) -> None:
        if self.project.asset_by_device(asset.device_name):
            raise ControllerError(f"设备名称重复：{asset.device_name}")
        self.project = self.project.model_copy(update={"assets": [*self.project.assets, asset]})

    def update_asset(self, original_device_name: str, asset: Asset) -> None:
        assets = list(self.project.assets)
        index = next(
            (i for i, item in enumerate(assets) if item.device_name == original_device_name),
            None,
        )
        if index is None:
            raise ControllerError(f"设备不存在：{original_device_name}")
        if asset.device_name != original_device_name and any(
            item.device_name == asset.device_name for item in assets
        ):
            raise ControllerError(f"设备名称重复：{asset.device_name}")
        assets[index] = asset
        self.project = self.project.model_copy(update={"assets": assets})

    def remove_asset(self, device_name: str) -> None:
        assets = [asset for asset in self.project.assets if asset.device_name != device_name]
        self.project = self.project.model_copy(update={"assets": assets})

    def expected_result_filename(self) -> str:
        return RESULT_FILENAME
