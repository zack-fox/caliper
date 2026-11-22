"""从网络设备指导书生成多厂商、多等级的设备规则域。

用法：
  .venv/bin/python tools/build_network_pack.py --guide guides/network.json --out packs/network_devices

设计原则：
- 测评项按等级共享，厂商只提供自己的采集块、归一化事实和判定规则；
- 同一测评项可以关联多个厂商采集适配器，但绝不把厂商命令混在同一条规则里；
- 自动化只判断配置/状态回显能证明的实施点，人工核查点单独保留。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
LINUX_PACK = REPO_ROOT / "packs" / "linux_os"

LEVELS = (2, 3, 4)

# 单元号是指导书的标准条款号；seq 只是原表行序，不能跨等级复用。
LEVEL_KEYS: dict[int, dict[int, str]] = {
    2: {
        1: "AUTH_ID",
        2: "LOGIN_FAIL",
        3: "REMOTE",
        4: "ACCOUNT_PERM",
        5: "DEFAULT",
        6: "EXTRA_ACCOUNT",
        7: "PRIV_SEP",
        8: "AUDIT_ENABLE",
        9: "AUDIT_CONTENT",
        10: "AUDIT_PROTECT",
        11: "MIN_INSTALL",
        12: "CLOSE_SERVICES",
        13: "TERMINAL",
        14: "INPUT",
        15: "VULN",
        16: "MALWARE",
        17: "TRUST",
        18: "INTEGRITY_TRANSFER",
        19: "BACKUP_LOCAL",
        20: "BACKUP_OFFSITE",
        21: "RESIDUAL",
        22: "PERSONAL_COLLECT",
        23: "PERSONAL_USE",
    },
    3: {
        1: "AUTH_ID",
        2: "LOGIN_FAIL",
        3: "REMOTE",
        4: "TWO_FACTOR",
        5: "ACCOUNT_PERM",
        6: "DEFAULT",
        7: "EXTRA_ACCOUNT",
        8: "PRIV_SEP",
        9: "ACCESS_POLICY",
        10: "ACCESS_GRANULARITY",
        11: "SECURITY_MARK",
        12: "AUDIT_ENABLE",
        13: "AUDIT_CONTENT",
        14: "AUDIT_PROTECT",
        15: "AUDIT_PROCESS",
        17: "MIN_INSTALL",
        18: "CLOSE_SERVICES",
        19: "TERMINAL",
        20: "INPUT",
        21: "VULN",
        22: "INTRUSION_DETECT",
        23: "MALWARE",
        24: "TRUST",
        25: "INTEGRITY_TRANSFER",
        26: "INTEGRITY_STORE",
        27: "CONF_TRANSFER",
        28: "CONF_STORE",
        29: "BACKUP_LOCAL",
        30: "BACKUP_OFFSITE",
        31: "HOT_REDUNDANCY",
        32: "RESIDUAL_STORAGE",
        33: "RESIDUAL_CLEAR",
        34: "PERSONAL_COLLECT",
        35: "PERSONAL_USE",
    },
    4: {
        1: "AUTH_ID",
        2: "LOGIN_FAIL",
        3: "REMOTE",
        4: "TWO_FACTOR",
        5: "ACCOUNT_PERM",
        6: "DEFAULT",
        7: "EXTRA_ACCOUNT",
        8: "PRIV_SEP",
        9: "ACCESS_POLICY",
        10: "ACCESS_GRANULARITY",
        11: "SECURITY_MARK",
        12: "AUDIT_ENABLE",
        13: "AUDIT_CONTENT",
        14: "AUDIT_PROTECT",
        15: "AUDIT_PROCESS",
        16: "MIN_INSTALL",
        17: "CLOSE_SERVICES",
        18: "TERMINAL",
        19: "INPUT",
        20: "VULN",
        21: "INTRUSION_DETECT",
        22: "TRUST",
        23: "INTEGRITY_TRANSFER",
        24: "INTEGRITY_STORE",
        25: "NON_REPUDIATION",
        26: "CONF_TRANSFER",
        27: "CONF_STORE",
        28: "BACKUP_LOCAL",
        29: "BACKUP_OFFSITE",
        30: "HOT_REDUNDANCY",
        31: "DR_CENTER",
    },
}

AUTO_KEYS: dict[int, set[str]] = {
    2: {
        "AUTH_ID",
        "LOGIN_FAIL",
        "REMOTE",
        "ACCOUNT_PERM",
        "DEFAULT",
        "PRIV_SEP",
        "AUDIT_ENABLE",
        "AUDIT_PROTECT",
        "TERMINAL",
        "INTEGRITY_TRANSFER",
    },
    3: {
        "AUTH_ID",
        "LOGIN_FAIL",
        "REMOTE",
        "ACCOUNT_PERM",
        "DEFAULT",
        "PRIV_SEP",
        "AUDIT_ENABLE",
        "AUDIT_PROTECT",
        "TERMINAL",
        "INTEGRITY_TRANSFER",
        "INTEGRITY_STORE",
        "CONF_TRANSFER",
        "CONF_STORE",
    },
    4: {
        "AUTH_ID",
        "LOGIN_FAIL",
        "REMOTE",
        "ACCOUNT_PERM",
        "DEFAULT",
        "PRIV_SEP",
        "AUDIT_ENABLE",
        "AUDIT_PROTECT",
        "TERMINAL",
        "INTEGRITY_TRANSFER",
        "INTEGRITY_STORE",
        "CONF_TRANSFER",
        "CONF_STORE",
    },
}

# 网络设备不具备“安装组件/关闭多余服务/异地实时备份”等能力，沿用指导书的不适用判定。
NA_KEYS: dict[int, set[str]] = {
    2: {"MIN_INSTALL", "CLOSE_SERVICES", "BACKUP_OFFSITE"},
    3: {"MIN_INSTALL", "CLOSE_SERVICES", "BACKUP_OFFSITE"},
    4: {"MIN_INSTALL", "CLOSE_SERVICES", "BACKUP_OFFSITE"},
}

POLICY: dict[str, tuple[str, bool]] = {
    "AUTH_ID": ("mixed_partial", False),
    "LOGIN_FAIL": ("mixed_partial", False),
    "REMOTE": ("binary", True),
    "ACCOUNT_PERM": ("mixed_partial", False),
    "DEFAULT": ("binary", True),
    "PRIV_SEP": ("mixed_partial", False),
    "AUDIT_ENABLE": ("mixed_partial", False),
    "AUDIT_PROTECT": ("mixed_partial", False),
    "TERMINAL": ("binary", True),
    "INTEGRITY_TRANSFER": ("binary", True),
    "INTEGRITY_STORE": ("binary", True),
    "CONF_TRANSFER": ("binary", True),
    "CONF_STORE": ("binary", True),
}

CRITICAL_KEYS = {"REMOTE", "TWO_FACTOR"}
OPTIONAL_KEYS = {"INTRUSION_DETECT"}

MANUAL_POINTS: dict[str, list[dict[str, Any]]] = {
    "AUTH_ID": [
        {"point": 1, "reason": "登录过程是否进行身份鉴别、口令是否定期更换需现场测试或访谈，不能仅凭配置回显定论"}
    ],
    "REMOTE": [
        {"point": 1, "reason": "是否实际通过远程方式管理设备需访谈确认；若仅本地 console 管理应判定为不适用"}
    ],
    "ACCOUNT_PERM": [
        {"point": 1, "reason": "账户作用是否与实际使用人员一一对应需结合访谈确认"}
    ],
    "DEFAULT": [
        {"point": 2, "reason": "默认口令是否已修改无法从密文回显确认，需登录测试"}
    ],
    "PRIV_SEP": [
        {"point": 1, "reason": "管理用户角色划分需访谈确认"},
        {"point": 3, "reason": "是否按最小权限原则分配权限需结合访谈确认"},
    ],
    "AUDIT_ENABLE": [
        {"point": 2, "reason": "审计范围是否覆盖每个用户需结合设备日志与用户清单确认"}
    ],
    "AUDIT_PROTECT": [
        {"point": 1, "reason": "审计记录保护措施是否有效需现场核查"}
    ],
}

# ZTE 指导书对第九条口令复杂度只给出访谈/测试方法，没有可采信的命令回显。
VENDOR_MANUAL_EXTRA: dict[str, dict[int, list[dict[str, Any]]]] = {
    "zte": {
        1: [
            {
                "point": 4,
                "reason": "ZTE 指导书未提供口令复杂度命令，需按访谈或口令测试结果人工判定",
            }
        ]
    }
}
VENDOR_SKIP_POINTS: dict[str, set[tuple[str, int]]] = {
    "zte": {("AUTH_ID", 4)}
}

HIGH_RISK_KEYS: dict[str, list[str]] = {
    "HR-01": ["AUTH_ID"],
    "HR-02": ["REMOTE"],
    "HR-03": ["TWO_FACTOR"],
    "HR-04": ["DEFAULT"],
    "HR-05": ["ACCOUNT_PERM", "PRIV_SEP", "ACCESS_POLICY", "ACCESS_GRANULARITY"],
    "HR-06": ["CLOSE_SERVICES"],
    "HR-07": ["VULN"],
    "HR-08": ["INPUT"],
    "HR-09": ["MALWARE"],
    "HR-10": ["CONF_TRANSFER"],
    "HR-11": ["CONF_STORE"],
    "HR-12": ["BACKUP_LOCAL"],
    "HR-13": ["HOT_REDUNDANCY"],
    "HR-14": ["BACKUP_OFFSITE"],
    "HR-15": ["RESIDUAL_CLEAR"],
    "HR-16": ["PERSONAL_COLLECT"],
}

NEUTRAL_ACTIONS = {
    "AUTH_ID": "建议为每个管理账户设置唯一用户名和满足复杂度要求的口令，并启用口令有效期与登录失败处理策略。",
    "LOGIN_FAIL": "建议启用登录失败锁定、登录超时自动退出等登录失败处理措施。",
    "REMOTE": "建议仅启用 SSH/HTTPS 等加密远程管理方式，关闭 Telnet/HTTP 明文管理。",
    "TWO_FACTOR": "建议对重要管理操作采用双因素鉴别，不能仅依赖口令认证。",
    "ACCOUNT_PERM": "建议按岗位分配账户和最小权限，删除匿名或共享账户。",
    "DEFAULT": "建议重命名或删除默认账户，并修改默认口令。",
    "EXTRA_ACCOUNT": "建议删除或禁用多余、过期账户，并定期核查账户清单。",
    "PRIV_SEP": "建议划分系统管理员、安全管理员和审计管理员等角色，实现权限分离。",
    "ACCESS_POLICY": "建议制定并落实访问控制策略，按默认拒绝原则授权。",
    "ACCESS_GRANULARITY": "建议按最小权限细化访问控制粒度，避免过宽授权。",
    "SECURITY_MARK": "建议对重要数据设置安全标记，并基于标记实施访问控制。",
    "AUDIT_ENABLE": "建议启用安全审计功能，确保审计覆盖每个用户和重要安全事件。",
    "AUDIT_CONTENT": "建议审计记录覆盖日期时间、用户、事件类型、结果等必要内容。",
    "AUDIT_PROTECT": "建议将审计记录备份至日志服务器，并限制审计记录访问。",
    "AUDIT_PROCESS": "建议对审计记录进行保护，避免未预期的删除、修改或覆盖。",
    "TERMINAL": "建议通过 ACL 或接入方式限制管理终端地址范围。",
    "INPUT": "建议对输入数据进行有效性校验，避免输入验证缺陷被利用。",
    "VULN": "建议及时修补已知漏洞，并关闭不必要的服务与端口。",
    "INTRUSION_DETECT": "建议部署入侵检测或防御能力，并在发生严重入侵事件时提供报警。",
    "MALWARE": "建议部署恶意代码检测与防范措施，并及时更新特征库。",
    "TRUST": "建议基于可信根对引导程序、系统程序和重要配置进行可信验证。",
    "INTEGRITY_TRANSFER": "建议使用 SSH/HTTPS 等加密协议传输管理数据，保证传输完整性。",
    "INTEGRITY_STORE": "建议账户口令以密文形式存储，保证存储完整性。",
    "NON_REPUDIATION": "建议通过安全审计与数字签名等手段保证重要操作不可否认。",
    "CONF_TRANSFER": "建议使用 SSH/HTTPS 等加密协议传输管理数据。",
    "CONF_STORE": "建议账户口令以密文形式存储。",
    "BACKUP_LOCAL": "建议定期备份重要配置与数据，并对备份文件采取保护措施。",
    "HOT_REDUNDANCY": "建议对关键设备或链路提供热冗余，避免单点故障影响业务。",
    "DR_CENTER": "建议建立异地灾难备份中心，保证重要数据可在灾难后恢复。",
    "RESIDUAL": "建议在设备退役或介质复用前彻底清除剩余信息。",
    "RESIDUAL_STORAGE": "建议对存储介质中的临时文件进行清除或安全删除。",
    "RESIDUAL_CLEAR": "建议在设备退役或介质复用前彻底清除剩余信息。",
    "PERSONAL_COLLECT": "建议仅采集业务必需的个人信息，并取得授权后处理。",
    "PERSONAL_USE": "建议限制个人信息访问范围，防止未授权访问或披露。",
}

BLOCK_NAMES: dict[str, list[str]] = {
    "h3c": [
        "H3C 账户与权限配置",
        "H3C 口令控制策略",
        "H3C 远程管理加密",
        "H3C 安全审计",
        "H3C 管理终端限制",
        "H3C 口令密文存储",
    ],
    "huawei": [
        "HUAWEI 账户与权限配置",
        "HUAWEI 口令与登录控制",
        "HUAWEI 远程管理加密",
        "HUAWEI 安全审计",
        "HUAWEI 管理终端限制",
        "HUAWEI 口令密文存储",
    ],
    "cisco": [
        "Cisco 账户与权限配置",
        "Cisco 口令与登录控制",
        "Cisco 远程管理加密",
        "Cisco 安全审计",
        "Cisco 管理终端限制",
        "Cisco 口令密文存储",
    ],
    "zte": [
        "ZTE 账户与权限配置",
        "ZTE 登录控制",
        "ZTE 远程管理加密",
        "ZTE 安全审计",
        "ZTE 管理终端限制",
        "ZTE 口令密文存储",
    ],
}

VENDOR_META = {
    "h3c": {
        "name": "H3C",
        "vendor": "H3C",
        "aliases": ["h3c", "新华三", "comware"],
        "normalize": "h3c_config",
    },
    "huawei": {
        "name": "HUAWEI",
        "vendor": "HUAWEI",
        "aliases": ["huawei", "华为", "vrp"],
        "normalize": "huawei_config",
    },
    "cisco": {
        "name": "Cisco",
        "vendor": "Cisco",
        "aliases": ["cisco", "思科", "ios"],
        "normalize": "cisco_config",
    },
    "zte": {
        "name": "中兴ZTE",
        "vendor": "中兴ZTE",
        "aliases": ["zte", "中兴", "中兴通讯"],
        "normalize": "zte_config",
    },
}

# 尚无厂商指导书的安全设备先提供人工核查模板：保留设备识别与整改链路，
# 不凭空编写采集命令，取得厂商资料后再补采集适配器。
SECURITY_ADAPTERS: dict[str, dict[str, Any]] = {
    "firewall": {
        "name": "防火墙",
        "vendor": "防火墙",
        "aliases": ["firewall", "fw", "ngfw", "下一代防火墙"],
    },
    "waf": {
        "name": "WAF",
        "vendor": "WAF",
        "aliases": ["web应用防火墙", "web 应用防火墙"],
    },
    "ids_ips": {
        "name": "IDS/IPS",
        "vendor": "IDS/IPS",
        "aliases": ["ids", "ips", "idps", "入侵检测", "入侵防御"],
    },
    "vpn": {
        "name": "VPN",
        "vendor": "VPN",
        "aliases": ["ssl vpn", "ipsec vpn", "虚拟专用网"],
    },
    "bastion": {
        "name": "堡垒机",
        "vendor": "堡垒机",
        "aliases": ["bastion", "运维审计", "跳板机", "jump server"],
    },
    "load_balancer": {
        "name": "负载均衡",
        "vendor": "负载均衡",
        "aliases": ["load balancer", "lb", "adc"],
    },
    "gap": {
        "name": "网闸",
        "vendor": "网闸",
        "aliases": ["隔离网闸", "安全隔离与信息交换", "gap"],
    },
}

VENDOR_BLOCKS: dict[str, list[dict[str, Any]]] = {
    "h3c": [
        {
            "title": "H3C 账户与权限配置",
            "section": "身份鉴别/访问控制",
            "block_index": 1,
            "pattern": r"^\s*display\s+(?:current-configuration|local-users?|users?)\s*$",
            "commands": [
                ("查看运行配置", "display current-configuration"),
                ("查看本地用户", "display local-user"),
            ],
            "binds": [
                ("AUTH_ID", [2, 3]),
                ("ACCOUNT_PERM", [2]),
                ("DEFAULT", [1]),
                ("PRIV_SEP", [2]),
                ("LOGIN_FAIL", [3]),
            ],
        },
        {
            "title": "H3C 口令控制策略",
            "section": "身份鉴别",
            "block_index": 2,
            "pattern": r"^\s*display\s+password-control\s*$",
            "commands": [("查看全局口令控制策略", "display password-control")],
            "binds": [("AUTH_ID", [4]), ("LOGIN_FAIL", [1, 2])],
        },
        {
            "title": "H3C 远程管理加密",
            "section": "身份鉴别/数据保密性",
            "block_index": 3,
            "pattern": (
                r"^\s*display\s+(?:ssh\s+server\s+status|telnet\s+server\s+status|"
                r"ip\s+https|ip\s+http)\s*$"
            ),
            "commands": [
                ("查看 SSH 服务状态", "display ssh server status"),
                ("查看 Telnet 服务状态", "display telnet server status"),
                ("查看 HTTPS 服务状态", "display ip https"),
                ("查看 HTTP 服务状态", "display ip http"),
            ],
            "binds": [
                ("REMOTE", [2]),
                ("INTEGRITY_TRANSFER", [1]),
                ("CONF_TRANSFER", [1]),
            ],
        },
        {
            "title": "H3C 安全审计",
            "section": "安全审计",
            "block_index": 4,
            "pattern": r"^\s*display\s+(?:info-center|logbuffer)\s*$",
            "commands": [
                ("查看信息中心状态", "display info-center"),
                ("查看日志缓冲区", "display logbuffer"),
            ],
            "binds": [("AUDIT_ENABLE", [1, 3]), ("AUDIT_PROTECT", [2])],
        },
        {
            "title": "H3C 管理终端限制",
            "section": "访问控制",
            "block_index": 5,
            "pattern": r"^\s*display\s+acl(?:\s+all)?\s*$|^\s*display\s+current-configuration\s*\|\s*include\s+acl\b",
            "commands": [
                ("查看 ACL 配置", "display acl all"),
                ("查看含 ACL 的配置行", "display current-configuration | include acl"),
            ],
            "binds": [("TERMINAL", [1])],
        },
        {
            "title": "H3C 口令密文存储",
            "section": "数据保密性",
            "block_index": 6,
            "pattern": r"^\s*display\s+current-configuration\s*\|\s*include\s+password\b",
            "commands": [
                ("查看含 password 的配置行", "display current-configuration | include password"),
            ],
            "binds": [("INTEGRITY_STORE", [1]), ("CONF_STORE", [1])],
        },
    ],
    "huawei": [
        {
            "title": "HUAWEI 账户与权限配置",
            "section": "身份鉴别/访问控制",
            "block_index": 1,
            "pattern": r"^\s*display\s+(?:current-configuration|local-users?|users?)\s*$",
            "commands": [
                ("查看运行配置", "display current-configuration"),
                ("查看在线用户", "display users"),
            ],
            "binds": [
                ("AUTH_ID", [2, 3]),
                ("ACCOUNT_PERM", [2]),
                ("DEFAULT", [1]),
                ("PRIV_SEP", [2]),
                ("LOGIN_FAIL", [3]),
            ],
        },
        {
            "title": "HUAWEI 口令与登录控制",
            "section": "身份鉴别",
            "block_index": 2,
            "pattern": (
                r"^\s*display\s+current-configuration\s*\|\s*include\s+"
                r"(?:password|aaa|user-interface)\b"
            ),
            "commands": [
                (
                    "查看口令与 AAA 配置",
                    "display current-configuration | include password",
                ),
                (
                    "查看登录失败处理配置",
                    "display current-configuration | include aaa",
                ),
                (
                    "查看管理终端配置",
                    "display current-configuration | include user-interface",
                ),
            ],
            "binds": [("AUTH_ID", [4]), ("LOGIN_FAIL", [1, 2])],
        },
        {
            "title": "HUAWEI 远程管理加密",
            "section": "身份鉴别/数据保密性",
            "block_index": 3,
            "pattern": (
                r"^\s*display\s+(?:ssh\s+server\s+status|telnet\s+server\s+status|"
                r"http\s+server\s+status|http\s+secure-server\s+status)\s*$"
            ),
            "commands": [
                ("查看 SSH 服务状态", "display ssh server status"),
                ("查看 Telnet 服务状态", "display telnet server status"),
                ("查看 HTTP 服务状态", "display http server status"),
                ("查看 HTTPS 服务状态", "display http secure-server status"),
            ],
            "binds": [
                ("REMOTE", [2]),
                ("INTEGRITY_TRANSFER", [1]),
                ("CONF_TRANSFER", [1]),
            ],
        },
        {
            "title": "HUAWEI 安全审计",
            "section": "安全审计",
            "block_index": 4,
            "pattern": r"^\s*display\s+(?:info-center|logbuffer)\s*$",
            "commands": [
                ("查看信息中心状态", "display info-center"),
                ("查看日志缓冲区", "display logbuffer"),
            ],
            "binds": [("AUDIT_ENABLE", [1, 3]), ("AUDIT_PROTECT", [2])],
        },
        {
            "title": "HUAWEI 管理终端限制",
            "section": "访问控制",
            "block_index": 5,
            "pattern": r"^\s*display\s+acl(?:\s+all)?\s*$|^\s*display\s+current-configuration\s*\|\s*include\s+acl\b",
            "commands": [
                ("查看 ACL 配置", "display acl all"),
                ("查看含 ACL 的配置行", "display current-configuration | include acl"),
            ],
            "binds": [("TERMINAL", [1])],
        },
        {
            "title": "HUAWEI 口令密文存储",
            "section": "数据保密性",
            "block_index": 6,
            "pattern": r"^\s*display\s+current-configuration\s*\|\s*include\s+password\b",
            "commands": [
                ("查看含 password 的配置行", "display current-configuration | include password"),
            ],
            "binds": [("INTEGRITY_STORE", [1]), ("CONF_STORE", [1])],
        },
    ],
    "cisco": [
        {
            "title": "Cisco 账户与权限配置",
            "section": "身份鉴别/访问控制",
            "block_index": 1,
            "pattern": r"^\s*show\s+(?:running-config|running-config\s*\|\s*include\s+username)\s*$",
            "commands": [
                ("查看运行配置", "show running-config"),
                ("查看用户配置", "show running-config | include username"),
            ],
            "binds": [
                ("AUTH_ID", [2, 3]),
                ("ACCOUNT_PERM", [2]),
                ("DEFAULT", [1]),
                ("PRIV_SEP", [2]),
                ("LOGIN_FAIL", [3]),
            ],
        },
        {
            "title": "Cisco 口令与登录控制",
            "section": "身份鉴别",
            "block_index": 2,
            "pattern": (
                r"^\s*show\s+(?:running-config\s*\|\s*include\s+"
                r"(?:password|login|exec-timeout)|passwords\s+configuration)\s*$"
            ),
            "commands": [
                (
                    "查看口令与登录控制配置",
                    "show running-config | include password",
                ),
                (
                    "查看口令策略",
                    "show passwords configuration",
                ),
            ],
            "binds": [("AUTH_ID", [4]), ("LOGIN_FAIL", [1, 2])],
        },
        {
            "title": "Cisco 远程管理加密",
            "section": "身份鉴别/数据保密性",
            "block_index": 3,
            "pattern": (
                r"^\s*show\s+(?:ip\s+ssh|ip\s+http\s+server\s+status|"
                r"ip\s+http\s+secure-server\s+status|running-config\s*\|\s*include\s+transport)\s*$"
            ),
            "commands": [
                ("查看 SSH 状态", "show ip ssh"),
                ("查看 HTTP 状态", "show ip http server status"),
                ("查看 HTTPS 状态", "show ip http secure-server status"),
                (
                    "查看 VTY 传输协议",
                    "show running-config | include transport",
                ),
            ],
            "binds": [
                ("REMOTE", [2]),
                ("INTEGRITY_TRANSFER", [1]),
                ("CONF_TRANSFER", [1]),
            ],
        },
        {
            "title": "Cisco 安全审计",
            "section": "安全审计",
            "block_index": 4,
            "pattern": r"^\s*show\s+(?:logging|running-config\s*\|\s*include\s+logging)\s*$",
            "commands": [
                ("查看日志配置", "show running-config | include logging"),
                ("查看日志状态", "show logging"),
            ],
            "binds": [("AUDIT_ENABLE", [1, 3]), ("AUDIT_PROTECT", [2])],
        },
        {
            "title": "Cisco 管理终端限制",
            "section": "访问控制",
            "block_index": 5,
            "pattern": (
                r"^\s*show\s+running-config\s*\|\s*include\s+"
                r"(?:access-list|access-class|ip\s+access-list)\s*$"
            ),
            "commands": [
                (
                    "查看 ACL 配置",
                    "show running-config | include access-list|access-class",
                ),
            ],
            "binds": [("TERMINAL", [1])],
        },
        {
            "title": "Cisco 口令密文存储",
            "section": "数据保密性",
            "block_index": 6,
            "pattern": r"^\s*show\s+running-config\s*\|\s*include\s+username\s*$",
            "commands": [
                ("查看用户口令配置", "show running-config | include username"),
            ],
            "binds": [("INTEGRITY_STORE", [1]), ("CONF_STORE", [1])],
        },
    ],
    "zte": [
        {
            "title": "ZTE 账户与权限配置",
            "section": "身份鉴别/访问控制",
            "block_index": 1,
            "pattern": r"^\s*show\s+(?:running-config|user)\s*$",
            "commands": [("查看账户与权限配置", "show running-config")],
            "binds": [
                ("AUTH_ID", [2, 3]),
                ("ACCOUNT_PERM", [2]),
                ("DEFAULT", [1]),
                ("PRIV_SEP", [2]),
            ],
        },
        {
            "title": "ZTE 登录控制",
            "section": "身份鉴别",
            "block_index": 2,
            "pattern": r"^\s*show\s+running-config\s*$",
            "commands": [("查看登录控制配置", "show running-config")],
            "binds": [("LOGIN_FAIL", [1, 2, 3])],
        },
        {
            "title": "ZTE 远程管理加密",
            "section": "身份鉴别/数据保密性",
            "block_index": 3,
            "pattern": r"^\s*show\s+running-config\s*$",
            "commands": [("查看远程管理配置", "show running-config")],
            "binds": [
                ("REMOTE", [2]),
                ("INTEGRITY_TRANSFER", [1]),
                ("CONF_TRANSFER", [1]),
            ],
        },
        {
            "title": "ZTE 安全审计",
            "section": "安全审计",
            "block_index": 4,
            "pattern": r"^\s*show\s+(?:running-config|logfile)\s*$",
            "commands": [
                ("查看审计配置", "show running-config"),
                ("查看日志", "show logfile"),
            ],
            "binds": [("AUDIT_ENABLE", [1, 3]), ("AUDIT_PROTECT", [2])],
        },
        {
            "title": "ZTE 管理终端限制",
            "section": "访问控制",
            "block_index": 5,
            "pattern": r"^\s*show\s+running-config\s*$",
            "commands": [("查看管理终端配置", "show running-config")],
            "binds": [("TERMINAL", [1])],
        },
        {
            "title": "ZTE 口令密文存储",
            "section": "数据保密性",
            "block_index": 6,
            "pattern": r"^\s*show\s+running-config\s*$",
            "commands": [("查看口令存储配置", "show running-config")],
            "binds": [("INTEGRITY_STORE", [1]), ("CONF_STORE", [1])],
        },
    ],
}


def _audit_facts(vendor: str) -> tuple[str, str, str]:
    suffix = {
        "h3c": ("info_center", "logbuffer", "loghost"),
    }.get(vendor, ("enabled", "buffer", "forwarded"))
    return tuple(f"fact:{vendor}.audit.{name}=true" for name in suffix)  # type: ignore[return-value]


def _rule_specs(vendor: str) -> list[dict[str, Any]]:
    prefix = f"fact:{vendor}."
    enabled = f"{prefix}password_control.enabled=true"
    length = f"{prefix}password_control.length="
    composition = f"{prefix}password_control.composition_types="
    aging = f"{prefix}password_control.aging_days="
    login_attempt = f"{prefix}password_control.login_attempt="
    lock_minutes = f"{prefix}password_control.lock_minutes="
    idle = f"{prefix}timeout.idle_minutes="
    audit_enabled, audit_buffer, audit_forwarded = _audit_facts(vendor)

    auth4: list[dict[str, Any]] = [
        {"contains": enabled},
        {"gt": {"prefix": length, "value": 7}},
        {"gt": {"prefix": composition, "value": 2}},
    ]
    if vendor in {"h3c", "cisco"}:
        auth4.append({"lt": {"prefix": aging, "value": 91}})

    specs: list[dict[str, Any]] = [
        {
            "key": "AUTH_ID",
            "point": 2,
            "block": "accounts",
            "expect": {"contains": f"{prefix}users.unique=true"},
            "pass_reason": "用户列表中的用户名唯一，未发现相同用户名账户。",
            "fail_reason": "用户列表存在相同用户名，身份标识不满足唯一性。",
        },
        {
            "key": "AUTH_ID",
            "point": 3,
            "block": "accounts",
            "expect": {"contains": f"{prefix}users.empty_password=none"},
            "pass_reason": "本地用户均配置了口令，未发现空口令账户。",
            "fail_reason": "存在未配置口令或空口令的本地用户。",
        },
        {
            "key": "AUTH_ID",
            "point": 4,
            "block": "policy",
            "expect": {"all": auth4},
            "pass_reason": "已启用的口令策略满足长度、组成复杂度及有效期要求。",
            "fail_reason": "未启用的口令策略，或长度、组成复杂度、有效期至少一项不满足要求。",
        },
        {
            "key": "LOGIN_FAIL",
            "point": 1,
            "block": "policy",
            "expect": (
                {"gt": {"prefix": login_attempt, "value": 0}}
                if vendor == "zte"
                else {
                    "all": [
                        {"contains": enabled},
                        {"gt": {"prefix": login_attempt, "value": 0}},
                    ]
                }
            ),
            "pass_reason": "已启用登录失败次数限制。",
            "fail_reason": "未启用登录失败次数限制。",
        },
        {
            "key": "LOGIN_FAIL",
            "point": 2,
            "block": "policy",
            "expect": {
                "all": [
                    {"lt": {"prefix": login_attempt, "value": 11}},
                    {"gt": {"prefix": lock_minutes, "value": 4}},
                ]
            },
            "pass_reason": "登录失败次数阈值不超过 10 次，且锁定时间不少于 5 分钟。",
            "fail_reason": "登录失败次数阈值过大或未配置足够的锁定时间。",
        },
        {
            "key": "LOGIN_FAIL",
            "point": 3,
            "block": "accounts",
            "expect": {"lt": {"prefix": idle, "value": 31}},
            "pass_reason": "管理终端空闲超时时间不超过 30 分钟。",
            "fail_reason": "未配置空闲超时或超时时间超过 30 分钟。",
        },
        {
            "key": "REMOTE",
            "point": 2,
            "block": "remote",
            "expect": {"contains": f"{prefix}remote.encrypted=true"},
            "pass_reason": "远程管理使用 SSH/HTTPS 加密，未启用 Telnet/HTTP 明文管理。",
            "fail_reason": "远程管理仍启用 Telnet/HTTP 等明文协议，鉴别信息可能被窃听。",
        },
        {
            "key": "ACCOUNT_PERM",
            "point": 2,
            "block": "accounts",
            "expect": {"contains": f"{prefix}users.anonymous=none"},
            "pass_reason": "未发现匿名或公共账户。",
            "fail_reason": "存在匿名、guest 或 public 等可登录账户。",
        },
        {
            "key": "DEFAULT",
            "point": 1,
            "block": "accounts",
            "expect": {"contains": f"{prefix}users.default_account=none"},
            "pass_reason": "未发现使用默认名称的可登录账户。",
            "fail_reason": "存在 admin、厂商名等默认名称账户且未被禁用或重命名。",
        },
        {
            "key": "PRIV_SEP",
            "point": 2,
            "block": "accounts",
            "expect": {"contains": f"{prefix}roles.privilege_distinct=true"},
            "pass_reason": "不同管理用户配置了不同角色或权限级别。",
            "fail_reason": "管理用户角色或权限级别未区分，存在权限过度集中。",
        },
        {
            "key": "AUDIT_ENABLE",
            "point": 1,
            "block": "audit",
            "expect": {"contains": audit_enabled},
            "pass_reason": "安全审计功能已启用。",
            "fail_reason": "安全审计功能未启用。",
        },
        {
            "key": "AUDIT_ENABLE",
            "point": 3,
            "block": "audit",
            "expect": {
                "all": [
                    {"contains": audit_enabled},
                    {"contains": audit_buffer},
                ]
            },
            "pass_reason": "审计功能和日志缓冲区均已启用，可记录重要用户行为和安全事件。",
            "fail_reason": "日志缓冲区未启用，无法确认重要用户行为和安全事件被审计。",
        },
        {
            "key": "AUDIT_PROTECT",
            "point": 2,
            "block": "audit",
            "expect": {"contains": audit_forwarded},
            "pass_reason": "已配置日志主机，审计记录可定期备份到外部系统。",
            "fail_reason": "未配置日志主机，审计记录缺少外部备份。",
        },
        {
            "key": "TERMINAL",
            "point": 1,
            "block": "acl",
            "expect": {"contains": f"{prefix}acl.vty_restricted=true"},
            "pass_reason": "管理终端已通过 ACL 限制接入范围。",
            "fail_reason": "未发现管理终端接入范围限制配置。",
        },
        {
            "key": "INTEGRITY_TRANSFER",
            "point": 1,
            "block": "remote",
            "expect": {"contains": f"{prefix}remote.encrypted=true"},
            "pass_reason": "数据传输采用 SSH/HTTPS 加密通道。",
            "fail_reason": "数据传输使用明文协议，完整性无法保证。",
        },
        {
            "key": "INTEGRITY_STORE",
            "point": 1,
            "block": "secret",
            "expect": {"contains": f"{prefix}secret_storage.cipher=true"},
            "pass_reason": "口令以密文形式存储。",
            "fail_reason": "口令以明文形式存储，完整性无法保证。",
        },
        {
            "key": "CONF_TRANSFER",
            "point": 1,
            "block": "remote",
            "expect": {"contains": f"{prefix}remote.encrypted=true"},
            "pass_reason": "数据传输采用 SSH/HTTPS 加密通道。",
            "fail_reason": "数据传输使用明文协议，保密性无法保证。",
        },
        {
            "key": "CONF_STORE",
            "point": 1,
            "block": "secret",
            "expect": {"contains": f"{prefix}secret_storage.cipher=true"},
            "pass_reason": "口令以密文形式存储。",
            "fail_reason": "口令以明文形式存储，保密性无法保证。",
        },
    ]
    return specs


def _dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )


def _all_records(guide: Path) -> list[dict]:
    return json.loads(guide.read_text(encoding="utf-8"))["records"]


def _records(records: list[dict], level: int, vendor: str) -> list[dict]:
    selected = [
        record
        for record in records
        if int(record["level"]) == level and record["object"] == vendor
    ]
    if level == 3 and vendor == "H3C":
        return sorted(selected, key=lambda record: int(record["seq"]))
    return sorted(selected, key=lambda record: int(record.get("excel_row") or 0))


def _unit_no(record: dict) -> int:
    match = re.search(r"(\d+)$", str(record["unit_no"]))
    if not match:
        raise ValueError(f"无法解析单元编号：{record['unit_no']}")
    return int(match.group(1))


def _key_for(level: int, record: dict) -> str:
    unit = _unit_no(record)
    try:
        return LEVEL_KEYS[level][unit]
    except KeyError as exc:
        raise ValueError(f"L{level} 单元 {record['unit_no']} 没有登记规则键") from exc


def _seq_by_key(guide_records: list[dict]) -> dict[int, dict[str, int]]:
    mapping: dict[int, dict[str, int]] = {}
    for level in LEVELS:
        mapping[level] = {}
        for record in _records(guide_records, level, "H3C"):
            mapping[level][_key_for(level, record)] = int(record["seq"])
    return mapping


def _split_guide(text: str) -> tuple[str, str]:
    body = text.strip()
    criteria = ""
    match = re.search(r"\n\s*判定[：:]\s*", body)
    if match:
        criteria = body[match.end() :]
        body = body[: match.start()]
    criteria = re.split(r"\n\s*版本差异", criteria)[0].strip()
    return body.strip(), criteria or "依据指导书判定标准执行。"


def _items(guide_records: list[dict], level: int) -> list[dict]:
    items: list[dict] = []
    for record in sorted(
        _records(guide_records, level, "H3C"), key=lambda entry: int(entry["seq"])
    ):
        key = _key_for(level, record)
        seq = int(record["seq"])
        content, criteria = _split_guide(str(record["operation_guide"]))
        if key in NA_KEYS[level]:
            mode, policy, binary = "na", "na", False
        elif key in AUTO_KEYS[level]:
            policy, binary = POLICY[key]
            mode = "auto"
        else:
            mode, policy, binary = "manual", "manual", False
        item = {
            "item_id": str(record["unit_no"]),
            "level": level,
            "seq": seq,
            "unit_no": _unit_no(record),
            "控制点": str(record["control_point"]).strip(),
            "控制项": str(record["item_text"]).strip(),
            "重要程度": "关键" if key in CRITICAL_KEYS else "重要",
            "检查内容": content,
            "判断标准": criteria,
            "policy": policy,
            "mode": mode,
            "binary": binary,
        }
        if key in OPTIONAL_KEYS:
            item["optional_clause"] = True
        if key in MANUAL_POINTS:
            item["manual_points"] = MANUAL_POINTS[key]
        items.append(item)
    return items


def _checks(vendor: str, seq_by_key: dict[int, dict[str, int]]) -> list[dict]:
    meta = VENDOR_META[vendor]
    allowed = {
        (spec["key"], spec["point"])
        for spec in _rule_specs(vendor)
        if (spec["key"], spec["point"]) not in VENDOR_SKIP_POINTS.get(vendor, set())
    }
    checks: list[dict] = []
    for block in VENDOR_BLOCKS[vendor]:
        binds: list[dict] = []
        for key, points in block["binds"]:
            usable = [point for point in points if (key, point) in allowed]
            if not usable:
                continue
            for level in LEVELS:
                seq = seq_by_key[level].get(key)
                if seq is None or key not in AUTO_KEYS[level]:
                    continue
                binds.append({"item": seq, "level": level, "points": usable})
        checks.append(
            {
                "title": block["title"],
                "section": "",
                "block_index": block["block_index"],
                "kind": "judge",
                "normalize": meta["normalize"],
                "binds": binds,
                "session": [{"kind": "network", "pattern": block["pattern"]}],
            }
        )
    return checks


def _rules(vendor: str, seq_by_key: dict[int, dict[str, int]]) -> dict[int, list[dict]]:
    names = BLOCK_NAMES[vendor]
    skipped = VENDOR_SKIP_POINTS.get(vendor, set())
    by_level: dict[int, list[dict]] = {level: [] for level in LEVELS}
    specs = _rule_specs(vendor)
    for level in LEVELS:
        counter: dict[str, int] = {}
        for spec in specs:
            key = spec["key"]
            if (key, spec["point"]) in skipped:
                continue
            if key not in AUTO_KEYS[level]:
                continue
            seq = seq_by_key[level].get(key)
            if seq is None:
                continue
            if vendor == "zte" and key == "LOGIN_FAIL" and spec["block"] == "accounts":
                block_index = 2
            else:
                block_index = {"accounts": 1, "policy": 2, "remote": 3, "audit": 4, "acl": 5, "secret": 6}[
                    spec["block"]
                ]
            counter[key] = counter.get(key, 0) + 1
            by_level[level].append(
                {
                    "rule_id": f"{names[0].split()[0]}-L{level}-{key}-P{spec['point']:02d}-{counter[key]:02d}",
                    "level": level,
                    "item": seq,
                    "point": spec["point"],
                    "block": names[block_index - 1],
                    "expect": spec["expect"],
                    "pass_reason": spec["pass_reason"],
                    "fail_reason": spec["fail_reason"],
                }
            )
    return by_level


def _vendor_records(records: list[dict], vendor_name: str, level: int) -> list[dict]:
    selected = [
        record
        for record in records
        if int(record["level"]) == level and record["object"] == vendor_name
    ]
    return sorted(selected, key=lambda record: int(record.get("excel_row") or 0))


def _texts(records: list[dict], vendor_name: str, seq_by_key: dict[int, dict[str, int]]) -> dict:
    entries: list[dict] = []
    seen: set[str] = set()
    for level in LEVELS:
        for record in _vendor_records(records, vendor_name, level):
            control_item = str(record["item_text"]).strip()
            if control_item in seen:
                continue
            key = _key_for(level, record)
            seq = seq_by_key[level].get(key)
            if seq is None:
                continue
            seen.add(control_item)
            problem = str(record.get("problem") or "").strip()
            lines = [line.strip() for line in problem.splitlines() if line.strip()]
            entries.append(
                {
                    "seq": seq,
                    "control_point": str(record["control_point"]).strip(),
                    "control_item": control_item,
                    "issue_summary": lines[0] if lines else "配置不符合指导书要求。",
                    "issue_detail": "\n".join(lines[1:]) if len(lines) > 1 else "",
                    "hazard": str(record.get("harm") or "").strip(),
                    "remediation": str(record.get("remediation") or "").strip(),
                    "threat": str(record.get("threat") or "").strip(),
                    "inherent_risk": str(record.get("risk_value") or "中").strip(),
                }
            )
    return {"texts": entries}


def _adapter_remediation(
    records: list[dict], vendor_name: str, seq_by_key: dict[int, dict[str, int]]
) -> dict:
    priority = {"高": "高", "中": "中", "低": "低"}
    rules: list[dict] = []
    prefix = re.sub(r"\W+", "", vendor_name).upper()
    for level in LEVELS:
        for record in _vendor_records(records, vendor_name, level):
            action = str(record.get("remediation") or "").strip()
            if not action:
                continue
            key = _key_for(level, record)
            seq = seq_by_key[level].get(key)
            if seq is None:
                continue
            problem = "；".join(
                line.strip()
                for line in str(record.get("problem") or "").splitlines()
                if line.strip()
            )
            rules.append(
                {
                    "id": f"REM-{prefix}-L{level}-{seq:02d}",
                    "title": f"{record['control_point']}整改",
                    "applies_to": {"level": [level], "family": ["network"], "item_seqs": [seq]},
                    "priority": priority.get(str(record.get("risk_value") or ""), "中"),
                    "problem": problem or "配置不符合指导书要求。",
                    "cause": "设备安全基线未配置或配置未落到该设备。",
                    "action": action,
                    "clause": str(record["item_text"]).strip(),
                }
            )
    return {"version": "0.1.0", "status": "active", "rules": rules}


def _pack_remediation(
    seq_by_key: dict[int, dict[str, int]], levels: tuple[int, ...] = (3,)
) -> dict:
    rules: list[dict] = []
    for level in levels:
        for key, seq in sorted(seq_by_key[level].items(), key=lambda entry: entry[1]):
            action = NEUTRAL_ACTIONS.get(key)
            if not action:
                continue
            rules.append(
                {
                    "id": f"REM-NET-L{level}-{seq:02d}",
                    "title": f"{key} 整改",
                    "applies_to": {"level": [level], "family": ["network"], "item_seqs": [seq]},
                    "priority": "高" if key in CRITICAL_KEYS else "中",
                    "problem": "设备配置不符合指导书要求。",
                    "cause": "设备安全基线未配置或配置未落到该设备。",
                    "action": action,
                    "clause": key,
                }
            )
    return {"version": "0.1.0", "status": "active", "rules": rules}


def _high_risk(seq_by_key: dict[int, dict[str, int]]) -> list[dict]:
    records = yaml.safe_load((LINUX_PACK / "high_risk.yaml").read_text(encoding="utf-8"))
    for record in records:
        hr_id = record.get("hr_id")
        keys = HIGH_RISK_KEYS.get(hr_id, [])
        seqs: list[int] = []
        for level in LEVELS:
            for key in keys:
                seq = seq_by_key[level].get(key)
                if seq is not None and seq not in seqs:
                    seqs.append(seq)
        if keys:
            record["binds_items"] = sorted(seqs)
    return records


def _capture(vendor: str) -> dict:
    rules: list[dict] = []
    for block in VENDOR_BLOCKS[vendor]:
        for title, command in block["commands"]:
            rules.append(
                {
                    "section": block["title"],
                    "title": title,
                    "command": command,
                    "levels": list(LEVELS),
                    "families": ["network"],
                }
            )
    return {
        "asset_family": "network",
        "version": "0.1.0",
        "status": "active",
        "rules": rules,
    }


def _coverage(
    records: list[dict],
    vendor: str,
    vendor_name: str,
    level: int,
    seq_by_key: dict[int, dict[str, int]],
) -> str:
    names = BLOCK_NAMES[vendor]
    rules = _rules(vendor, seq_by_key)[level]
    manual = {item["seq"]: item for item in _items(records, level)}
    lines = [
        f"# {vendor_name} {level} 级网络设备规则域覆盖报告",
        "",
        "本报告由 `tools/build_network_pack.py` 从网络设备指导书自动生成。",
        "采集命令、判定规则与人工核查点只适用于本厂商，不能复制给其他厂商。",
        "",
        "| 项 | 控制点 | 模式 | 自动实施点 | 人工核查点 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for record in sorted(
        _records(records, level, "H3C"), key=lambda entry: int(entry["seq"])
    ):
        seq = int(record["seq"])
        item = manual[seq]
        auto_points = sorted(rule["point"] for rule in rules if rule["item"] == seq)
        manual_points = sorted(point["point"] for point in item.get("manual_points", []))
        lines.append(
            "| {seq} | {point} | {mode} | {auto} | {manual} |".format(
                seq=seq,
                point=str(record["control_point"]).strip(),
                mode=item["mode"],
                auto=",".join(map(str, auto_points)) or "—",
                manual=",".join(map(str, manual_points)) or "—",
            )
        )
    return "\n".join(lines) + "\n"


def build(guide: Path, out: Path) -> None:
    records = _all_records(guide)
    expected = {2: 23, 3: 34, 4: 31}
    for level, count in expected.items():
        actual = len(_records(records, level, "H3C"))
        if actual != count:
            raise SystemExit(f"H3C {level} 级记录应为 {count} 条，实际 {actual}")
    seq_by_key = _seq_by_key(records)

    _dump(
        out / "pack.yaml",
        {
            "name": "network_devices",
            "version": "0.2.0",
            "levels": list(LEVELS),
            "os_family": ["network"],
            "asset_types": ["网络设备", "安全设备"],
            "guides": ["二级-安全通用要求", "三级-安全通用要求", "四级-安全通用要求"],
            "items": {
                "level_2": "items_L2.yaml",
                "level_3": "items_L3.yaml",
                "level_4": "items_L4.yaml",
            },
            "adapters": {
                "h3c": "adapters/h3c",
                "huawei": "adapters/huawei",
                "cisco": "adapters/cisco",
                "zte": "adapters/zte",
                **{
                    key: f"adapters/{key}"
                    for key in SECURITY_ADAPTERS
                },
                "generic": "adapters/generic",
            },
            "default_adapter": "generic",
        },
    )
    for level in LEVELS:
        _dump(out / f"items_L{level}.yaml", _items(records, level))
    _dump(out / "remediation.yaml", _pack_remediation(seq_by_key))
    (out / "record.yaml").write_text(
        (LINUX_PACK / "record.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )

    adapter_keys = ["h3c", "huawei", "cisco", "zte"]
    for vendor in adapter_keys:
        meta = VENDOR_META[vendor]
        adapter = out / "adapters" / vendor
        vendor_name = meta["name"]
        adapter_meta = {
            "name": vendor_name,
            "vendor": meta["vendor"],
            "aliases": meta["aliases"],
            "levels": list(LEVELS),
            "asset_types": ["网络设备", "安全设备"],
            "checks_map": "checks_map.yaml",
            "rules_dir": "rules",
            "high_risk": "high_risk.yaml",
            "major": "major.yaml",
            "texts": "texts/library.yaml",
            "capture": "capture.yaml",
        }
        if vendor in VENDOR_MANUAL_EXTRA:
            adapter_meta["manual_points"] = VENDOR_MANUAL_EXTRA[vendor]
        _dump(adapter / "adapter.yaml", adapter_meta)
        _dump(adapter / "checks_map.yaml", {"checks": _checks(vendor, seq_by_key)})
        for level, rules in _rules(vendor, seq_by_key).items():
            _dump(adapter / "rules" / f"level{level}.yaml", {"rules": rules})
        _dump(adapter / "high_risk.yaml", _high_risk(seq_by_key))
        (adapter / "major.yaml").write_text(
            (LINUX_PACK / "major.yaml").read_text(encoding="utf-8"), encoding="utf-8"
        )
        _dump(adapter / "texts" / "library.yaml", _texts(records, vendor_name, seq_by_key))
        _dump(adapter / "capture.yaml", _capture(vendor))
        _dump(
            adapter / "remediation.yaml",
            _adapter_remediation(records, vendor_name, seq_by_key),
        )

    for key, meta in SECURITY_ADAPTERS.items():
        adapter = out / "adapters" / key
        _dump(
            adapter / "adapter.yaml",
            {
                "name": meta["name"],
                "vendor": meta["vendor"],
                "aliases": meta["aliases"],
                "levels": list(LEVELS),
                "asset_types": ["安全设备", "网络设备"],
                "manual_all": True,
            },
        )
        _dump(
            adapter / "remediation.yaml",
            _pack_remediation(seq_by_key, tuple(LEVELS)),
        )

    _dump(
        out / "adapters" / "generic" / "adapter.yaml",
        {
            "name": "通用安全设备",
            "vendor": "generic",
            "aliases": ["通用", "generic", "通用安全设备"],
            "levels": list(LEVELS),
            "asset_types": ["网络设备", "安全设备"],
            "manual_all": True,
        },
    )
    _dump(
        out / "adapters" / "generic" / "remediation.yaml",
        _pack_remediation(seq_by_key, tuple(LEVELS)),
    )

    _dump(
        out / "library.yaml",
        {
            "version": "0.2.0",
            "libraries": {
                "capture": {
                    "title": "数据采集命令库",
                    "status": "active",
                    "paths": [f"adapters/{vendor}/capture.yaml" for vendor in adapter_keys],
                },
                "record": {
                    "title": "记录表生成规则库",
                    "status": "active",
                    "path": "record.yaml",
                },
                "judge": {
                    "title": "记录表判定规则库",
                    "status": "active",
                    "paths": [
                        f"adapters/{vendor}/rules/level{level}.yaml"
                        for vendor in adapter_keys
                        for level in LEVELS
                    ],
                },
                "remediation": {
                    "title": "风险分析与整改建议库",
                    "status": "active",
                    "path": "remediation.yaml",
                },
                "high_risk": {
                    "title": "高风险判定规则库",
                    "status": "active",
                    "paths": [f"adapters/{vendor}/high_risk.yaml" for vendor in adapter_keys],
                },
                "major": {
                    "title": "重大风险隐患规则库",
                    "status": "active",
                    "paths": [f"adapters/{vendor}/major.yaml" for vendor in adapter_keys],
                },
            },
        },
    )

    reports = REPO_ROOT / "guides" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    for vendor in adapter_keys:
        for level in LEVELS:
            report = reports / f"network_{vendor}_L{level}.md"
            report.write_text(
                _coverage(
                    records,
                    vendor,
                    VENDOR_META[vendor]["name"],
                    level,
                    seq_by_key,
                ),
                encoding="utf-8",
            )

    security_lines = [
        "# 网络安全设备人工核查模板",
        "",
        "以下设备类型尚无厂商指导书，先建立人工核查模板：",
        "不提供采集命令，所有测评项按人工核查处理；取得厂商资料后再补充专用采集适配器。",
        "",
        "| 适配器 | 设备类型 | 可识别的资产厂商/类型 | 等级 |",
        "| --- | --- | --- | --- |",
    ]
    for key, meta in SECURITY_ADAPTERS.items():
        names = "、".join(
            dict.fromkeys([meta["name"], meta["vendor"], *meta["aliases"]])
        )
        security_lines.append(
            f"| {key} | {meta['name']} | {names} | {','.join(map(str, LEVELS))} |"
        )
    (reports / "network_security_devices.md").write_text(
        "\n".join(security_lines) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="生成网络设备规则域与多厂商适配器")
    parser.add_argument("--guide", default="guides/network.json")
    parser.add_argument("--out", default="packs/network_devices")
    args = parser.parse_args()
    build(Path(args.guide), Path(args.out))


if __name__ == "__main__":
    main()
