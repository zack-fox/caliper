"""整改建议润色：只发送白名单字段，默认不发起任何网络调用。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from core.remediation.generator import Advice

# 发给模型的白名单字段：问题、成因、动作、优先级、条款、标题。
# 证据原文、备注、日志、主机名、IP 等一律不出机。
PAYLOAD_FIELDS = ("problem", "cause", "action", "priority", "clause", "title")


class PolishClient(Protocol):
    """外部润色客户端的最小边界；本模块不提供任何联网实现。"""

    def polish(self, payload: Mapping[str, str]) -> Mapping[str, Any]: ...


def build_payload(advice: Advice) -> dict[str, str]:
    """构造脱敏后的请求体，只含白名单字段。"""
    data = advice.model_dump()
    return {field: str(data.get(field, "")) for field in PAYLOAD_FIELDS}


def polish(advice: Advice, client: PolishClient | None = None) -> Advice:
    """client 为空时原样返回；有客户端时也只允许回写白名单字段。"""
    if client is None:
        return advice
    result = client.polish(build_payload(advice))
    if not isinstance(result, Mapping):
        return advice
    updates = {
        key: str(value)
        for key, value in result.items()
        if key in PAYLOAD_FIELDS and key in Advice.model_fields and value is not None
    }
    return advice.model_copy(update=updates) if updates else advice
