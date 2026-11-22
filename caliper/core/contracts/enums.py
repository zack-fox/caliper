"""枚举：资产类型、重要程度、风险等级、整改状态、安全问题属性、安全层面、安全要求。"""

from __future__ import annotations

from enum import Enum


class AssetType(str, Enum):
    SERVER = "服务器"
    STORAGE = "存储设备"
    DATABASE = "数据库"

    @property
    def family(self) -> str:
        """规则库适用口径：服务器与数据库分开建模。"""
        return "database" if self is AssetType.DATABASE else "server"


class Importance(str, Enum):
    CRITICAL = "关键"
    IMPORTANT = "重要"
    NORMAL = "一般"


class RiskLevel(str, Enum):
    HIGH = "高"
    MEDIUM = "中"
    LOW = "低"


class RectifyStatus(str, Enum):
    PENDING = "未整改"
    IN_PROGRESS = "整改中"
    DONE = "已整改"


class SecurityIssueAttr(str, Enum):
    TECH = "安全技术"
    MGMT = "安全管理"


class SecurityLayer(str, Enum):
    PHYSICAL = "安全物理环境"
    NETWORK = "安全通信网络"
    BOUNDARY = "安全区域边界"
    COMPUTING = "安全计算环境"
    MANAGEMENT_CENTER = "安全管理中心"
    POLICY = "安全管理制度"
    ORGANIZATION = "安全管理机构"
    PERSONNEL = "安全管理人员"
    CONSTRUCTION = "安全建设管理"
    OPERATION = "安全运维管理"


class Requirement(str, Enum):
    GENERAL = "安全通用要求"
