"""重大隐患三维评分：规则库装载、候选评估、规则版本与判定依据指纹。

高风险命中只是候选；本模块按相关、严重、高发三个维度加权评分，
达到阈值仍须人工确认并留痕后才允许导出。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Iterable

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from core.issues.summary import IssueRow
from core.major.risk import as_entry_dict, triggers_for
from core.model.entities import RunResult

if TYPE_CHECKING:
    from core.store.corrections import CorrectionStore

DIMENSION_NAMES = ("相关性", "严重性", "高发性")
WEIGHT_TOLERANCE = 0.001


class MajorError(Exception):
    """重大隐患规则库不可用。"""


class MajorGateError(Exception):
    """重大隐患人工确认未完成或已失效。"""


class MajorDimension(BaseModel):
    name: str
    weight: float

    @field_validator("name")
    @classmethod
    def _known_name(cls, value: str) -> str:
        if value not in DIMENSION_NAMES:
            raise ValueError(f"维度只支持 {'/'.join(DIMENSION_NAMES)}，实际 {value!r}")
        return value

    @field_validator("weight")
    @classmethod
    def _weight_range(cls, value: float) -> float:
        if not 0 < value <= 1:
            raise ValueError(f"维度权重应在 (0, 1] 内，实际 {value}")
        return value


class RuleScore(BaseModel):
    score: int
    reason: str

    @field_validator("score")
    @classmethod
    def _score_range(cls, value: int) -> int:
        if not 0 <= value <= 3:
            raise ValueError(f"维度得分应在 0—3 内，实际 {value}")
        return value

    @field_validator("reason")
    @classmethod
    def _reason_required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("维度评分理由不能为空")
        return value.strip()


class MajorRule(BaseModel):
    id: str
    hr_ids: list[str] = Field(min_length=1)
    scores: dict[str, RuleScore]

    @model_validator(mode="after")
    def _rule_complete(self) -> "MajorRule":
        if set(self.scores) != set(DIMENSION_NAMES):
            raise ValueError(
                f"{self.id} 的评分维度应完整包含 {'/'.join(DIMENSION_NAMES)}"
            )
        if len(set(self.hr_ids)) != len(self.hr_ids):
            raise ValueError(f"{self.id} 的 hr_ids 不能重复")
        return self


class MajorLibrary(BaseModel):
    version: str
    status: str = "active"
    threshold: float
    dimensions: list[MajorDimension]
    rules: list[MajorRule]

    @field_validator("threshold")
    @classmethod
    def _threshold_range(cls, value: float) -> float:
        if not 0 <= value <= 3:
            raise ValueError(f"阈值应在 0—3 内，实际 {value}")
        return value

    @model_validator(mode="after")
    def _library_complete(self) -> "MajorLibrary":
        if self.status != "active":
            raise ValueError(f"重大隐患规则库未启用（status={self.status}）")
        if not self.dimensions:
            raise ValueError("缺少 dimensions")
        if {item.name for item in self.dimensions} != set(DIMENSION_NAMES):
            raise ValueError("dimensions 必须完整包含相关性/严重性/高发性")
        total_weight = sum(item.weight for item in self.dimensions)
        if abs(total_weight - 1) > WEIGHT_TOLERANCE:
            raise ValueError(f"维度权重之和应为 1，实际 {total_weight}")
        if not self.rules:
            raise ValueError("active 的重大隐患规则库不能为空")
        ids = [rule.id for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("规则 id 不能重复")
        return self

    def dimension(self, name: str) -> MajorDimension:
        return next(item for item in self.dimensions if item.name == name)

    def evaluate(self, rule: MajorRule) -> tuple[float, list["DimensionScore"]]:
        scores: list[DimensionScore] = []
        total = 0.0
        for name in DIMENSION_NAMES:
            weight = self.dimension(name).weight
            entry = rule.scores[name]
            total += weight * entry.score
            scores.append(DimensionScore(name, entry.score, entry.reason, weight))
        return round(total, 2), scores

    def missing_hr_ids(self, high_risk_ids: Iterable[str]) -> list[str]:
        covered = {hr_id for rule in self.rules for hr_id in rule.hr_ids}
        return sorted(set(high_risk_ids) - covered)


@dataclass(frozen=True)
class DimensionScore:
    name: str
    score: int
    reason: str
    weight: float


@dataclass(frozen=True)
class MajorCandidate:
    """一条规则的评估结果；未达阈值时 is_candidate 为 false。"""

    rule_id: str
    hr_ids: tuple[str, ...]
    scores: tuple[DimensionScore, ...]
    total: float
    threshold: float
    is_candidate: bool
    clauses: tuple[str, ...] = ()
    binds_items: tuple[int, ...] = ()
    reducible: bool = False
    reduction_basis: tuple[str, ...] = ()


def load_major_library(path: Path) -> MajorLibrary:
    """读取并校验重大隐患规则库。"""
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise MajorError(f"{path}：无法读取重大隐患规则库：{exc}") from exc
    if not isinstance(raw, dict):
        raise MajorError(f"{path}：重大隐患规则库应为对象")
    try:
        return MajorLibrary.model_validate(raw)
    except ValidationError as exc:
        raise MajorError(f"{path}：重大隐患规则字段非法：{exc}") from exc


def assess_major(
    hits: Iterable[dict], library: MajorLibrary
) -> list[MajorCandidate]:
    """按命中的高风险条目评估规则，返回含是否候选的确定性列表。"""
    index: dict[str, dict] = {}
    for raw in hits:
        entry = as_entry_dict(raw)
        hr_id = str(entry.get("hr_id", "")).strip()
        if hr_id:
            index[hr_id] = entry

    results: list[MajorCandidate] = []
    for rule in library.rules:
        matched = [index[hr_id] for hr_id in rule.hr_ids if hr_id in index]
        if not matched:
            continue
        total, scores = library.evaluate(rule)
        clauses = tuple(
            dict.fromkeys(
                str(entry.get("标准要求", "")).strip()
                for entry in matched
                if str(entry.get("标准要求", "")).strip()
            )
        )
        binds = tuple(
            dict.fromkeys(
                seq for entry in matched for seq in entry.get("binds_items", [])
            )
        )
        results.append(
            MajorCandidate(
                rule_id=rule.id,
                hr_ids=tuple(rule.hr_ids),
                scores=tuple(scores),
                total=total,
                threshold=library.threshold,
                is_candidate=total >= library.threshold,
                clauses=clauses,
                binds_items=binds,
                reducible=any(bool(entry.get("可降风险")) for entry in matched),
                reduction_basis=tuple(
                    dict.fromkeys(
                        str(entry.get("降风险前提", "")).strip()
                        for entry in matched
                        if entry.get("可降风险") and str(entry.get("降风险前提", "")).strip()
                    )
                ),
            )
        )
    return results


def compute_rule_version(paths: Iterable[Path]) -> str:
    """按规则文件内容计算短哈希；文件顺序由调用方固定。"""
    digest = hashlib.sha256()
    for path in paths:
        digest.update(Path(path).read_bytes())
    return digest.hexdigest()[:12]


def basis_fingerprints(result: RunResult) -> dict[str, str]:
    """按资产类型汇总判定依据指纹；同类型多资产时再取内容哈希。"""
    grouped: dict[str, list[str]] = {}
    for run in result.asset_runs:
        grouped.setdefault(run.asset.asset_type.value, []).append(run.basis_fingerprint)
    fingerprints: dict[str, str] = {}
    for asset_type, values in grouped.items():
        unique = sorted(set(values))
        if len(unique) == 1:
            fingerprints[asset_type] = unique[0]
        else:
            raw = "|".join(unique)
            fingerprints[asset_type] = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return fingerprints


@dataclass(frozen=True)
class MajorGateItem:
    item_id: str
    asset_type: str
    seq: int
    rule_ids: tuple[str, ...]
    reason: str


def ensure_major_confirmations(
    issue_rows: list[IssueRow],
    high_risk: list[dict],
    library: MajorLibrary,
    level: int,
    run_result: RunResult,
    store: "CorrectionStore",
    rule_version: str,
) -> None:
    """导出前校验重大隐患候选的确认是否有效；不通过时抛出条目清单。"""
    fingerprints = basis_fingerprints(run_result)
    confirmed = store.major_confirmed(level)
    problems: list[MajorGateItem] = []

    for issue in issue_rows:
        key = (issue.item_id, issue.asset_type)
        entries = triggers_for(issue.seq, level, high_risk)
        if not entries:
            continue
        candidates = [item for item in assess_major(entries, library) if item.is_candidate]
        rule_ids = tuple(item.rule_id for item in candidates)
        if not candidates and key not in confirmed:
            continue
        basis = fingerprints.get(issue.asset_type)
        if basis is None:
            problems.append(
                MajorGateItem(
                    issue.item_id,
                    issue.asset_type,
                    issue.seq,
                    rule_ids,
                    "缺少判定依据指纹，需重新运行判定",
                )
            )
            continue
        reason = store.major_confirmation_issue(
            level, issue.item_id, issue.asset_type, rule_version, basis
        )
        if reason:
            problems.append(
                MajorGateItem(issue.item_id, issue.asset_type, issue.seq, rule_ids, reason)
            )

    if not problems:
        return
    examples = "；".join(
        f"{item.asset_type} 第{item.seq}项（{item.item_id}，{'+'.join(item.rule_ids) or '关联风险'}）{item.reason}"
        for item in problems[:3]
    )
    suffix = "" if len(problems) <= 3 else "；…"
    raise MajorGateError(
        f"还有 {len(problems)} 条重大隐患候选未完成有效人工确认，暂不能导出。"
        f"示例：{examples}{suffix}"
    )
