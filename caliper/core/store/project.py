"""项目配置读写。相对路径按项目文件所在目录解析，保存时保持用户填写的相对路径。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml
from pydantic import ValidationError

from core.model.entities import ProjectConfig


class ProjectStoreError(Exception):
    """项目文件不可用。"""


def load_project(path: Path) -> tuple[ProjectConfig, Path]:
    path = Path(path)
    if not path.exists():
        raise ProjectStoreError(f"项目文件不存在：{path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ProjectStoreError(f"{path}：YAML 无法解析：{exc}") from exc
    if not isinstance(data, dict):
        raise ProjectStoreError(f"{path}：应为键值结构")
    try:
        project = ProjectConfig.model_validate(data)
    except ValidationError as exc:
        raise ProjectStoreError(f"{path}：字段非法：{exc}") from exc
    return project, path.parent


def save_project(project: ProjectConfig, path: Path) -> Path:
    path = Path(path)
    payload = project.model_dump(mode="json")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    tmp.replace(path)
    return path


def new_project() -> ProjectConfig:
    return ProjectConfig(check_date=date.today())
