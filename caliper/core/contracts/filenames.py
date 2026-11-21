"""四张产出表的文件名模板（项目编号为空写“未填写”）。"""

from __future__ import annotations

from datetime import datetime

EMPTY_PROJECT_CODE = "未填写"

ASSET_FILENAME = "服务器_存储设备_资产记录表.xlsx"
RESULT_FILENAME = "服务器_存储设备_结果记录表.xlsx"

ISSUE_FILENAME_TEMPLATE = "【安全问题汇总】_{project_code}_{system_name}测评_{date}_{time}.xlsx"
MAJOR_FILENAME_TEMPLATE = "【重大安全隐患】_{project_code}_{system_name}测评_{date}_{time}.xlsx"


def _parts(moment: datetime) -> dict[str, str]:
    return {"date": moment.strftime("%Y-%m-%d"), "time": moment.strftime("%H%M%S")}


def issue_filename(project_code: str, system_name: str, moment: datetime) -> str:
    return ISSUE_FILENAME_TEMPLATE.format(
        project_code=project_code or EMPTY_PROJECT_CODE,
        system_name=system_name,
        **_parts(moment),
    )


def major_filename(project_code: str, system_name: str, moment: datetime) -> str:
    return MAJOR_FILENAME_TEMPLATE.format(
        project_code=project_code or EMPTY_PROJECT_CODE,
        system_name=system_name,
        **_parts(moment),
    )
