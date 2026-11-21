"""把规则结果链接回安全要求和测评要求中的原始单元。"""

from __future__ import annotations

import re

from core.model.entities import Item

_CES_CONTROL_POINTS = {
    "身份鉴别": 1,
    "访问控制": 2,
    "安全审计": 3,
    "入侵防范": 4,
    "恶意代码防范": 5,
    "可信验证": 6,
    "数据完整性": 7,
    "数据保密性": 8,
    "数据备份恢复": 9,
    "剩余信息保护": 10,
    "个人信息保护": 11,
}
_LETTER_RE = re.compile(r"^\s*([a-z])\s*[）)]", re.IGNORECASE)


def standard_references(item: Item) -> list[str]:
    """返回可核对的标准单元引用；不推断未登记的标准条款编号。"""
    refs: list[str] = []
    identifier = item.item_id.upper()
    if identifier.startswith(("L2-CES1-", "L3-CES1-")):
        control_clause = _CES_CONTROL_POINTS.get(item.control_point)
        letter = _LETTER_RE.match(item.control_item)
        if control_clause is not None and letter:
            refs.append(
                f"GB/T 22239—2019 §8.1.4.{control_clause} {letter.group(1).lower()})"
            )
    refs.append(
        f"GB/T 28448—2019 {item.item_id} c)测评实施 / d)单元判定"
    )
    return refs
