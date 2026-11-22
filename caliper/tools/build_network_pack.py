"""从网络设备指导书生成设备规则域与 H3C 三级适配器。

用法：
  .venv/bin/python tools/build_network_pack.py --guide guides/network.json --out packs/network_devices

生成结果只包含指导书原文可追溯的字段；判定规则与人工核查点集中在本文件的
SPEC 中维护，避免把不同厂商命令混在同一条规则里。
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

# 自动化模式、判定策略与人工核查点：具体测评项仍以指导书原文为准。
MANUAL_ITEMS = {4, 7, 9, 10, 11, 13, 15, 19, 20, 21, 22, 27, 29, 30, 31, 32, 33, 34}
NA_ITEMS = {16, 17, 28}
AUTO_POLICY: dict[int, tuple[str, bool]] = {
    1: ("mixed_partial", False),
    2: ("mixed_partial", False),
    3: ("binary", True),
    5: ("mixed_partial", False),
    6: ("binary", True),
    8: ("mixed_partial", False),
    12: ("mixed_partial", False),
    14: ("mixed_partial", False),
    18: ("binary", True),
    23: ("binary", True),
    24: ("binary", True),
    25: ("binary", True),
    26: ("binary", True),
}
MANUAL_POINTS: dict[int, list[dict[str, Any]]] = {
    1: [{"point": 1, "reason": "登录过程是否进行身份鉴别需现场测试，不能仅凭配置回显定论"}],
    3: [{"point": 1, "reason": "是否实际通过远程方式管理设备需访谈确认，若未启用远程管理应判定为不适用"}],
    5: [{"point": 1, "reason": "账户权限分配是否遵循最小权限需结合访谈确认"}],
    6: [{"point": 2, "reason": "默认口令是否已修改无法从密文回显确认，需登录测试"}],
    8: [
        {"point": 1, "reason": "管理用户角色划分与权限分离需访谈确认"},
        {"point": 3, "reason": "是否按最小权限原则分配权限需结合访谈确认"},
    ],
    12: [{"point": 2, "reason": "审计范围是否覆盖每个用户需结合设备日志与用户清单确认"}],
    14: [{"point": 1, "reason": "审计记录保护措施是否有效需现场核查"}],
}
CRITICAL_ITEMS = {3, 4}
OPTIONAL_ITEMS = {22}

# 每个采集块只列本厂商命令；规则只引用该块的归一化事实。
BLOCKS: list[dict[str, Any]] = [
    {
        "title": "H3C 账户与权限配置",
        "section": "身份鉴别/访问控制",
        "block_index": 1,
        "pattern": r"^\s*display\s+(?:current-configuration|local-users?)\s*$",
        "commands": [
            ("查看运行配置", "display current-configuration"),
            ("查看本地用户", "display local-user"),
        ],
        "binds": [
            (1, [2, 3]),
            (2, [3]),
            (5, [2]),
            (6, [1]),
            (8, [2]),
        ],
    },
    {
        "title": "H3C 口令控制策略",
        "section": "身份鉴别",
        "block_index": 2,
        "pattern": r"^\s*display\s+password-control\s*$",
        "commands": [("查看全局口令控制策略", "display password-control")],
        "binds": [(1, [4]), (2, [1, 2])],
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
        "binds": [(3, [2]), (23, [1]), (25, [1])],
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
        "binds": [(12, [1, 3]), (14, [2])],
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
        "binds": [(18, [1])],
    },
    {
        "title": "H3C 口令密文存储",
        "section": "数据保密性",
        "block_index": 6,
        "pattern": r"^\s*display\s+current-configuration\s*\|\s*include\s+password\b",
        "commands": [
            ("查看含 password 的配置行", "display current-configuration | include password"),
        ],
        "binds": [(24, [1]), (26, [1])],
    },
]

RULES: list[dict[str, Any]] = [
    {
        "item": 1,
        "point": 2,
        "block": "H3C 账户与权限配置",
        "expect": {"contains": "fact:h3c.users.unique=true"},
        "pass_reason": "用户列表中的用户名唯一，未发现相同用户名账户。",
        "fail_reason": "用户列表存在相同用户名，身份标识不满足唯一性。",
    },
    {
        "item": 1,
        "point": 3,
        "block": "H3C 账户与权限配置",
        "expect": {"contains": "fact:h3c.users.empty_password=none"},
        "pass_reason": "本地用户均配置了口令，未发现空口令账户。",
        "fail_reason": "存在未配置口令或空口令的本地用户。",
    },
    {
        "item": 5,
        "point": 2,
        "block": "H3C 账户与权限配置",
        "expect": {"contains": "fact:h3c.users.anonymous=none"},
        "pass_reason": "未发现匿名或公共账户。",
        "fail_reason": "存在匿名、guest 或 public 等可登录账户。",
    },
    {
        "item": 6,
        "point": 1,
        "block": "H3C 账户与权限配置",
        "expect": {"contains": "fact:h3c.users.default_account=none"},
        "pass_reason": "未发现使用默认名称的可登录账户。",
        "fail_reason": "存在 admin、h3c 等默认名称账户且未被禁用或重命名。",
    },
    {
        "item": 8,
        "point": 2,
        "block": "H3C 账户与权限配置",
        "expect": {"contains": "fact:h3c.roles.privilege_distinct=true"},
        "pass_reason": "不同管理用户配置了不同角色或权限级别。",
        "fail_reason": "管理用户角色或权限级别未区分，存在权限过度集中。",
    },
    {
        "item": 2,
        "point": 3,
        "block": "H3C 账户与权限配置",
        "expect": {"lt": {"prefix": "fact:h3c.timeout.idle_minutes=", "value": 31}},
        "pass_reason": "管理终端空闲超时时间不超过 30 分钟。",
        "fail_reason": "未配置空闲超时或超时时间超过 30 分钟。",
    },
    {
        "item": 1,
        "point": 4,
        "block": "H3C 口令控制策略",
        "expect": {
            "all": [
                {"contains": "fact:h3c.password_control.enabled=true"},
                {
                    "lt": {
                        "prefix": "fact:h3c.password_control.aging_days=",
                        "value": 91,
                    }
                },
                {
                    "gt": {
                        "prefix": "fact:h3c.password_control.length=",
                        "value": 7,
                    }
                },
                {
                    "gt": {
                        "prefix": "fact:h3c.password_control.composition_types=",
                        "value": 2,
                    }
                },
            ]
        },
        "pass_reason": "已启用全局口令管理，口令有效期、长度和组成复杂度满足要求。",
        "fail_reason": "未启用口令管理，或口令有效期、长度、组成复杂度至少一项不满足要求。",
    },
    {
        "item": 2,
        "point": 1,
        "block": "H3C 口令控制策略",
        "expect": {
            "all": [
                {"contains": "fact:h3c.password_control.enabled=true"},
                {
                    "gt": {
                        "prefix": "fact:h3c.password_control.login_attempt=",
                        "value": 0,
                    }
                },
            ]
        },
        "pass_reason": "已启用口令管理并配置登录失败次数限制。",
        "fail_reason": "未启用口令管理或未配置登录失败次数限制。",
    },
    {
        "item": 2,
        "point": 2,
        "block": "H3C 口令控制策略",
        "expect": {
            "all": [
                {
                    "lt": {
                        "prefix": "fact:h3c.password_control.login_attempt=",
                        "value": 11,
                    }
                },
                {
                    "gt": {
                        "prefix": "fact:h3c.password_control.lock_minutes=",
                        "value": 4,
                    }
                },
            ]
        },
        "pass_reason": "登录失败次数阈值不超过 10 次，且锁定时间不少于 5 分钟。",
        "fail_reason": "登录失败次数阈值过大或未配置足够的锁定时间。",
    },
    {
        "item": 3,
        "point": 2,
        "block": "H3C 远程管理加密",
        "expect": {"contains": "fact:h3c.remote.encrypted=true"},
        "pass_reason": "远程管理使用 SSH/HTTPS 加密，未启用 Telnet/HTTP 明文管理。",
        "fail_reason": "远程管理仍启用 Telnet/HTTP 等明文协议，鉴别信息可能被窃听。",
    },
    {
        "item": 23,
        "point": 1,
        "block": "H3C 远程管理加密",
        "expect": {"contains": "fact:h3c.remote.encrypted=true"},
        "pass_reason": "数据传输采用 SSH/HTTPS 加密通道。",
        "fail_reason": "数据传输使用明文协议，完整性无法保证。",
    },
    {
        "item": 25,
        "point": 1,
        "block": "H3C 远程管理加密",
        "expect": {"contains": "fact:h3c.remote.encrypted=true"},
        "pass_reason": "数据传输采用 SSH/HTTPS 加密通道。",
        "fail_reason": "数据传输使用明文协议，保密性无法保证。",
    },
    {
        "item": 12,
        "point": 1,
        "block": "H3C 安全审计",
        "expect": {"contains": "fact:h3c.audit.info_center=true"},
        "pass_reason": "信息中心已启用，具备安全审计功能。",
        "fail_reason": "信息中心未启用，未开启安全审计功能。",
    },
    {
        "item": 12,
        "point": 3,
        "block": "H3C 安全审计",
        "expect": {
            "all": [
                {"contains": "fact:h3c.audit.info_center=true"},
                {"contains": "fact:h3c.audit.logbuffer=true"},
            ]
        },
        "pass_reason": "信息中心和日志缓冲区均已启用，可记录重要用户行为和安全事件。",
        "fail_reason": "日志缓冲区未启用，无法确认重要用户行为和安全事件被审计。",
    },
    {
        "item": 14,
        "point": 2,
        "block": "H3C 安全审计",
        "expect": {"contains": "fact:h3c.audit.loghost=true"},
        "pass_reason": "已配置日志主机，审计记录可定期备份到外部系统。",
        "fail_reason": "未配置日志主机，审计记录缺少外部备份。",
    },
    {
        "item": 18,
        "point": 1,
        "block": "H3C 管理终端限制",
        "expect": {"contains": "fact:h3c.acl.vty_restricted=true"},
        "pass_reason": "管理终端已通过 ACL 限制接入范围。",
        "fail_reason": "未发现管理终端接入范围限制配置。",
    },
    {
        "item": 24,
        "point": 1,
        "block": "H3C 口令密文存储",
        "expect": {"contains": "fact:h3c.secret_storage.cipher=true"},
        "pass_reason": "口令以 irreversible-cipher/cipher 等密文形式存储。",
        "fail_reason": "口令以 simple 等明文形式存储，完整性无法保证。",
    },
    {
        "item": 26,
        "point": 1,
        "block": "H3C 口令密文存储",
        "expect": {"contains": "fact:h3c.secret_storage.cipher=true"},
        "pass_reason": "口令以 irreversible-cipher/cipher 等密文形式存储。",
        "fail_reason": "口令以 simple 等明文形式存储，保密性无法保证。",
    },
]

HIGH_RISK_BINDS = {
    "HR-01": [1],
    "HR-02": [3],
    "HR-03": [4],
    "HR-04": [6],
    "HR-05": [5, 8, 9, 10],
    "HR-06": [17],
    "HR-07": [20],
    "HR-08": [19],
    "HR-09": [30],
    "HR-10": [25],
    "HR-11": [26],
    "HR-12": [27],
    "HR-13": [29],
    "HR-14": [28],
    "HR-15": [33],
    "HR-16": [34],
}


def _dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )


def _records(guide: Path, level: int = 3, vendor: str = "H3C") -> list[dict]:
    data = json.loads(guide.read_text(encoding="utf-8"))
    records = [
        record
        for record in data["records"]
        if int(record["level"]) == level and record["object"] == vendor
    ]
    return sorted(records, key=lambda record: int(record["seq"]))


def _split_guide(text: str) -> tuple[str, str]:
    body = text.strip()
    criteria = ""
    match = re.search(r"\n\s*判定[：:]\s*", body)
    if match:
        criteria = body[match.end() :]
        body = body[: match.start()]
    criteria = re.split(r"\n\s*版本差异", criteria)[0].strip()
    return body.strip(), criteria or "依据指导书判定标准执行。"


def _unit_no(record: dict) -> int:
    match = re.search(r"(\d+)$", str(record["unit_no"]))
    if not match:
        raise ValueError(f"无法解析单元编号：{record['unit_no']}")
    return int(match.group(1))


def _items(records: list[dict]) -> list[dict]:
    items: list[dict] = []
    for record in records:
        seq = int(record["seq"])
        content, criteria = _split_guide(str(record["operation_guide"]))
        if seq in NA_ITEMS:
            mode, policy, binary = "na", "na", False
        elif seq in MANUAL_ITEMS:
            mode, policy, binary = "manual", "manual", False
        else:
            policy, binary = AUTO_POLICY[seq]
            mode = "auto"
        item = {
            "item_id": str(record["unit_no"]),
            "level": int(record["level"]),
            "seq": seq,
            "unit_no": _unit_no(record),
            "控制点": str(record["control_point"]).strip(),
            "控制项": str(record["item_text"]).strip(),
            "重要程度": "关键" if seq in CRITICAL_ITEMS else "重要",
            "检查内容": content,
            "判断标准": criteria,
            "policy": policy,
            "mode": mode,
            "binary": binary,
        }
        if seq in OPTIONAL_ITEMS:
            item["optional_clause"] = True
        if seq in MANUAL_POINTS:
            item["manual_points"] = MANUAL_POINTS[seq]
        items.append(item)
    return items


def _checks() -> list[dict]:
    checks = []
    for block in BLOCKS:
        checks.append(
            {
                "title": block["title"],
                # 报告日志的一个 section 可包含多个主题，按标题绑定更稳健。
                "section": "",
                "block_index": block["block_index"],
                "kind": "judge",
                "normalize": "h3c_config",
                "binds": [
                    {"item": item, "level": 3, "points": points}
                    for item, points in block["binds"]
                ],
                "session": [{"kind": "network", "pattern": block["pattern"]}],
            }
        )
    return checks


def _rules() -> list[dict]:
    rules = []
    for index, rule in enumerate(RULES, 1):
        rules.append(
            {
                "rule_id": f"H3C-L3-{rule['item']:02d}-P{rule['point']:02d}-{index:02d}",
                "level": 3,
                "item": rule["item"],
                "point": rule["point"],
                "block": rule["block"],
                "expect": rule["expect"],
                "pass_reason": rule["pass_reason"],
                "fail_reason": rule["fail_reason"],
            }
        )
    return rules


def _texts(records: list[dict]) -> dict:
    entries = []
    for record in records:
        problem = str(record.get("problem") or "").strip()
        lines = [line.strip() for line in problem.splitlines() if line.strip()]
        entries.append(
            {
                "seq": int(record["seq"]),
                "control_point": str(record["control_point"]).strip(),
                "control_item": str(record["item_text"]).strip(),
                "issue_summary": lines[0] if lines else "配置不符合指导书要求。",
                "issue_detail": "\n".join(lines[1:]) if len(lines) > 1 else "",
                "hazard": str(record.get("harm") or "").strip(),
                "remediation": str(record.get("remediation") or "").strip(),
                "threat": str(record.get("threat") or "").strip(),
                "inherent_risk": str(record.get("risk_value") or "中").strip(),
            }
        )
    return {"texts": entries}


def _remediation(records: list[dict]) -> dict:
    priority = {"高": "高", "中": "中", "低": "低"}
    rules = []
    for record in records:
        seq = int(record["seq"])
        action = str(record.get("remediation") or "").strip()
        if not action:
            continue
        problem = "；".join(
            line.strip()
            for line in str(record.get("problem") or "").splitlines()
            if line.strip()
        )
        rules.append(
            {
                "id": f"REM-NET-{seq:02d}",
                "title": f"{record['control_point']}整改",
                "applies_to": {"level": [3], "family": ["network"], "item_seqs": [seq]},
                "priority": priority.get(str(record.get("risk_value") or ""), "中"),
                "problem": problem or "配置不符合指导书要求。",
                "cause": "设备安全基线未配置或配置未落到该设备。",
                "action": action,
                "clause": str(record["item_text"]).strip(),
            }
        )
    return {
        "version": "0.1.0",
        "status": "active",
        "rules": rules,
    }


def _high_risk() -> list[dict]:
    records = yaml.safe_load((LINUX_PACK / "high_risk.yaml").read_text(encoding="utf-8"))
    for record in records:
        hr_id = record.get("hr_id")
        if hr_id in HIGH_RISK_BINDS:
            record["binds_items"] = HIGH_RISK_BINDS[hr_id]
    return records


def _capture() -> dict:
    rules = []
    for block in BLOCKS:
        for title, command in block["commands"]:
            rules.append(
                {
                    "section": block["title"],
                    "title": title,
                    "command": command,
                    "levels": [3],
                    "families": ["network"],
                }
            )
    return {
        "asset_family": "network",
        "version": "0.1.0",
        "status": "active",
        "rules": rules,
    }


def _coverage(records: list[dict]) -> str:
    auto = {item for item in AUTO_POLICY}
    manual_points = {seq: points for seq, points in MANUAL_POINTS.items()}
    lines = [
        "# H3C 三级网络设备规则域覆盖报告",
        "",
        "本报告由 `tools/build_network_pack.py` 从网络设备指导书自动生成。",
        "H3C 采集命令、判定规则与人工核查点独立于其他厂商，不能直接复制给 HUAWEI/Cisco/ZTE。",
        "",
        "| 项 | 控制点 | 模式 | 采集块 | 自动判定点 | 人工核查点 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    block_by_item: dict[int, list[str]] = {}
    for block in BLOCKS:
        for item, points in block["binds"]:
            block_by_item.setdefault(item, []).append(
                f"{block['title']}({','.join(map(str, points))})"
            )
    for record in records:
        seq = int(record["seq"])
        if seq in NA_ITEMS:
            mode = "不适用"
        elif seq in MANUAL_ITEMS:
            mode = "人工"
        else:
            mode = "自动/部分人工"
        auto_points = sorted(
            {
                point
                for block in BLOCKS
                for item, points in block["binds"]
                if item == seq
                for point in points
            }
        )
        manual = sorted(point["point"] for point in manual_points.get(seq, []))
        lines.append(
            "| {seq} | {point} | {mode} | {blocks} | {auto} | {manual} |".format(
                seq=seq,
                point=str(record["control_point"]).strip(),
                mode=mode,
                blocks="<br>".join(block_by_item.get(seq, [])),
                auto=",".join(map(str, auto_points)) or "—",
                manual=",".join(map(str, manual)) or "—",
            )
        )
    return "\n".join(lines) + "\n"


def build(guide: Path, out: Path) -> None:
    records = _records(guide)
    if len(records) != 34:
        raise SystemExit(f"H3C 三级记录应为 34 条，实际 {len(records)}")

    _dump(out / "pack.yaml", {
        "name": "network_devices",
        "version": "0.1.0",
        "levels": [3],
        "os_family": ["network"],
        "asset_types": ["网络设备", "安全设备"],
        "guides": ["三级-安全通用要求"],
        "items": {"level_3": "items_L3.yaml"},
        "adapters": {
            "h3c": "adapters/h3c",
            "generic": "adapters/generic",
        },
        "default_adapter": "generic",
    })
    _dump(out / "items_L3.yaml", _items(records))
    _dump(out / "remediation.yaml", _remediation(records))
    (out / "record.yaml").write_text(
        (LINUX_PACK / "record.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    _dump(out / "library.yaml", {
        "version": "0.1.0",
        "libraries": {
            "capture": {
                "title": "数据采集命令库",
                "status": "active",
                "path": "adapters/h3c/capture.yaml",
            },
            "record": {
                "title": "记录表生成规则库",
                "status": "active",
                "path": "record.yaml",
            },
            "judge": {
                "title": "记录表判定规则库",
                "status": "active",
                "paths": ["adapters/h3c/rules/level3.yaml"],
            },
            "remediation": {
                "title": "风险分析与整改建议库",
                "status": "active",
                "path": "remediation.yaml",
            },
            "high_risk": {
                "title": "高风险判定规则库",
                "status": "active",
                "path": "adapters/h3c/high_risk.yaml",
            },
            "major": {
                "title": "重大风险隐患规则库",
                "status": "active",
                "path": "adapters/h3c/major.yaml",
            },
        },
    })

    adapter = out / "adapters" / "h3c"
    _dump(adapter / "adapter.yaml", {
        "name": "H3C",
        "vendor": "H3C",
        "aliases": ["h3c", "新华三", "comware"],
        "levels": [3],
        "asset_types": ["网络设备", "安全设备"],
        "checks_map": "checks_map.yaml",
        "rules_dir": "rules",
        "high_risk": "high_risk.yaml",
        "major": "major.yaml",
        "texts": "texts/library.yaml",
        "capture": "capture.yaml",
    })
    _dump(adapter / "checks_map.yaml", {"checks": _checks()})
    _dump(adapter / "rules" / "level3.yaml", {"rules": _rules()})
    _dump(adapter / "high_risk.yaml", _high_risk())
    (adapter / "major.yaml").write_text(
        (LINUX_PACK / "major.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    _dump(adapter / "texts" / "library.yaml", _texts(records))
    _dump(adapter / "capture.yaml", _capture())

    _dump(out / "adapters" / "generic" / "adapter.yaml", {
        "name": "通用安全设备",
        "vendor": "generic",
        "aliases": ["通用", "generic", "通用安全设备"],
        "levels": [3],
        "asset_types": ["网络设备", "安全设备"],
        "manual_all": True,
    })

    report = REPO_ROOT / "guides" / "reports" / "network_h3c_L3.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(_coverage(records), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="生成网络设备规则域与 H3C 三级适配器")
    parser.add_argument("--guide", default="guides/network.json")
    parser.add_argument("--out", default="packs/network_devices")
    args = parser.parse_args()
    build(Path(args.guide), Path(args.out))


if __name__ == "__main__":
    main()
