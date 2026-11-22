"""记录表模型：公司日常记录表的 9 列口径。

只做「判定结果 → 记录行」的搬运与取值收敛，不生成判定，也不写 xlsx。
表头区与列序以历史记录表为准，见 docs/PROJECT-PLAN.md 第五节。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from core.contracts.verdict import Verdict
from core.model.entities import AssetRun, Item, ItemResult, ProjectConfig
from core.records.profile import RecordError, RecordProfile, load_profile

COLUMNS = (
    "序号",
    "控制点",
    "控制项",
    "结果记录",
    "符合情况",
    "备注",
    "重要程度",
    "检查内容",
    "判断标准",
)

# 备注只承载不适用理由与未采集诊断，判定说明留在结果记录列。
NOTE_VERDICTS = {Verdict.NOT_APPLICABLE, Verdict.UNCOLLECTED}


class RecordHeader(BaseModel):
    """记录表表头区：项目编号、系统名称、核查对象等固定字段。"""

    project_code: str = ""
    system_name: str = ""
    asset_name: str = ""
    asset_type: str = ""
    ip: str = ""
    check_date: str = ""
    guide: str = ""
    domain: str = "安全计算环境"


class RecordRow(BaseModel):
    seq: int
    control_point: str
    control_item: str
    result_text: str = ""
    compliance: str = ""
    note: str = ""
    importance: str = ""
    check_content: str = ""
    criteria: str = ""

    def values(self) -> tuple[str, ...]:
        return (
            str(self.seq),
            self.control_point,
            self.control_item,
            self.result_text,
            self.compliance,
            self.note,
            self.importance,
            self.check_content,
            self.criteria,
        )


class RecordSheet(BaseModel):
    header: RecordHeader
    rows: list[RecordRow] = Field(default_factory=list)

    def row_by_seq(self, seq: int) -> RecordRow | None:
        return next((row for row in self.rows if row.seq == seq), None)


def build_sheet(
    project: ProjectConfig,
    run: AssetRun,
    items: list[Item],
    profile: RecordProfile | None = None,
) -> RecordSheet:
    """由一次资产核查结果构建记录表；items 用于补齐检查内容与判断标准。

    符合情况文案默认从项目 pack 的 record.yaml 加载；显式传入 profile 可覆盖，
    便于规则库变更后的回归比对。
    """
    if profile is None:
        if project.pack_dir is None:
            raise RecordError("项目未配置 pack_dir，无法加载 record.yaml；可显式传入 profile")
        profile = load_profile(project.pack_dir)
    by_seq = {item.seq: item for item in items}
    rows: list[RecordRow] = []
    for result in sorted(run.items, key=lambda entry: entry.seq):
        item = by_seq.get(result.seq)
        if item is None:
            continue
        rows.append(
            RecordRow(
                seq=result.seq,
                control_point=result.control_point,
                control_item=item.control_item,
                result_text=_result_text(result),
                compliance=profile.text(result.verdict),
                note=result.note if result.verdict in NOTE_VERDICTS else "",
                importance=result.importance,
                check_content=item.check_content,
                criteria=item.criteria,
            )
        )
    return RecordSheet(header=_header(project, run), rows=rows)


def _header(project: ProjectConfig, run: AssetRun) -> RecordHeader:
    return RecordHeader(
        project_code=project.project_code,
        system_name=project.system_name,
        asset_name=run.asset.device_name,
        asset_type=run.asset.asset_type.value,
        ip=run.asset.ip,
        check_date=project.check_date.isoformat(),
        guide=run.asset.guide,
    )


def _result_text(result: ItemResult) -> str:
    """结果记录统一以「经核查：」起句；无实施点时用结论 + 原因兜底，不落空串。"""
    text = result.result_text.strip()
    if text:
        return text if text.startswith("经核查") else f"经核查：{text}"
    reason = result.note.strip()
    if not reason:
        return f"经核查：{result.verdict.value}"
    # 备注已自带结论前缀（如「未采集：…」）时不再重复写判定值
    if reason.startswith(f"{result.verdict.value}："):
        return f"经核查：{reason}"
    return f"经核查：{result.verdict.value}，{reason}"
