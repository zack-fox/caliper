"""从 guides/os.json 生成操作系统设备规则域。

六套指导书共用同一组测评项，但采集命令、判定规则与人工核查点按平台隔离：
Linux 复用 RHEL 基线，Ubuntu 复用 Debian 基线，Windows/AIX/ESXi/Solaris
先落人工核查模板。任何适配器都不得引用其他平台的命令。
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "guides" / "os.json"
OUT = ROOT / "packs" / "os_devices"
SOURCE = ROOT / "packs" / "linux_os"
LEVELS = (2, 3, 4)

PLATFORMS: dict[str, dict[str, Any]] = {
    "linux": {
        "object": "Linux",
        "name": "Linux",
        "vendor": "Linux",
        "aliases": [
            "linux",
            "centos",
            "rhel",
            "red hat",
            "redhat",
            "rocky",
            "almalinux",
            "suse",
            "sles",
            "kylin",
            "麒麟",
            "统信",
            "uos",
        ],
        "asset_types": ["服务器", "存储设备"],
        "manual": False,
    },
    "ubuntu": {
        "object": "Ubuntu（Debian）",
        "name": "Ubuntu",
        "vendor": "Ubuntu",
        "aliases": ["ubuntu", "debian", "debian gnu/linux"],
        "asset_types": ["服务器", "存储设备"],
        "manual": False,
    },
    "windows": {
        "object": "Windows",
        "name": "Windows",
        "vendor": "Windows",
        "aliases": ["windows", "windows server", "win server", "microsoft windows"],
        "asset_types": ["服务器", "存储设备"],
        "manual": True,
    },
    "aix": {
        "object": "AIX",
        "name": "AIX",
        "vendor": "AIX",
        "aliases": ["aix", "ibm aix"],
        "asset_types": ["服务器", "存储设备"],
        "manual": True,
    },
    "solaris": {
        "object": "Solaris",
        "name": "Solaris",
        "vendor": "Solaris",
        "aliases": ["solaris", "oracle solaris", "sunos"],
        "asset_types": ["服务器", "存储设备"],
        "manual": True,
    },
    "esxi": {
        "object": "ESXI",
        "name": "VMware ESXi",
        "vendor": "VMware ESXi",
        "aliases": ["esxi", "vmware", "vmware esxi", "vsphere"],
        "asset_types": ["服务器"],
        "manual": True,
    },
    "generic": {
        "object": "",
        "name": "通用操作系统",
        "vendor": "通用操作系统",
        "aliases": ["generic", "os", "other os", "其他操作系统", "未知操作系统"],
        "asset_types": ["服务器", "存储设备"],
        "manual": True,
    },
}

# 仅保留操作系统自身的检查块；中间件、数据库摘要不得进入操作系统规则域。
EXCLUDED_TITLE_PREFIXES = (
    "MySQL",
    "Nginx",
    "Apache",
    "Tomcat",
    "Docker",
    "Middleware",
    "Database detected",
    "Public IP",
)
UBUNTU_EXCLUDED_TITLES = {"SELinux status"}

# 三级测评项到四级测评项的主题映射；四级的两个新增子项走人工核查。
L3_TO_L4 = {
    1: 1,
    2: 2,
    3: 3,
    4: 4,
    5: 5,
    6: 6,
    7: 7,
    8: 8,
    9: 9,
    10: 10,
    11: 11,
    12: 12,
    13: 13,
    14: 14,
    15: 15,
    16: 16,
    17: 17,
    18: 18,
    19: 19,
    20: 20,
    21: 21,
    22: 22,
    23: 23,
    24: 24,
    25: 25,
    26: 27,
    27: 28,
    28: 29,
    29: 30,
    30: 31,
    31: 33,
    32: 34,
}
L4_TO_L3 = {target: source for source, target in L3_TO_L4.items()}
L4_MANUAL_SEQS = {26, 32}

# 高风险判例按业务主题显式绑定到各等级，避免 seq 漂移串项。
HR_BINDS: dict[str, dict[int, list[int]]] = {
    "HR-01": {2: [1], 3: [1], 4: [1]},
    "HR-02": {2: [3], 3: [3], 4: [3]},
    "HR-03": {3: [4], 4: [4]},
    "HR-04": {2: [5], 3: [6], 4: [6]},
    "HR-05": {2: [4, 7, 8, 9], 3: [5, 8, 9, 10], 4: [5, 8, 9, 10]},
    "HR-06": {2: [12], 3: [17], 4: [17]},
    "HR-07": {2: [15], 3: [20], 4: [20]},
    "HR-08": {},
    "HR-09": {2: [16], 3: [22], 4: [22]},
    "HR-10": {3: [26], 4: [27]},
    "HR-11": {3: [27], 4: [28]},
    "HR-12": {2: [19], 3: [28], 4: [29]},
    "HR-13": {3: [30], 4: [31]},
    "HR-14": {4: [32]},
    "HR-15": {2: [22], 3: [33]},
    "HR-16": {2: [23], 3: [34]},
}

DEFAULT_ACCOUNTS_TITLE = "Default accounts"
DEFAULT_ACCOUNTS_COMMAND = (
    "awk -F: '$3 < 1000 {print $1 \":\" $3 \":\" $7}' /etc/passwd"
)

COMMON_MANUAL_POINTS = {
    3: {
        6: [
            {
                "point": 2,
                "reason": "默认账户口令是否已修改，需结合 /etc/shadow 或访谈确认。",
            }
        ],
        8: [
            {
                "point": 3,
                "reason": "管理用户权限是否为最小权限，需结合授权清单和访谈确认。",
            }
        ],
        9: [
            {
                "point": 3,
                "reason": "越权访问需通过实际测试验证。",
            }
        ],
    },
    4: {
        6: [
            {
                "point": 2,
                "reason": "默认账户口令是否已修改，需结合 /etc/shadow 或访谈确认。",
            }
        ],
        8: [
            {
                "point": 3,
                "reason": "管理用户权限是否为最小权限，需结合授权清单和访谈确认。",
            }
        ],
        9: [
            {
                "point": 3,
                "reason": "越权访问需通过实际测试验证。",
            }
        ],
    },
}

UBUNTU_MANUAL_POINTS = {
    3: {
        11: [
            {
                "point": 1,
                "reason": "Ubuntu 默认使用 AppArmor 而非 SELinux，需人工核查强制访问控制状态。",
            }
        ]
    },
    4: {
        11: [
            {
                "point": 1,
                "reason": "Ubuntu 默认使用 AppArmor 而非 SELinux，需人工核查强制访问控制状态。",
            }
        ]
    },
}

EXTRA_RULES = {
    3: [
        {
            "item": 6,
            "point": 1,
            "block": DEFAULT_ACCOUNTS_TITLE,
            "expect": {"eq": "fact:os.default_accounts.none=true"},
            "pass": "未发现常见系统默认账户。",
            "fail": "仍存在常见系统默认账户，应重命名或删除。",
        },
        {
            "item": 9,
            "point": 1,
            "block": "Separation of duty (three roles)",
            "expect": {"contains": "sudo user"},
            "pass": "已由授权主体配置访问控制策略。",
            "fail": "未发现授权主体配置访问控制策略的证据。",
        },
        {
            "item": 9,
            "point": 2,
            "block": "sudo authorization / NOPASSWD",
            "expect": {"not_contains": "NOPASSWD"},
            "pass": "未发现免密提权规则，访问控制策略受限。",
            "fail": "存在 NOPASSWD 免密提权规则，应复核最小权限。",
        },
    ],
    4: [
        {
            "item": 6,
            "point": 1,
            "block": DEFAULT_ACCOUNTS_TITLE,
            "expect": {"eq": "fact:os.default_accounts.none=true"},
            "pass": "未发现常见系统默认账户。",
            "fail": "仍存在常见系统默认账户，应重命名或删除。",
        },
        {
            "item": 9,
            "point": 1,
            "block": "Separation of duty (three roles)",
            "expect": {"contains": "sudo user"},
            "pass": "已由授权主体配置访问控制策略。",
            "fail": "未发现授权主体配置访问控制策略的证据。",
        },
        {
            "item": 9,
            "point": 2,
            "block": "sudo authorization / NOPASSWD",
            "expect": {"not_contains": "NOPASSWD"},
            "pass": "未发现免密提权规则，访问控制策略受限。",
            "fail": "存在 NOPASSWD 免密提权规则，应复核最小权限。",
        },
    ],
}


def _manual_points(platform: str) -> dict:
    data = copy.deepcopy(COMMON_MANUAL_POINTS)
    if platform == "ubuntu":
        for level, points in UBUNTU_MANUAL_POINTS.items():
            for seq, entries in points.items():
                data.setdefault(level, {}).setdefault(seq, []).extend(entries)
    return data


def _load(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )


def _records(data: dict) -> list[dict]:
    return data["records"]


def _records_for(records: list[dict], obj: str, level: int) -> list[dict]:
    if not obj:
        return []
    return [row for row in records if row["object"] == obj and row["level"] == level]


def _ordered(records: list[dict]) -> list[dict]:
    return sorted(records, key=lambda row: (row.get("excel_row") or 0))


def _title_allowed(title: str, platform: str) -> bool:
    if any(title.startswith(prefix) for prefix in EXCLUDED_TITLE_PREFIXES):
        return False
    if platform == "ubuntu" and title in UBUNTU_EXCLUDED_TITLES:
        return False
    return True


def _build_items(records: list[dict]) -> dict[int, list[dict]]:
    l2 = _load(SOURCE / "items_L2.yaml")
    l3 = _load(SOURCE / "items_L3.yaml")
    l4_recs = _ordered(_records_for(records, "Linux", 4))
    if len(l4_recs) != 34:
        raise SystemExit(f"四级 Linux 测评项应为 34 条，实际 {len(l4_recs)}")
    l3_by_seq = {row["seq"]: row for row in l3}
    l4: list[dict] = []
    for index, rec in enumerate(l4_recs, start=1):
        if index in L4_MANUAL_SEQS:
            item = {
                "item_id": rec["unit_no"],
                "level": 4,
                "seq": index,
                "unit_no": index,
                "控制点": rec["control_point"],
                "控制项": rec["item_text"],
                "重要程度": _importance(rec),
                "检查内容": f"1) {rec['item_text']}",
                "判断标准": "需结合指导书和现场访谈进行人工核查。",
                "policy": "manual",
                "mode": "manual",
                "binary": False,
                "optional_clause": False,
            }
        else:
            source = l3_by_seq[L4_TO_L3[index]]
            item = copy.deepcopy(source)
            item["item_id"] = rec["unit_no"]
            item["level"] = 4
            item["seq"] = index
            item["unit_no"] = index
            item["控制点"] = rec["control_point"]
            item["控制项"] = rec["item_text"]
        l4.append(item)
    return {2: l2, 3: l3, 4: l4}


def _importance(rec: dict) -> str:
    value = str(rec.get("risk_value") or "").strip()
    if value == "高":
        return "关键"
    if value == "中":
        return "重要"
    return "一般"


def _filter_checks_map(platform: str) -> dict:
    data = _load(SOURCE / "checks_map.yaml")
    checks: list[dict] = []
    for check in data["checks"]:
        if not _title_allowed(check["title"], platform):
            continue
        item = copy.deepcopy(check)
        item["os_family"] = ["debian", "rhel"]
        item["block_index"] = len(checks) + 1
        binds: list[dict] = []
        for bind in item.get("binds", []):
            binds.append(bind)
            if bind.get("level", 3) == 3:
                mapped = L3_TO_L4.get(bind["item"])
                if mapped is not None:
                    binds.append(
                        {
                            "level": 4,
                            "item": mapped,
                            "points": list(bind["points"]),
                        }
                    )
        unique: list[dict] = []
        seen: set[tuple[int, int]] = set()
        for bind in binds:
            if item["title"] == "Password hash algorithm" and bind.get("level", 3) != 2:
                continue
            key = (bind.get("level", 3), bind["item"])
            if key in seen:
                continue
            seen.add(key)
            unique.append(bind)
        item["binds"] = unique
        checks.append(item)
    checks.append(
        {
            "section": "3. ACCESS CONTROL",
            "title": DEFAULT_ACCOUNTS_TITLE,
            "command": DEFAULT_ACCOUNTS_COMMAND,
            "file": "/etc/passwd",
            "expect": "默认账户已重命名或删除。",
            "os_family": ["debian", "rhel"],
            "normalize": "os_default_accounts",
            "block_index": len(checks) + 1,
            "binds": [
                {"level": 3, "item": 6, "points": [1]},
                {"level": 4, "item": 6, "points": [1]},
            ],
        }
    )
    return {"checks": checks}


LINUX_COMMANDS: dict[str, str] = {
    "Privileged groups": "getent group wheel root 2>/dev/null",
    "Patches / reboot": (
        "test -f /var/run/reboot-required && echo reboot-required; "
        "command -v dnf >/dev/null 2>&1 && dnf check-update 2>/dev/null | head -20; "
        "command -v yum >/dev/null 2>&1 && yum check-update 2>/dev/null | head -20"
    ),
    "Security agent (EDR / AV / IDS)": (
        "pgrep -af 'aegis|YunJing|sangfor|falcon|clamd|osquery|wazuh|suricata|snort' 2>/dev/null; "
        "command -v rpm >/dev/null 2>&1 && rpm -qa 2>/dev/null "
        "| grep -Ei 'aegis|edr|antivirus|clam|osquery|wazuh|suricata|snort'"
    ),
    "Password hash algorithm": (
        "awk -F: '$2!~/^[!*]/{print $1, substr($2,1,3)}' /etc/shadow; "
        "grep -h 'pam_unix.so' /etc/pam.d/system-auth /etc/pam.d/password-auth 2>/dev/null"
    ),
}

UBUNTU_COMMANDS: dict[str, str] = {
    "Host / OS / kernel / time": "hostname; uname -a; date; uptime; cat /etc/os-release 2>/dev/null",
    "Privileged groups": "getent group sudo adm shadow 2>/dev/null",
    "Patches / reboot": (
        "test -f /var/run/reboot-required && echo reboot-required; "
        "apt list --upgradable 2>/dev/null | head -20"
    ),
    "Security agent (EDR / AV / IDS)": (
        "pgrep -af 'aegis|YunJing|sangfor|falcon|clamd|osquery|wazuh|suricata|snort' 2>/dev/null; "
        "dpkg -l 2>/dev/null | awk '$1==\"ii\"{print $2,$3}' "
        "| grep -Ei 'aegis|edr|antivirus|clam|osquery|wazuh|suricata|snort'"
    ),
    "Password complexity": (
        "grep -RhE 'pam_(pwquality|cracklib)' /etc/pam.d 2>/dev/null; "
        "cat /etc/security/pwquality.conf 2>/dev/null"
    ),
    "Time sync": (
        "timedatectl 2>/dev/null | grep -Ei 'time zone|system clock|NTP'; "
        "systemctl is-active systemd-timesyncd 2>/dev/null"
    ),
    "Password hash algorithm": (
        "awk -F: '$2!~/^[!*]/{print $1, substr($2,1,3)}' /etc/shadow; "
        "grep -h 'pam_unix.so' /etc/pam.d/common-password 2>/dev/null"
    ),
}


def _capture(platform: str) -> dict:
    data = _load(SOURCE / "capture.yaml")
    rules: list[dict] = []
    for rule in data["rules"]:
        if not _title_allowed(rule["title"], platform):
            continue
        item = copy.deepcopy(rule)
        item["levels"] = [2, 3, 4]
        item["families"] = ["server"]
        overrides = UBUNTU_COMMANDS if platform == "ubuntu" else LINUX_COMMANDS
        if item["title"] in overrides:
            item["command"] = overrides[item["title"]]
        rules.append(item)
    rules.append(
        {
            "section": "3. ACCESS CONTROL",
            "title": DEFAULT_ACCOUNTS_TITLE,
            "command": DEFAULT_ACCOUNTS_COMMAND,
            "file": "/etc/passwd",
            "expect": "默认账户已重命名或删除。",
            "levels": [2, 3, 4],
            "families": ["server"],
        }
    )
    return {
        "version": data.get("version", "0.1.0"),
        "status": "active",
        "asset_family": "server",
        "rules": rules,
    }


def _rules(platform: str) -> dict[int, list[dict]]:
    allowed = {
        check["title"] for check in _filter_checks_map(platform)["checks"]
    }
    result: dict[int, list[dict]] = {}
    for level in (2, 3):
        data = _load(SOURCE / "rules" / f"level{level}.yaml")
        rules = [
            copy.deepcopy(rule)
            for rule in data["rules"]
            if rule["block"] in allowed
        ]
        for index, spec in enumerate(EXTRA_RULES.get(level, []), start=1):
            rules.append(
                {
                    "rule_id": f"L{level}-EXTRA-{spec['item']:02d}-P{spec['point']:02d}-{index:02d}",
                    "level": level,
                    "item": spec["item"],
                    "point": spec["point"],
                    "block": spec["block"],
                    "expect": spec["expect"],
                    "pass_reason": spec["pass"],
                    "fail_reason": spec["fail"],
                }
            )
        result[level] = rules
    l4: list[dict] = []
    for index, rule in enumerate(result[3], start=1):
        if str(rule.get("rule_id", "")).startswith("L3-EXTRA"):
            continue
        mapped = L3_TO_L4.get(rule["item"])
        if mapped is None:
            continue
        item = copy.deepcopy(rule)
        item["level"] = 4
        item["item"] = mapped
        item["rule_id"] = f"L4-{mapped:02d}-P{rule['point']:02d}-{index:03d}"
        l4.append(item)
    for index, spec in enumerate(EXTRA_RULES[4], start=1):
        l4.append(
            {
                "rule_id": f"L4-EXTRA-{spec['item']:02d}-P{spec['point']:02d}-{index:02d}",
                "level": 4,
                "item": spec["item"],
                "point": spec["point"],
                "block": spec["block"],
                "expect": spec["expect"],
                "pass_reason": spec["pass"],
                "fail_reason": spec["fail"],
            }
        )
    result[4] = l4
    return result


def _texts_and_remediation(
    records: list[dict], platform: str, items: dict[int, list[dict]]
) -> tuple[list[dict], list[dict]]:
    obj = PLATFORMS[platform]["object"]
    texts: list[dict] = []
    remediation: list[dict] = []
    seen: set[str] = set()
    for level in LEVELS:
        rows = _ordered(_records_for(records, obj, level))
        if not rows:
            continue
        for index, rec in enumerate(rows, start=1):
            control_item = str(rec.get("item_text") or "").strip()
            if not control_item:
                continue
            problem = str(rec.get("problem") or "").strip()
            summary = problem.splitlines()[0].strip() if problem else control_item
            if control_item not in seen:
                seen.add(control_item)
                texts.append(
                    {
                        "seq": index,
                        "standard_code": rec.get("unit_no") or f"L{level}-{index:02d}",
                        "layer": "安全计算环境",
                        "control_point": rec.get("control_point") or "",
                        "control_item": control_item,
                        "issue_summary": summary,
                        "issue_detail": str(rec.get("result_fail") or "").strip(),
                        "hazard": str(rec.get("harm") or "").strip(),
                        "remediation": str(rec.get("remediation") or "").strip(),
                        "threat": str(rec.get("threat") or "").strip(),
                        "inherent_risk": _priority(rec),
                    }
                )
            remediation.append(
                {
                    "id": f"REM-{platform.upper()}-{level}-{index:02d}",
                    "title": f"{rec.get('control_point') or '安全控制'}要求未满足",
                    "applies_to": {
                        "level": [level],
                        "family": ["server"],
                        "item_seqs": [index],
                    },
                    "priority": _priority(rec),
                    "problem": problem or control_item,
                    "cause": str(rec.get("threat") or "").strip() or "安全基线未落实。",
                    "action": str(rec.get("remediation") or "").strip()
                    or "按指导书要求完成整改。",
                    "clause": f"GB/T 22239-2019 {level}级 {rec.get('unit_no') or index} {rec.get('control_point') or ''}".strip(),
                }
            )
    if not texts:
        for level in LEVELS:
            for item in items[level]:
                texts.append(
                    {
                        "seq": item["seq"],
                        "standard_code": item["item_id"],
                        "layer": "安全计算环境",
                        "control_point": item["控制点"],
                        "control_item": item["控制项"],
                        "issue_summary": item["控制项"],
                        "issue_detail": "需按通用操作系统基线进行人工核查。",
                        "hazard": "",
                        "remediation": "按通用操作系统安全基线完成配置核查与整改。",
                        "threat": "",
                        "inherent_risk": "中",
                    }
                )
                remediation.append(
                    {
                        "id": f"REM-{platform.upper()}-{level}-{item['seq']:02d}",
                        "title": f"{item['控制点']}要求未满足",
                        "applies_to": {
                            "level": [level],
                            "family": ["server"],
                            "item_seqs": [item["seq"]],
                        },
                        "priority": "中",
                        "problem": item["控制项"],
                        "cause": "通用操作系统基线未落实。",
                        "action": "按通用操作系统安全基线完成配置核查与整改。",
                        "clause": f"GB/T 22239-2019 {level}级 {item['item_id']} {item['控制点']}",
                    }
                )
    return texts, remediation


def _priority(rec: dict) -> str:
    value = str(rec.get("risk_value") or "").strip()
    return value if value in {"高", "中", "低"} else "中"


def _high_risk() -> list[dict]:
    data = _load(SOURCE / "high_risk.yaml")
    entries: list[dict] = []
    for entry in data:
        item = copy.deepcopy(entry)
        item["binds"] = HR_BINDS.get(item["hr_id"], {})
        entries.append(item)
    return entries


def _adapter_meta(platform: str) -> dict:
    meta = PLATFORMS[platform]
    data: dict[str, Any] = {
        "name": meta["name"],
        "vendor": meta["vendor"],
        "aliases": list(meta["aliases"]),
        "levels": list(LEVELS),
        "asset_types": list(meta["asset_types"]),
    }
    if meta["manual"]:
        data["manual_all"] = True
    else:
        data.update(
            {
                "checks_map": "checks_map.yaml",
                "rules_dir": "rules",
                "capture": "capture.yaml",
                "high_risk": "high_risk.yaml",
                "texts": "texts/library.yaml",
                "remediation": "remediation.yaml",
            }
        )
        data["manual_points_by_level"] = _manual_points(platform)
    return data


def _coverage(
    platform: str, level: int, rows: list[dict], rules: list[dict]
) -> str:
    meta = PLATFORMS[platform]
    extra_manual = _manual_points(platform).get(level, {})
    lines = [
        f"# {meta['name']} {level} 级操作系统规则域覆盖报告",
        "",
        "本报告由 `tools/build_os_pack.py` 从操作系统指导书自动生成。",
        "采集命令、判定规则与人工核查点只适用于本平台，不能复制给其他平台。",
    ]
    if meta["manual"]:
        lines.extend(
            [
                "",
                "该平台指导书未提供可直接执行的采集命令，整包按人工核查模板处理。",
            ]
        )
    lines.extend(
        [
            "",
            "| 项 | 控制点 | 模式 | 自动实施点 | 人工核查点 |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for item in rows:
        seq = item["seq"]
        auto_points = sorted({rule["point"] for rule in rules if rule["item"] == seq})
        manual_points = {entry["point"] for entry in item.get("manual_points", [])}
        manual_points.update(entry["point"] for entry in extra_manual.get(seq, []))
        lines.append(
            "| {seq} | {point} | {mode} | {auto} | {manual} |".format(
                seq=seq,
                point=item["控制点"],
                mode=item["mode"],
                auto=",".join(map(str, auto_points)) or "—",
                manual=",".join(map(str, sorted(manual_points))) or "—",
            )
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    records = _records(json.loads(GUIDE.read_text(encoding="utf-8")))
    items = _build_items(records)

    for level, rows in items.items():
        _dump(OUT / f"items_L{level}.yaml", rows)

    _dump(OUT / "record.yaml", _load(SOURCE / "record.yaml"))
    major = _load(SOURCE / "major.yaml")
    _dump(OUT / "major.yaml", major)
    high_risk = _high_risk()

    adapters = {key: f"adapters/{key}" for key in PLATFORMS}
    pack = {
        "name": "os_devices",
        "version": "0.1.0",
        "levels": list(LEVELS),
        "os_family": ["debian", "rhel", "unknown"],
        "asset_types": ["服务器", "存储设备"],
        "guides": [
            "二级-安全通用要求",
            "三级-安全通用要求",
            "四级-安全通用要求",
        ],
        "items": {
            "level_2": "items_L2.yaml",
            "level_3": "items_L3.yaml",
            "level_4": "items_L4.yaml",
        },
        "adapters": adapters,
        "default_adapter": "generic",
    }
    _dump(OUT / "pack.yaml", pack)
    _dump(OUT / "high_risk.yaml", high_risk)

    library = {
        "version": "0.1.0",
        "libraries": {
            "capture": {
                "title": "数据采集命令库",
                "status": "active",
                "paths": [
                    f"adapters/{key}/capture.yaml"
                    for key, meta in PLATFORMS.items()
                    if not meta["manual"]
                ],
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
                    f"adapters/{key}/rules/level{level}.yaml"
                    for key, meta in PLATFORMS.items()
                    if not meta["manual"]
                    for level in LEVELS
                ],
            },
            "remediation": {
                "title": "风险分析与整改建议库",
                "status": "active",
                "paths": [f"adapters/{key}/remediation.yaml" for key in PLATFORMS],
            },
            "high_risk": {
                "title": "高风险判定规则库",
                "status": "active",
                "paths": [
                    f"adapters/{key}/high_risk.yaml"
                    for key, meta in PLATFORMS.items()
                    if not meta["manual"]
                ],
            },
            "major": {
                "title": "重大风险隐患规则库",
                "status": "active",
                "path": "major.yaml",
            },
        },
    }
    _dump(OUT / "library.yaml", library)

    for platform, meta in PLATFORMS.items():
        root = OUT / "adapters" / platform
        _dump(root / "adapter.yaml", _adapter_meta(platform))
        texts, remediation = _texts_and_remediation(records, platform, items)
        _dump(root / "texts" / "library.yaml", {"texts": texts})
        _dump(
            root / "remediation.yaml",
            {"version": "0.1.0", "status": "active", "rules": remediation},
        )
        if meta["manual"]:
            continue
        _dump(root / "checks_map.yaml", _filter_checks_map(platform))
        _dump(root / "capture.yaml", _capture(platform))
        _dump(root / "high_risk.yaml", high_risk)
        _dump(root / "major.yaml", major)
        for level, rules in _rules(platform).items():
            _dump(root / "rules" / f"level{level}.yaml", {"rules": rules})

    reports = ROOT / "guides" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    for platform in PLATFORMS:
        rules_by_level = {} if PLATFORMS[platform]["manual"] else _rules(platform)
        for level in LEVELS:
            (reports / f"os_{platform}_L{level}.md").write_text(
                _coverage(platform, level, items[level], rules_by_level.get(level, [])),
                encoding="utf-8",
            )

    summary = [
        "# 操作系统平台适配概览",
        "",
        "六个平台共享同一套测评项，以下为各平台的采集能力与人工核查边界。",
        "",
        "| 适配器 | 指导书对象 | 采集方式 |",
        "| --- | --- | --- |",
    ]
    for platform, meta in PLATFORMS.items():
        mode = "人工核查模板" if meta["manual"] else "自动采集 + 人工核查点"
        summary.append(f"| {meta['name']} | {meta['object']} | {mode} |")
    (reports / "os_platforms.md").write_text(
        "\n".join(summary) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
