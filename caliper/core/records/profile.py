"""记录表生成规则库：符合情况文案的唯一来源。

口径写在 pack 根目录的 record.yaml 的 `rules` 列表中：每条规则把一种五值判定
（match）映射为记录表单元格文案（text），取值只能是
「符合(1分) / 不符合(0分) / 不适用 / 空」。
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from core.contracts.verdict import Verdict

RECORD_FILENAME = "record.yaml"
ALLOWED_COMPLIANCE_TEXT = ("符合(1分)", "不符合(0分)", "不适用", "")
EXPECTED_MATCHES = {verdict.value for verdict in Verdict}


class RecordError(Exception):
    """记录表生成规则库缺失或取值非法。"""


class RecordRule(BaseModel):
    """一条记录表文案规则：五值判定 → 单元格文案。"""

    id: str
    match: Verdict
    text: str


class RecordProfile(BaseModel):
    """record.yaml 的装载结果；rules 是记录表符合情况的唯一口径。"""

    version: str = ""
    status: str = ""
    rules: list[RecordRule] = Field(default_factory=list)

    def text(self, verdict: Verdict) -> str:
        for rule in self.rules:
            if rule.match == verdict:
                return rule.text
        raise RecordError(f"缺少 {verdict.value} 的符合情况文案")


def load_profile(pack_dir: Path) -> RecordProfile:
    """读取 pack 的 record.yaml；缺文件、缺规则或非法取值一律抛 RecordError。"""
    pack_dir = Path(pack_dir)
    path = pack_dir / RECORD_FILENAME
    if not path.is_file():
        raise RecordError(f"{path}：缺少记录表生成规则库")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RecordError(f"{path}：YAML 无法解析：{exc}") from exc
    if not isinstance(data, dict):
        raise RecordError(f"{path}：规则库应为对象")

    raw = data.get("rules")
    if not isinstance(raw, list):
        raise RecordError(f"{path}：缺少 rules")
    if len(raw) < len(Verdict):
        raise RecordError(f"{path}：rules 至少 {len(Verdict)} 条")

    seen_ids: set[str] = set()
    seen_verdicts: dict[Verdict, str] = {}
    rules: list[RecordRule] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise RecordError(f"{path}：第 {index} 条规则应为对象")

        rule_id = item.get("id")
        if not isinstance(rule_id, str) or not rule_id.strip():
            raise RecordError(f"{path}：第 {index} 条规则缺少 id")
        rule_id = rule_id.strip()
        if rule_id in seen_ids:
            raise RecordError(f"{path}：规则 id 重复：{rule_id}")
        seen_ids.add(rule_id)

        match = item.get("match")
        if not isinstance(match, str) or match not in EXPECTED_MATCHES:
            raise RecordError(f"{path}：{rule_id} 的 match {match!r} 未登记")
        verdict = Verdict(match)
        if verdict in seen_verdicts:
            raise RecordError(
                f"{path}：{match} 重复出现（{seen_verdicts[verdict]} / {rule_id}）"
            )

        value = item.get("text")
        # YAML 里未加引号的空值会解析成 None，统一按空文案处理
        if value is None:
            value = ""
        if not isinstance(value, str):
            raise RecordError(f"{path}：{rule_id} 的文案应为字符串")
        value = value.strip()
        if value not in ALLOWED_COMPLIANCE_TEXT:
            allowed = " / ".join(text or "空" for text in ALLOWED_COMPLIANCE_TEXT)
            raise RecordError(
                f"{path}：{rule_id} 的取值 {value!r} 非法，只能是 {allowed}"
            )

        seen_verdicts[verdict] = rule_id
        rules.append(RecordRule(id=rule_id, match=verdict, text=value))

    missing = [verdict.value for verdict in Verdict if verdict not in seen_verdicts]
    if missing:
        raise RecordError(f"{path}：rules 缺少 {', '.join(missing)}")

    return RecordProfile(
        version=str(data.get("version", "")),
        status=str(data.get("status", "")),
        rules=rules,
    )
