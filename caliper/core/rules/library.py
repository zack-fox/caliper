"""六套规则库的统一入口：清单校验、装载与统计。

清单固定为规则包根目录下的 library.yaml，六个库缺一不可；
status=active 的库必须解析出规则，status=scaffold 允许暂时为空。
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

LIBRARY_KEYS = ("capture", "record", "judge", "remediation", "high_risk", "major")
STATUSES = {"active", "scaffold"}


class LibraryError(Exception):
    """六库清单或规则文件不可用。"""


class LibraryEntry(BaseModel):
    key: str
    title: str
    status: str
    paths: list[str] = Field(default_factory=list)
    rule_count: int = 0


class RuleLibrary(BaseModel):
    version: str
    pack_dir: Path
    entries: list[LibraryEntry] = Field(default_factory=list)

    @classmethod
    def load(cls, pack_dir: Path) -> "RuleLibrary":
        pack_dir = Path(pack_dir)
        manifest_path = pack_dir / "library.yaml"
        if not manifest_path.is_file():
            raise LibraryError(f"{manifest_path}：缺少六库清单")
        try:
            data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise LibraryError(f"{manifest_path}：YAML 无法解析：{exc}") from exc
        if not isinstance(data, dict):
            raise LibraryError(f"{manifest_path}：清单应为对象")
        version = str(data.get("version", "")).strip()
        if not version:
            raise LibraryError(f"{manifest_path}：缺少 version")
        libraries = data.get("libraries")
        if not isinstance(libraries, dict):
            raise LibraryError(f"{manifest_path}：缺少 libraries")

        missing = [key for key in LIBRARY_KEYS if key not in libraries]
        if missing:
            raise LibraryError(f"{manifest_path}：缺少规则库 {', '.join(missing)}")
        extra = sorted(set(libraries) - set(LIBRARY_KEYS))
        if extra:
            raise LibraryError(f"{manifest_path}：未登记的规则库 {', '.join(extra)}")

        entries: list[LibraryEntry] = []
        for key in LIBRARY_KEYS:
            spec = libraries[key]
            if not isinstance(spec, dict):
                raise LibraryError(f"{manifest_path}：{key} 配置应为对象")
            title = str(spec.get("title", "")).strip()
            status = str(spec.get("status", "")).strip()
            if not title or status not in STATUSES:
                raise LibraryError(f"{manifest_path}：{key} 的 title/status 非法")
            paths = cls._paths(spec)
            if not paths:
                raise LibraryError(f"{manifest_path}：{key} 未声明 path")
            count = 0
            for relative in paths:
                path = pack_dir / relative
                if not path.is_file():
                    raise LibraryError(f"{manifest_path}：{key} 的规则文件不存在：{relative}")
                count += _count_rules(path, key)
            if status == "active" and count == 0:
                raise LibraryError(f"{manifest_path}：{key} 标记为 active 但没有规则")
            entries.append(
                LibraryEntry(key=key, title=title, status=status, paths=paths, rule_count=count)
            )
        return cls(version=version, pack_dir=pack_dir, entries=entries)

    @staticmethod
    def _paths(spec: dict) -> list[str]:
        raw = spec.get("paths")
        if isinstance(raw, list):
            return [str(item) for item in raw]
        single = spec.get("path")
        return [str(single)] if single else []

    def entry(self, key: str) -> LibraryEntry | None:
        return next((entry for entry in self.entries if entry.key == key), None)

    def total_rules(self) -> int:
        return sum(entry.rule_count for entry in self.entries)


def _count_rules(path: Path, key: str) -> int:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise LibraryError(f"{path}：YAML 无法解析：{exc}") from exc
    if data is None:
        return 0
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        rules = data.get("rules")
        if rules is None:
            return 0
        if not isinstance(rules, list):
            raise LibraryError(f"{path}：{key} 的 rules 应为列表")
        return len(rules)
    raise LibraryError(f"{path}：{key} 的规则文件结构非法")
