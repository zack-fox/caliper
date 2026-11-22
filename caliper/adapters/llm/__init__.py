"""大模型适配层。

默认不联网：只提供整改建议的字段白名单与空实现润色，
真实客户端必须由调用方显式注入。
"""

from adapters.llm.polish import PAYLOAD_FIELDS, PolishClient, build_payload, polish

__all__ = ["PAYLOAD_FIELDS", "PolishClient", "build_payload", "polish"]
