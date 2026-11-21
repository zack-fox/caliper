"""渲染层：结果记录表与资产记录表；问题汇总/重大隐患在 P6–P7 接入。"""

from core.render.asset_record import (
    AssetRecordError,
    AssetReport,
    fill_asset_workbook,
    verify_asset_workbook,
)
from core.render.result_record import (
    RenderError,
    estimate_height,
    find_template,
    render_result_workbook,
    sanitize_sheet_name,
    verify_workbook,
)

__all__ = [
    "AssetRecordError",
    "AssetReport",
    "RenderError",
    "estimate_height",
    "fill_asset_workbook",
    "find_template",
    "render_result_workbook",
    "sanitize_sheet_name",
    "verify_asset_workbook",
    "verify_workbook",
]
