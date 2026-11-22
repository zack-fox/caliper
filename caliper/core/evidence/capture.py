"""数据采集命令库：加载、校验与采集脚本生成。

脚本结构与 ``core.evidence.logparse`` 的结果段约定保持一致：
``===== RESULTS (collected) =====`` → 分区 ``===== n. NAME =====`` →
``[nn] 标题`` + ``  cmd:`` / ``  file:`` + 两空格缩进的输出。
静态结构写在带引号的 heredoc 里，既能被执行，也能被现有解析器原样还原。
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
)

FAMILIES = {"server", "database"}
LEVELS = {2, 3}
STATUSES = {"active", "scaffold"}
RESULTS_MARKER = "===== RESULTS (collected) ====="
END_MARKER = "===== END OF REPORT ====="
# 单引号 heredoc：命令里的 $、反引号等一律原样写入，不参与 shell 展开。
HEREDOC = "CALIPER_EOF"


class CaptureError(Exception):
    """采集命令库不可用或参数非法。"""


def _single_line(value: str, field: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError(f"{field} 不能为空")
    if "\n" in text or "\r" in text:
        raise ValueError(f"{field} 必须是单行文本")
    return text


class CaptureRule(BaseModel):
    """一条采集命令：分区、块标题、只读命令、目标文件与期望输出。"""

    model_config = ConfigDict(extra="forbid")

    section: str
    title: str
    command: str
    file: str | None = None
    expect: str | None = None
    levels: list[int] = Field(min_length=1)
    families: list[str] = Field(min_length=1)

    @field_validator("section", "title", "command")
    @classmethod
    def _required_single_line(cls, value: str, info: ValidationInfo) -> str:
        return _single_line(value, info.field_name or "")

    @field_validator("file", "expect")
    @classmethod
    def _optional_single_line(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        if "\n" in text or "\r" in text:
            raise ValueError(f"{info.field_name} 必须是单行文本")
        return text

    @field_validator("levels")
    @classmethod
    def _check_levels(cls, value: list[int]) -> list[int]:
        invalid = sorted(set(value) - LEVELS)
        if invalid:
            raise ValueError(f"levels 只支持 2/3，实际 {invalid}")
        return sorted(set(value))

    @field_validator("families")
    @classmethod
    def _check_families(cls, value: list[str]) -> list[str]:
        normalized = [str(item).strip() for item in value]
        invalid = sorted(set(normalized) - FAMILIES)
        if invalid:
            raise ValueError(f"families 只支持 server/database，实际 {invalid}")
        return sorted(set(normalized))


class CaptureLibrary(BaseModel):
    """规则包目录下 capture.yaml 的完整内容。"""

    model_config = ConfigDict(extra="forbid")

    version: str
    status: str
    asset_family: str = "server"
    rules: list[CaptureRule] = Field(min_length=1)

    @field_validator("version")
    @classmethod
    def _check_version(cls, value: str) -> str:
        return _single_line(value, "version")

    @field_validator("status")
    @classmethod
    def _check_status(cls, value: str) -> str:
        status = value.strip()
        if status not in STATUSES:
            raise ValueError(f"status 只支持 active/scaffold，实际 {status!r}")
        return status

    @field_validator("asset_family")
    @classmethod
    def _check_asset_family(cls, value: str) -> str:
        family = value.strip()
        if family not in FAMILIES:
            raise ValueError(f"asset_family 只支持 server/database，实际 {family!r}")
        return family

    def rules_for(self, family: str, level: int) -> list[CaptureRule]:
        return [
            rule
            for rule in self.rules
            if family in rule.families and level in rule.levels
        ]


def load_capture(pack_dir: Path) -> CaptureLibrary:
    """读取并校验 ``<pack_dir>/capture.yaml``。任何结构问题都抛 CaptureError。"""
    path = Path(pack_dir) / "capture.yaml"
    if not path.is_file():
        raise CaptureError(f"{path}：缺少采集命令库")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise CaptureError(f"{path}：YAML 无法解析：{exc}") from exc
    if not isinstance(data, dict):
        raise CaptureError(f"{path}：采集命令库应为对象")
    if "rules" not in data:
        raise CaptureError(f"{path}：缺少 rules 列表")
    if not isinstance(data["rules"], list):
        raise CaptureError(f"{path}：rules 应为列表")
    if not data["rules"]:
        raise CaptureError(f"{path}：rules 不能为空")

    try:
        library = CaptureLibrary.model_validate(data)
    except ValidationError as exc:
        raise CaptureError(f"{path}：采集条目非法：{exc}") from exc

    seen: dict[str, int] = {}
    for index, rule in enumerate(library.rules, 1):
        if rule.title in seen:
            raise CaptureError(
                f"{path}：第 {index} 条与第 {seen[rule.title]} 条 title 重复：{rule.title}"
            )
        seen[rule.title] = index
    return library


def _section_block(section: str) -> str:
    return (
        f'cat >>"$B" <<\'{HEREDOC}\'\n'
        f"\n===== {section} =====\n"
        f"{HEREDOC}\n"
    )


def _rule_block(index: int, rule: CaptureRule) -> str:
    lines = ["", f"[{index:02d}] {rule.title}", f"  cmd: {rule.command}"]
    if rule.file:
        lines.append(f"  file: {rule.file}")
    static = "\n".join(lines)
    command = rule.command.rstrip(";").strip()
    expect = f"# 期望输出：{rule.expect}\n" if rule.expect else ""
    return (
        f"{expect}"
        f'cat >>"$B" <<\'{HEREDOC}\'\n'
        f"{static}\n"
        f"{HEREDOC}\n"
        f'out=$( {{ {command}; }} 2>/dev/null )\n'
        'if [ -n "$out" ]; then\n'
        'printf \'%s\\n\' "$out" | sed \'s/^/  /\' >>"$B"\n'
        "fi\n"
    )


def render_script(library: CaptureLibrary, family: str, level: int) -> str:
    """按资产族与等级拼出可直接执行的 POSIX shell 采集脚本。"""
    if family not in FAMILIES:
        raise CaptureError(f"family 只支持 server/database，实际 {family!r}")
    if level not in LEVELS:
        raise CaptureError(f"level 只支持 2/3，实际 {level}")
    rules = library.rules_for(family, level)
    if not rules:
        raise CaptureError(f"没有适用于 {family} 族 {level} 级的采集条目")

    parts = [
        "#!/bin/sh\n",
        "# Caliper 数据采集脚本\n",
        "# 仅供已授权环境使用；请只在取得书面授权的资产上执行，采集内容仅用于等保测评。\n",
        f"# ===== Ubuntu/Debian baseline check (family={family}, level={level}) =====\n",
    ]
    if family == "server":
        parts.append("# 同时适用于 CentOS/RHEL：安装包查询按 dpkg/rpm 自动分支。\n")
    else:
        parts.append("# 适用于 MySQL 8.x / MariaDB 10.x：只执行 SELECT/SHOW 与配置文件读取。\n")
        parts.append("# 连接参数请通过只读账户的客户端配置文件（如 ~/.my.cnf）提供。\n")
    parts.extend(
        [
            "B=${TMPDIR:-/tmp}/caliper-capture.$$\n",
            "trap 'rm -f \"$B\"' 0 1 2 15\n",
            ': >"$B"\n',
            # 报告头同时写进缓冲区：运行后 os_family 仍可被解析器识别。
            f'cat >>"$B" <<\'{HEREDOC}\'\n'
            f"# ===== Ubuntu/Debian baseline check (family={family}, level={level}) =====\n"
            f"{RESULTS_MARKER}\n"
            f"{HEREDOC}\n",
        ]
    )

    current_section = ""
    for index, rule in enumerate(rules, 1):
        if rule.section != current_section:
            parts.append(_section_block(rule.section))
            current_section = rule.section
        parts.append(_rule_block(index, rule))

    parts.extend(
        [
            f'cat >>"$B" <<\'{HEREDOC}\'\n\n{END_MARKER}\n{HEREDOC}\n',
            'cat "$B"\n',
        ]
    )
    return "".join(parts)
