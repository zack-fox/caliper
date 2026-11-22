"""从数据库指导书生成多引擎、多等级的设备规则域。

用法：
  .venv/bin/python tools/build_database_pack.py --guide guides/database.json --out packs/database

设计原则：
- 测评项按等级共享，MySQL / Oracle / SQL Server 各自拥有独立的采集命令、
  归一化事实、判定规则和人工核查点，绝不混用其他引擎的命令；
- 同一测评项可关联多个引擎适配器，但仅有厂商指导书给出命令的实施点才自动判定；
- SQL Server 指导书以图形界面和访谈为主，整包走人工核查模板；未知数据库引擎
  使用 generic 人工核查模板，避免误套 MySQL 或 Oracle 命令。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
NETWORK_PACK = REPO_ROOT / "packs" / "network_devices"
LEVELS = (2, 3, 4)

# 指导书单元号 → 共同测评主题。单元号是指导书标准条款号，seq 只是原表行序。
L2_KEYS = {
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
}
L3_KEYS = {
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
}
# 四级以 MySQL 指导书（36 条，含恶意代码防范）为基准；
# Oracle / SQL Server 指导书少一条恶意代码，unit 22 起整体前移一位。
L4_KEYS = {
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
    22: "MALWARE",
    23: "TRUST",
    24: "INTEGRITY_TRANSFER",
    25: "INTEGRITY_STORE",
    26: "NON_REPUDIATION",
    27: "CONF_TRANSFER",
    28: "CONF_STORE",
    29: "BACKUP_LOCAL",
    30: "BACKUP_OFFSITE",
    31: "HOT_REDUNDANCY",
    32: "DR_CENTER",
    33: "RESIDUAL_STORAGE",
    34: "RESIDUAL_CLEAR",
    35: "PERSONAL_COLLECT",
    36: "PERSONAL_USE",
}
LEVEL_KEYS = {2: L2_KEYS, 3: L3_KEYS, 4: L4_KEYS}

# 指导书明确判定为不适用的实施点；REMOTE/数据完整性/保密性属于“仅本地管理时不适用”，
# 由测评定性时人工确认，不默认置为不适用。
NA_KEYS = {
    2: {"MIN_INSTALL", "CLOSE_SERVICES", "INPUT", "MALWARE", "TRUST", "PERSONAL_COLLECT", "PERSONAL_USE"},
    3: {
        "MIN_INSTALL",
        "CLOSE_SERVICES",
        "INPUT",
        "INTRUSION_DETECT",
        "MALWARE",
        "TRUST",
        "PERSONAL_COLLECT",
        "PERSONAL_USE",
    },
}
NA_KEYS[4] = NA_KEYS[3]

AUTO_KEYS = {
    2: {
        "AUTH_ID",
        "LOGIN_FAIL",
        "REMOTE",
        "ACCOUNT_PERM",
        "EXTRA_ACCOUNT",
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
        "EXTRA_ACCOUNT",
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
AUTO_KEYS[4] = AUTO_KEYS[3]

POLICY: dict[str, tuple[str, bool]] = {
    "AUTH_ID": ("mixed_partial", False),
    "LOGIN_FAIL": ("mixed_partial", False),
    "REMOTE": ("binary", True),
    "ACCOUNT_PERM": ("mixed_partial", False),
    "EXTRA_ACCOUNT": ("mixed_partial", False),
    "PRIV_SEP": ("mixed_partial", False),
    "AUDIT_ENABLE": ("mixed_partial", False),
    "AUDIT_PROTECT": ("mixed_partial", False),
    "TERMINAL": ("binary", True),
    "INTEGRITY_TRANSFER": ("binary", True),
    "INTEGRITY_STORE": ("binary", True),
    "CONF_TRANSFER": ("binary", True),
    "CONF_STORE": ("binary", True),
}

CRITICAL_KEYS = {"REMOTE"}
OPTIONAL_KEYS: set[str] = set()

# 所有引擎共有的人工核查点：指导书要求访谈、测试或查看外部证据。
SHARED_MANUAL_POINTS: dict[str, list[int]] = {
    "AUTH_ID": [3],
    "REMOTE": [1],
    "ACCOUNT_PERM": [1],
    "EXTRA_ACCOUNT": [1, 3],
    "PRIV_SEP": [1],
    "AUDIT_ENABLE": [2, 3, 4],
    "AUDIT_PROTECT": [2],
    "TERMINAL": [2],
    "INTEGRITY_TRANSFER": [1],
    "INTEGRITY_STORE": [2],
    "CONF_TRANSFER": [1],
    "CONF_STORE": [2],
}
MANUAL_REASONS = {
    ("AUTH_ID", 3): "口令组成情况需访谈确认，命令回显无法判断实际口令强度",
    ("REMOTE", 1): "是否实际通过远程方式管理数据库需访谈确认；仅本地管理时该项不适用",
    ("ACCOUNT_PERM", 1): "账户是否与实际使用人员一一对应需结合访谈确认",
    ("EXTRA_ACCOUNT", 1): "是否存在多余账户需结合人员与业务清单访谈确认",
    ("EXTRA_ACCOUNT", 3): "是否存在多人共用账户需结合访谈确认",
    ("PRIV_SEP", 1): "是否单独设立系统管理员、安全管理员和审计管理员需访谈确认",
    ("AUDIT_ENABLE", 2): "是否启用了满足要求的审计策略需现场核查",
    ("AUDIT_ENABLE", 3): "审计对象是否覆盖全部用户和重要行为需结合日志核查",
    ("AUDIT_ENABLE", 4): "审计事件是否完善需结合审计配置与日志内容核查",
    ("AUDIT_PROTECT", 2): "审计记录是否定期备份、保存时间是否大于 6 个月需访谈并查看备份记录",
    ("TERMINAL", 2): "允许登录的地址范围是否合理需结合业务访谈确认",
    ("INTEGRITY_TRANSFER", 1): "是否涉及远程管理需访谈确认；仅本地管理时该项不适用",
    ("INTEGRITY_STORE", 2): "业务数据是否加密存储需结合表空间与文件核查",
    ("CONF_TRANSFER", 1): "是否涉及远程管理需访谈确认；仅本地管理时该项不适用",
    ("CONF_STORE", 2): "业务数据是否加密存储需结合表空间与文件核查",
}

ENGINES: dict[str, dict[str, Any]] = {
    "mysql": {
        "name": "MySQL",
        "vendor": "MySQL",
        "guide_object": "MySQL",
        "aliases": ["mysql", "mariadb", "percona", "mysql数据库", "mariadb数据库"],
        "asset_types": ["数据库"],
    },
    "oracle": {
        "name": "Oracle",
        "vendor": "Oracle",
        "guide_object": "Oracle",
        "aliases": ["oracle", "甲骨文", "oracle db", "oracle数据库"],
        "asset_types": ["数据库"],
    },
    "sqlserver": {
        "name": "SQL Server",
        "vendor": "SQL Server",
        "guide_object": "SQLSever",
        "aliases": ["sqlserver", "sql server", "mssql", "sqlsever", "sql server数据库"],
        "asset_types": ["数据库"],
        "manual_all": True,
    },
    "generic": {
        "name": "通用数据库",
        "vendor": "通用数据库",
        "guide_object": "MySQL",
        "aliases": ["generic", "database", "数据库", "其他数据库"],
        "asset_types": ["数据库"],
        "manual_all": True,
    },
}

MYSQL_ACCOUNT_COMMAND = (
    'mysql -N -B -e "SELECT User,Host,plugin,authentication_string,account_locked,'
    "password_expired,Super_priv,Grant_priv,File_priv,Process_priv FROM mysql.user "
    'ORDER BY User,Host;"'
)
MYSQL_PASSWORD_COMMAND = (
    'mysql -N -B -e "SHOW GLOBAL VARIABLES LIKE \'validate_password%\'; '
    'SHOW GLOBAL VARIABLES LIKE \'default_password_lifetime\';"'
)
MYSQL_LOGIN_COMMAND = (
    'mysql -N -B -e "SHOW GLOBAL VARIABLES LIKE \'connection_control%\'; '
    'SHOW GLOBAL VARIABLES LIKE \'interactive_timeout\'; '
    'SHOW GLOBAL VARIABLES LIKE \'wait_timeout\'; '
    "SELECT PLUGIN_NAME,PLUGIN_STATUS FROM information_schema.PLUGINS "
    'WHERE PLUGIN_NAME LIKE \'%connection_control%\';"'
)
MYSQL_REMOTE_COMMAND = (
    'mysql -N -B -e "SHOW GLOBAL VARIABLES LIKE \'%ssl%\'; '
    'SHOW GLOBAL VARIABLES LIKE \'skip_networking\'; '
    'SHOW GLOBAL VARIABLES LIKE \'bind_address\';"'
)
MYSQL_AUDIT_COMMAND = (
    'mysql -N -B -e "SHOW GLOBAL VARIABLES LIKE \'general_log\'; '
    'SHOW GLOBAL VARIABLES LIKE \'slow_query_log\'; '
    'SHOW GLOBAL VARIABLES LIKE \'log_output\'; '
    'SHOW GLOBAL VARIABLES LIKE \'expire_logs_days\'; '
    'SHOW GLOBAL VARIABLES LIKE \'binlog_expire_logs_seconds\'; '
    "SELECT PLUGIN_NAME,PLUGIN_STATUS FROM information_schema.PLUGINS "
    'WHERE PLUGIN_NAME LIKE \'%audit%\';"'
)

ORACLE_SQLPLUS = "| sqlplus -S \"$CALIPER_ORACLE_CONN\""
ORACLE_USER_COMMAND = (
    'printf "set pagesize 200\\nset linesize 200\\n'
    'select username,account_status from dba_users order by username;\\nexit\\n" '
    + ORACLE_SQLPLUS
)
ORACLE_PROFILE_COMMAND = (
    'printf "set pagesize 200\\nset linesize 200\\n'
    "select resource_name,limit from dba_profiles where profile='DEFAULT';\\nexit\\n\" "
    + ORACLE_SQLPLUS
)
ORACLE_AUDIT_PARAM_COMMAND = (
    'printf "set pagesize 200\\nshow parameter audit\\n'
    'show parameter audit_sys_operations\\nexit\\n" ' + ORACLE_SQLPLUS
)
ORACLE_AUDIT_OPT_COMMAND = (
    'printf "set pagesize 200\\nset linesize 300\\n'
    "select * from dba_stmt_audit_opts;\\nselect * from dba_priv_audit_opts;\\nexit\\n\" "
    + ORACLE_SQLPLUS
)
ORACLE_O7_COMMAND = (
    'printf "set pagesize 200\\nshow parameter o7_dictionary_accessibility\\nexit\\n" '
    + ORACLE_SQLPLUS
)

MYSQL_BLOCKS: list[dict[str, Any]] = [
    {
        "title": "MySQL 用户账户与权限",
        "section": "账户、权限与存储",
        "command": MYSQL_ACCOUNT_COMMAND,
        "expect": "每个账户一行：User、Host、plugin、authentication_string、account_locked、password_expired、Super_priv、Grant_priv、File_priv、Process_priv",
        "normalize": "db_mysql_accounts",
        "binds": {
            "AUTH_ID": [1, 2],
            "ACCOUNT_PERM": [2],
            "EXTRA_ACCOUNT": [2],
            "PRIV_SEP": [2],
            "AUDIT_PROTECT": [1],
            "TERMINAL": [1],
            "INTEGRITY_STORE": [1],
            "CONF_STORE": [1],
        },
    },
    {
        "title": "MySQL 口令策略",
        "section": "账户、权限与存储",
        "command": MYSQL_PASSWORD_COMMAND,
        "expect": "validate_password_policy / validate_password_length / validate_password_*_count / default_password_lifetime",
        "normalize": "db_mysql_password_policy",
        "binds": {"AUTH_ID": [4]},
    },
    {
        "title": "MySQL 登录失败与超时",
        "section": "登录控制",
        "command": MYSQL_LOGIN_COMMAND,
        "expect": "connection_control_failed_connections_threshold / connection_control_min_connection_delay / interactive_timeout / wait_timeout",
        "normalize": "db_mysql_login_control",
        "binds": {"LOGIN_FAIL": [1, 2, 3]},
    },
    {
        "title": "MySQL 远程管理加密",
        "section": "传输保护",
        "command": MYSQL_REMOTE_COMMAND,
        "expect": "have_ssl=YES / have_openssl=YES，skip_networking 与 bind_address",
        "normalize": "db_mysql_remote",
        "binds": {
            "REMOTE": [2],
            "INTEGRITY_TRANSFER": [2],
            "CONF_TRANSFER": [2],
        },
    },
    {
        "title": "MySQL 安全审计",
        "section": "安全审计",
        "command": MYSQL_AUDIT_COMMAND,
        "expect": "general_log / slow_query_log / log_output / expire_logs_days / binlog_expire_logs_seconds / audit 插件状态",
        "normalize": "db_mysql_audit",
        "binds": {"AUDIT_ENABLE": [1], "AUDIT_PROTECT": [3]},
    },
]

ORACLE_BLOCKS: list[dict[str, Any]] = [
    {
        "title": "Oracle 用户账户",
        "section": "账户与权限",
        "command": ORACLE_USER_COMMAND,
        "expect": "USERNAME、ACCOUNT_STATUS，例如 OPEN / EXPIRED / EXPIRED & LOCKED",
        "normalize": "oracle_sql",
        "binds": {"AUTH_ID": [2], "EXTRA_ACCOUNT": [2]},
    },
    {
        "title": "Oracle 口令与登录策略",
        "section": "账户与权限",
        "command": ORACLE_PROFILE_COMMAND,
        "expect": "DEFAULT 概要文件的 PASSWORD_LIFE_TIME、FAILED_LOGIN_ATTEMPTS、PASSWORD_LOCK_TIME、IDLE_TIME、PASSWORD_VERIFY_FUNCTION",
        "normalize": "oracle_sql",
        "binds": {"AUTH_ID": [4], "LOGIN_FAIL": [2, 3]},
    },
    {
        "title": "Oracle 审计参数",
        "section": "安全审计",
        "command": ORACLE_AUDIT_PARAM_COMMAND,
        "expect": "audit_trail=DB、audit_sys_operations=TRUE",
        "normalize": "oracle_sql",
        "binds": {"AUDIT_ENABLE": [1]},
    },
    {
        "title": "Oracle 审计策略",
        "section": "安全审计",
        "command": ORACLE_AUDIT_OPT_COMMAND,
        "expect": "dba_stmt_audit_opts / dba_priv_audit_opts 返回已配置的审计策略",
        "normalize": "oracle_sql",
        "kind": "context",
        "binds": {},
    },
    {
        "title": "Oracle 权限分离",
        "section": "访问控制",
        "command": ORACLE_O7_COMMAND,
        "expect": "o7_dictionary_accessibility=FALSE",
        "normalize": "oracle_sql",
        "binds": {"PRIV_SEP": [2]},
    },
]

MYSQL_RULES: list[dict[str, Any]] = [
    {
        "key": "AUTH_ID",
        "point": 1,
        "block": "MySQL 用户账户与权限",
        "expect": {"contains": "fact:db.mysql.users.empty_password.none=true"},
        "pass_reason": "未发现空口令账户，登录用户均需口令鉴别。",
        "fail_reason": "存在空口令账户或无需口令即可登录的账户。",
    },
    {
        "key": "AUTH_ID",
        "point": 2,
        "block": "MySQL 用户账户与权限",
        "expect": {"contains": "fact:db.mysql.users.unique=true"},
        "pass_reason": "mysql.user 中不存在 User+Host 完全相同的账户。",
        "fail_reason": "mysql.user 中存在 User+Host 相同的账户，身份标识不唯一。",
    },
    {
        "key": "AUTH_ID",
        "point": 4,
        "block": "MySQL 口令策略",
        "expect": {
            "all": [
                {"contains": "fact:db.mysql.password_policy.enabled=true"},
                {"gt": {"prefix": "fact:db.mysql.password_policy.length=", "value": 7}},
                {
                    "gt": {
                        "prefix": "fact:db.mysql.password_policy.composition_types=",
                        "value": 2,
                    }
                },
                {"gt": {"prefix": "fact:db.mysql.password_policy.aging_days=", "value": 0}},
                {"lt": {"prefix": "fact:db.mysql.password_policy.aging_days=", "value": 91}},
            ]
        },
        "pass_reason": "已启用口令复杂度校验，长度、组成和有效期满足要求。",
        "fail_reason": "未启用口令复杂度校验，或长度、组成、有效期至少一项不满足要求。",
    },
    {
        "key": "LOGIN_FAIL",
        "point": 1,
        "block": "MySQL 登录失败与超时",
        "expect": {"contains": "fact:db.mysql.login_fail.enabled=true"},
        "pass_reason": "已启用 connection_control 登录失败处理能力。",
        "fail_reason": "未启用连接控制插件，缺少登录失败处理能力。",
    },
    {
        "key": "LOGIN_FAIL",
        "point": 2,
        "block": "MySQL 登录失败与超时",
        "expect": {
            "all": [
                {"gt": {"prefix": "fact:db.mysql.login_fail.attempt=", "value": 0}},
                {"lt": {"prefix": "fact:db.mysql.login_fail.attempt=", "value": 11}},
                {"gt": {"prefix": "fact:db.mysql.login_fail.lock_ms=", "value": 299999}},
            ]
        },
        "pass_reason": "登录失败次数和锁定时间配置合理。",
        "fail_reason": "登录失败次数阈值过大或锁定时间不足。",
    },
    {
        "key": "LOGIN_FAIL",
        "point": 3,
        "block": "MySQL 登录失败与超时",
        "expect": {
            "all": [
                {"lt": {"prefix": "fact:db.mysql.timeout.interactive_seconds=", "value": 1801}},
                {"lt": {"prefix": "fact:db.mysql.timeout.wait_seconds=", "value": 1801}},
            ]
        },
        "pass_reason": "交互连接和空闲连接超时时间不超过 30 分钟。",
        "fail_reason": "交互连接或空闲连接超时时间超过 30 分钟。",
    },
    {
        "key": "REMOTE",
        "point": 2,
        "block": "MySQL 远程管理加密",
        "expect": {"contains": "fact:db.mysql.ssl.enabled=true"},
        "pass_reason": "已启用 SSL/TLS，远程管理数据可加密传输。",
        "fail_reason": "未启用 SSL/TLS，远程管理鉴别信息可能被窃听。",
    },
    {
        "key": "ACCOUNT_PERM",
        "point": 2,
        "block": "MySQL 用户账户与权限",
        "expect": {"contains": "fact:db.mysql.users.anonymous.none=true"},
        "pass_reason": "不存在匿名账户。",
        "fail_reason": "存在匿名账户，可被未授权访问。",
    },
    {
        "key": "EXTRA_ACCOUNT",
        "point": 2,
        "block": "MySQL 用户账户与权限",
        "expect": {"contains": "fact:db.mysql.users.expired.none=true"},
        "pass_reason": "未发现口令已过期仍可使用的账户。",
        "fail_reason": "存在口令已过期账户，账户生命周期管理不到位。",
    },
    {
        "key": "PRIV_SEP",
        "point": 2,
        "block": "MySQL 用户账户与权限",
        "expect": {
            "all": [
                {
                    "contains": "fact:db.mysql.privileges.no_wildcard_super=true"
                },
                {
                    "contains": "fact:db.mysql.privileges.nonroot_file_priv.none=true"
                },
            ]
        },
        "pass_reason": "未发现远端通配账户持有 SUPER 或普通账户持有 FILE 权限。",
        "fail_reason": "存在远端通配账户持有 SUPER 权限，或普通账户持有 FILE 权限。",
    },
    {
        "key": "AUDIT_ENABLE",
        "point": 1,
        "block": "MySQL 安全审计",
        "expect": {"contains": "fact:db.mysql.audit.enabled=true"},
        "pass_reason": "已开启通用查询日志、慢查询日志或审计插件。",
        "fail_reason": "未开启任何审计日志或审计插件。",
    },
    {
        "key": "AUDIT_PROTECT",
        "point": 1,
        "block": "MySQL 用户账户与权限",
        "expect": {
            "contains": "fact:db.mysql.privileges.nonroot_file_priv.none=true"
        },
        "pass_reason": "普通账户不具备 FILE 权限，难以直接删除或覆盖审计文件。",
        "fail_reason": "普通账户具备 FILE 权限，存在删除或覆盖审计文件的风险。",
    },
    {
        "key": "AUDIT_PROTECT",
        "point": 3,
        "block": "MySQL 安全审计",
        "expect": {
            "gt": {"prefix": "fact:db.mysql.audit.retention_days=", "value": 179}
        },
        "pass_reason": "日志保留时间不少于 6 个月。",
        "fail_reason": "日志保留时间不足 6 个月。",
    },
    {
        "key": "TERMINAL",
        "point": 1,
        "block": "MySQL 用户账户与权限",
        "expect": {"contains": "fact:db.mysql.terminal.restricted=true"},
        "pass_reason": "不存在 Host 为 % 的账户，登录来源受到限制。",
        "fail_reason": "存在 Host 为 % 的账户，任意地址均可尝试登录。",
    },
    {
        "key": "INTEGRITY_TRANSFER",
        "point": 2,
        "block": "MySQL 远程管理加密",
        "expect": {"contains": "fact:db.mysql.ssl.enabled=true"},
        "pass_reason": "已启用 SSL/TLS，传输完整性受到保护。",
        "fail_reason": "未启用 SSL/TLS，传输完整性无法保证。",
    },
    {
        "key": "INTEGRITY_STORE",
        "point": 1,
        "block": "MySQL 用户账户与权限",
        "expect": {"contains": "fact:db.mysql.secret.hashed=true"},
        "pass_reason": "账户鉴别信息以哈希形式存储。",
        "fail_reason": "存在明文或可还原形式存储的账户鉴别信息。",
    },
    {
        "key": "CONF_TRANSFER",
        "point": 2,
        "block": "MySQL 远程管理加密",
        "expect": {"contains": "fact:db.mysql.ssl.enabled=true"},
        "pass_reason": "已启用 SSL/TLS，传输数据可加密保护。",
        "fail_reason": "未启用 SSL/TLS，传输数据可能被窃听。",
    },
    {
        "key": "CONF_STORE",
        "point": 1,
        "block": "MySQL 用户账户与权限",
        "expect": {"contains": "fact:db.mysql.secret.hashed=true"},
        "pass_reason": "账户鉴别信息以哈希形式存储，未发现明文口令。",
        "fail_reason": "存在明文或可还原形式存储的账户鉴别信息。",
    },
]

ORACLE_RULES: list[dict[str, Any]] = [
    {
        "key": "AUTH_ID",
        "point": 2,
        "block": "Oracle 用户账户",
        "expect": {"contains": "fact:db.oracle.users.unique=true"},
        "pass_reason": "dba_users 中用户名唯一。",
        "fail_reason": "dba_users 中存在重复用户名，身份标识不唯一。",
    },
    {
        "key": "AUTH_ID",
        "point": 4,
        "block": "Oracle 口令与登录策略",
        "expect": {
            "all": [
                {"contains": "fact:db.oracle.password_policy.verify_function=true"},
                {"gt": {"prefix": "fact:db.oracle.password_policy.life_days=", "value": 0}},
                {"lt": {"prefix": "fact:db.oracle.password_policy.life_days=", "value": 91}},
            ]
        },
        "pass_reason": "DEFAULT 概要文件配置了口令复杂度校验函数，口令有效期不超过 90 天。",
        "fail_reason": "未配置口令复杂度校验函数，或口令未设置有效期、有效期超过 90 天。",
    },
    {
        "key": "LOGIN_FAIL",
        "point": 2,
        "block": "Oracle 口令与登录策略",
        "expect": {
            "all": [
                {"gt": {"prefix": "fact:db.oracle.login_fail.attempt=", "value": 0}},
                {"lt": {"prefix": "fact:db.oracle.login_fail.attempt=", "value": 11}},
                {"contains": "fact:db.oracle.login_fail.locked=true"},
            ]
        },
        "pass_reason": "登录失败次数限制不超过 10 次，且失败后账户会被锁定。",
        "fail_reason": "未限制登录失败次数、阈值超过 10 次或失败后未设置账户锁定。",
    },
    {
        "key": "LOGIN_FAIL",
        "point": 3,
        "block": "Oracle 口令与登录策略",
        "expect": {
            "lt": {"prefix": "fact:db.oracle.timeout.idle_minutes=", "value": 31}
        },
        "pass_reason": "空闲会话超时时间不超过 30 分钟。",
        "fail_reason": "未设置空闲会话超时或超过 30 分钟。",
    },
    {
        "key": "EXTRA_ACCOUNT",
        "point": 2,
        "block": "Oracle 用户账户",
        "expect": {"contains": "fact:db.oracle.users.expired.none=true"},
        "pass_reason": "未发现 EXPIRED 状态的账户。",
        "fail_reason": "存在 EXPIRED 状态账户，未及时清理或续期。",
    },
    {
        "key": "AUDIT_ENABLE",
        "point": 1,
        "block": "Oracle 审计参数",
        "expect": {"contains": "fact:db.oracle.audit.enabled=true"},
        "pass_reason": "audit_trail 已设置为 DB，数据库审计已开启。",
        "fail_reason": "audit_trail 未设置为 DB，数据库审计未开启。",
    },
    {
        "key": "PRIV_SEP",
        "point": 2,
        "block": "Oracle 权限分离",
        "expect": {
            "contains": "fact:db.oracle.privileges.o7_dictionary=false"
        },
        "pass_reason": "O7_DICTIONARY_ACCESSIBILITY 为 FALSE，数据字典访问受限。",
        "fail_reason": "O7_DICTIONARY_ACCESSIBILITY 为 TRUE，普通权限用户可访问数据字典。",
    },
]

# Oracle 指导书只给出用户、概要文件和审计参数查询；其余实施点按人工核查保留。
ORACLE_MANUAL_BY_LEVEL: dict[int, dict[str, list[tuple[int, str]]]] = {
    2: {
        "AUTH_ID": [(1, "Oracle 不允许空口令账户，但仍需现场确认不存在免口令登录方式")],
        "LOGIN_FAIL": [(1, "登录失败处理功能是否可用需结合测试确认")],
        "ACCOUNT_PERM": [(2, "是否存在匿名或共享账户需结合用户清单访谈确认")],
        "AUDIT_PROTECT": [
            (1, "普通权限用户能否删除审计记录需现场测试"),
            (3, "审计记录备份与保留时间需访谈并查看备份记录"),
        ],
        "TERMINAL": [(1, "是否限制允许登录的地址范围需查看 sqlnet.ora 或访谈确认")],
        "REMOTE": [(2, "远程管理是否启用加密需查看 sqlnet.ora 的加密配置")],
        "INTEGRITY_TRANSFER": [(2, "远程管理传输完整性保护需查看 sqlnet.ora 配置")],
    },
    3: {
        "AUTH_ID": [(1, "Oracle 不允许空口令账户，但仍需现场确认不存在免口令登录方式")],
        "LOGIN_FAIL": [(1, "登录失败处理功能是否可用需结合测试确认")],
        "ACCOUNT_PERM": [(2, "是否存在匿名或共享账户需结合用户清单访谈确认")],
        "AUDIT_PROTECT": [
            (1, "普通权限用户能否删除审计记录需现场测试"),
            (3, "审计记录备份与保留时间需访谈并查看备份记录"),
        ],
        "TERMINAL": [(1, "是否限制允许登录的地址范围需查看 sqlnet.ora 或访谈确认")],
        "REMOTE": [(2, "远程管理是否启用加密需查看 sqlnet.ora 的加密配置")],
        "INTEGRITY_TRANSFER": [(2, "远程管理传输完整性保护需查看 sqlnet.ora 配置")],
        "INTEGRITY_STORE": [(1, "业务数据是否加密存储需结合表空间和文件核查")],
        "CONF_TRANSFER": [(2, "远程管理传输保密性保护需查看 sqlnet.ora 配置")],
        "CONF_STORE": [(1, "业务数据是否加密存储需结合表空间和文件核查")],
    },
}
ORACLE_MANUAL_BY_LEVEL[4] = ORACLE_MANUAL_BY_LEVEL[3]

NEUTRAL_ACTIONS = {
    "AUTH_ID": "建议为每个数据库账户设置唯一用户名和满足复杂度要求的口令，并启用口令有效期与登录失败处理策略。",
    "LOGIN_FAIL": "建议启用登录失败锁定、登录超时自动退出等登录失败处理措施。",
    "REMOTE": "建议仅启用加密的远程管理方式，关闭明文管理协议。",
    "ACCOUNT_PERM": "建议按岗位分配账户和最小权限，删除匿名或共享账户。",
    "DEFAULT": "建议重命名或删除默认账户，并修改默认口令。",
    "EXTRA_ACCOUNT": "建议删除或禁用多余、过期账户，并定期核查账户清单。",
    "PRIV_SEP": "建议划分系统管理员、安全管理员和审计管理员等角色，实现权限分离。",
    "ACCESS_POLICY": "建议制定并落实数据库访问控制策略，按默认拒绝原则授权。",
    "ACCESS_GRANULARITY": "建议按最小权限细化访问控制粒度，避免过宽授权。",
    "SECURITY_MARK": "建议对重要数据设置安全标记，并基于标记实施访问控制。",
    "AUDIT_ENABLE": "建议启用数据库审计功能，确保审计覆盖每个用户和重要安全事件。",
    "AUDIT_CONTENT": "建议审计记录覆盖日期时间、用户、事件类型、结果等必要内容。",
    "AUDIT_PROTECT": "建议将审计记录备份至日志服务器，并限制审计记录访问。",
    "AUDIT_PROCESS": "建议对审计记录进行保护，避免未预期的删除、修改或覆盖。",
    "TERMINAL": "建议通过地址白名单限制允许登录数据库的终端范围。",
    "INPUT": "建议对输入数据进行有效性校验，避免注入等输入验证缺陷。",
    "VULN": "建议及时修补数据库已知漏洞，并关闭不必要的组件与端口。",
    "INTRUSION_DETECT": "建议部署入侵检测或防御能力，并在发生严重入侵事件时提供报警。",
    "MALWARE": "建议部署恶意代码检测与防范措施，并及时更新特征库。",
    "TRUST": "建议基于可信根对数据库程序与重要配置进行可信验证。",
    "INTEGRITY_TRANSFER": "建议使用加密协议传输数据库管理数据，保证传输完整性。",
    "INTEGRITY_STORE": "建议账户口令以不可逆加密形式存储，重要业务数据采用校验机制。",
    "NON_REPUDIATION": "建议通过安全审计与数字签名等手段保证重要操作不可否认。",
    "CONF_TRANSFER": "建议使用加密协议传输数据库管理数据。",
    "CONF_STORE": "建议账户口令以不可逆加密形式存储，重要业务数据加密存储。",
    "BACKUP_LOCAL": "建议定期备份数据库与配置，并对备份文件采取保护措施。",
    "BACKUP_OFFSITE": "建议在异地保存重要数据备份，避免单点灾难导致数据丢失。",
    "HOT_REDUNDANCY": "建议对关键数据库提供热冗余或高可用能力，避免单点故障。",
    "DR_CENTER": "建议建立异地灾难备份中心，保证重要数据可在灾难后恢复。",
    "RESIDUAL": "建议在数据库退役或介质复用前彻底清除剩余信息。",
    "RESIDUAL_STORAGE": "建议对存储介质中的临时文件进行清除或安全删除。",
    "RESIDUAL_CLEAR": "建议在数据库退役或介质复用前彻底清除剩余信息。",
    "PERSONAL_COLLECT": "建议仅采集业务必需的个人信息，并取得授权后处理。",
    "PERSONAL_USE": "建议限制个人信息访问范围，防止未授权访问或披露。",
}

BLOCK_NAMES: dict[str, str] = {
    "mysql": "MySQL",
    "oracle": "Oracle",
    "sqlserver": "SQL Server",
}


def _all_records(guide: Path) -> list[dict]:
    return json.loads(guide.read_text(encoding="utf-8"))["records"]


def _unit(record: dict) -> int:
    match = re.search(r"(\d+)$", str(record["unit_no"]))
    if not match:
        raise ValueError(f"无法解析单元编号：{record['unit_no']}")
    return int(match.group(1))


def keys_for(engine: str, level: int) -> dict[int, str]:
    """返回该引擎该等级的 unit → 主题键；Oracle/SQL Server 四级从 unit 22 起前移一位。"""
    base = LEVEL_KEYS[level]
    if level != 4 or engine in {"mysql", "generic"}:
        return base
    shifted = {unit: key for unit, key in base.items() if unit < 22}
    shifted.update({unit: base[unit + 1] for unit in range(22, 36) if unit + 1 in base})
    return shifted


def _records(records: list[dict], level: int, engine: str) -> list[dict]:
    obj = ENGINES[engine]["guide_object"]
    selected = [
        record
        for record in records
        if int(record["level"]) == level and record["object"] == obj
    ]
    return sorted(selected, key=_unit)


def seq_by_key(records: list[dict], level: int) -> dict[str, int]:
    """以 MySQL 指导书为共享测评项基线，返回主题键 → 连续 seq。"""
    mapping: dict[str, int] = {}
    for index, record in enumerate(_records(records, level, "mysql"), 1):
        mapping[keys_for("mysql", level)[_unit(record)]] = index
    return mapping


def _split_guide(body: str) -> tuple[str, str]:
    criteria = ""
    match = re.search(r"\n\s*判定[：:]\s*", body)
    if match:
        criteria = body[match.end() :]
        body = body[: match.start()]
    criteria = re.split(r"\n\s*版本差异", criteria)[0].strip()
    return body.strip(), criteria or "依据指导书判定标准执行。"


def _manual_points(level: int, seqs: dict[str, int]) -> dict[str, list[dict[str, Any]]]:
    points: dict[str, list[dict[str, Any]]] = {}
    for key, numbers in SHARED_MANUAL_POINTS.items():
        if key not in seqs:
            continue
        entries = []
        for number in numbers:
            reason = MANUAL_REASONS.get((key, number))
            if reason:
                entries.append({"point": number, "reason": reason})
        if entries:
            points[key] = entries
    return points


def build_items(records: list[dict], level: int) -> list[dict]:
    seqs = seq_by_key(records, level)
    manual_by_key = _manual_points(level, seqs)
    items: list[dict] = []
    for index, record in enumerate(_records(records, level, "mysql"), 1):
        key = keys_for("mysql", level)[_unit(record)]
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
            "seq": index,
            "unit_no": _unit(record),
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
        if key in manual_by_key:
            item["manual_points"] = manual_by_key[key]
        items.append(item)
    _assert_keys_match(seqs, [keys_for("mysql", level)[_unit(r)] for r in _records(records, level, "mysql")])
    return items


def _assert_keys_match(mapping: dict[str, int], keys: list[str]) -> None:
    if set(mapping) != set(keys):
        missing = sorted(set(keys) - set(mapping))
        raise ValueError(f"主题键与共享测评项不一致：{missing}")


def _checks(engine: str, blocks: list[dict], seqs_by_level: dict[int, dict[str, int]]) -> list[dict]:
    levels = list(LEVELS)
    checks: list[dict] = []
    for block in blocks:
        binds: list[dict] = []
        for key, points in block["binds"].items():
            for level in levels:
                seq = seqs_by_level[level].get(key)
                if seq is None:
                    continue
                binds.append({"item": seq, "level": level, "points": list(points)})
        if not binds and block.get("kind") != "context":
            continue
        checks.append(
            {
                "title": block["title"],
                "section": "",
                "block_index": len(checks) + 1,
                "kind": block.get("kind", "judge"),
                "normalize": block["normalize"],
                "binds": binds,
            }
        )
    return checks


def _rules(
    engine: str, specs: list[dict], seqs: dict[str, int], level: int
) -> list[dict]:
    rules: list[dict] = []
    for spec in specs:
        seq = seqs.get(spec["key"])
        if seq is None:
            continue
        rules.append(
            {
                "rule_id": f"DB-{engine.upper()}-L{level}-{spec['key']}-P{spec['point']:02d}-{len(rules) + 1:02d}",
                "level": level,
                "item": seq,
                "point": spec["point"],
                "block": spec["block"],
                "expect": json.loads(json.dumps(spec["expect"])),
                "pass_reason": spec["pass_reason"],
                "fail_reason": spec["fail_reason"],
            }
        )
    return rules


def _capture(blocks: list[dict]) -> dict:
    return {
        "version": "0.1.0",
        "status": "active",
        "rules": [
            {
                "section": block["section"],
                "title": block["title"],
                "command": block["command"],
                "expect": block["expect"],
                "levels": list(LEVELS),
                "families": ["database"],
            }
            for block in blocks
        ],
    }


def _texts(records: list[dict]) -> list[dict]:
    entries: list[dict] = []
    seen: set[str] = set()
    for engine in ENGINES:
        for level in LEVELS:
            for record in _records(records, level, engine):
                control_item = str(record["item_text"]).strip()
                if control_item in seen:
                    continue
                seen.add(control_item)
                entries.append(
                    {
                        "seq": len(entries) + 1,
                        "control_point": str(record["control_point"]).strip(),
                        "control_item": control_item,
                        "issue_summary": str(record.get("problem") or "").strip(),
                        "issue_detail": "",
                        "hazard": str(record.get("harm") or "").strip(),
                        "remediation": str(record.get("remediation") or "").strip(),
                        "threat": str(record.get("threat") or "").strip(),
                        "inherent_risk": str(record.get("risk_value") or "").strip(),
                    }
                )
    return entries


def _remediation(engine: str, records: list[dict]) -> dict:
    rules: list[dict] = []
    for level in LEVELS:
        seqs = seq_by_key(records, level)
        for record in _records(records, level, engine):
            key = keys_for(engine, level)[_unit(record)]
            seq = seqs.get(key)
            if seq is None:
                continue
            if engine == "generic":
                action = NEUTRAL_ACTIONS.get(key, "建议按指导书要求完善数据库安全配置。")
                problem = f"{record['control_point']}相关配置不符合指导书要求。"
            else:
                action = str(record.get("remediation") or "").strip() or NEUTRAL_ACTIONS.get(
                    key, "建议按指导书要求完善数据库安全配置。"
                )
                problem = str(record.get("problem") or "").strip() or (
                    f"{record['control_point']}相关配置未满足指导书要求。"
                )
            priority = str(record.get("risk_value") or "").strip()
            if priority not in {"高", "中", "低"}:
                priority = "中"
            rules.append(
                {
                    "id": f"REM-{engine.upper()}-L{level}-{seq:02d}",
                    "title": f"{str(record['control_point']).strip()}整改",
                    "applies_to": {
                        "level": [level],
                        "family": ["database"],
                        "item_seqs": [seq],
                    },
                    "priority": priority,
                    "problem": problem,
                    "cause": "数据库安全基线未配置或配置未落到该实例。",
                    "action": action,
                    "clause": str(record["item_text"]).strip(),
                }
            )
    return {"version": "0.1.0", "status": "active", "rules": rules}


def _high_risk(records: list[dict]) -> list[dict]:
    source = yaml.safe_load(
        (NETWORK_PACK / "adapters" / "h3c" / "high_risk.yaml").read_text(encoding="utf-8")
    )
    binds: dict[str, list[str]] = {
        "HR-01": ["AUTH_ID"],
        "HR-02": ["REMOTE"],
        "HR-03": ["TWO_FACTOR"],
        "HR-04": ["DEFAULT", "EXTRA_ACCOUNT"],
        "HR-05": ["ACCOUNT_PERM", "PRIV_SEP", "ACCESS_POLICY", "ACCESS_GRANULARITY"],
        "HR-06": ["CLOSE_SERVICES", "MIN_INSTALL"],
        "HR-07": ["VULN"],
        "HR-08": ["INPUT"],
        "HR-09": ["MALWARE"],
        "HR-10": ["INTEGRITY_TRANSFER", "CONF_TRANSFER"],
        "HR-11": ["INTEGRITY_STORE", "CONF_STORE"],
        "HR-12": ["BACKUP_LOCAL", "BACKUP_OFFSITE"],
        "HR-13": ["HOT_REDUNDANCY"],
        "HR-14": ["DR_CENTER"],
        "HR-15": ["PERSONAL_COLLECT"],
        "HR-16": ["PERSONAL_USE"],
    }
    seqs_by_level = {level: seq_by_key(records, level) for level in LEVELS}
    result: list[dict] = []
    for entry in source:
        keys = binds.get(str(entry.get("hr_id")), [])
        per_level = {
            str(level): [
                seqs_by_level[level][key] for key in keys if key in seqs_by_level[level]
            ]
            for level in LEVELS
        }
        per_level = {level: seqs for level, seqs in per_level.items() if seqs}
        if not per_level:
            continue
        clone = dict(entry)
        clone.pop("binds_items", None)
        clone["level_min"] = min(int(level) for level in per_level)
        clone["binds"] = per_level
        result.append(clone)
    return result


def _dump(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )


def _adapter_meta(engine: str, seqs_by_level: dict[int, dict[str, int]]) -> dict:
    meta = ENGINES[engine]
    payload = {
        "name": meta["name"],
        "vendor": meta["vendor"],
        "aliases": meta["aliases"],
        "levels": list(LEVELS),
        "asset_types": meta["asset_types"],
    }
    if meta.get("manual_all"):
        payload["manual_all"] = True
    if engine == "oracle":
        by_level: dict[int, dict[int, list[dict[str, Any]]]] = {}
        for level in LEVELS:
            seqs = seqs_by_level[level]
            entries_by_seq: dict[int, list[dict[str, Any]]] = {}
            for key, entries in ORACLE_MANUAL_BY_LEVEL[level].items():
                seq = seqs.get(key)
                if seq is None:
                    continue
                entries_by_seq.setdefault(seq, []).extend(
                    {"point": point, "reason": reason} for point, reason in entries
                )
            by_level[level] = entries_by_seq
        payload["manual_points_by_level"] = by_level
    return payload


def _coverage(
    records: list[dict], engine: str, level: int, seqs_by_level: dict[int, dict[str, int]]
) -> str:
    meta = ENGINES[engine]
    seqs = seqs_by_level[level]
    items = build_items(records, level)
    if engine == "mysql":
        specs = MYSQL_RULES
    elif engine == "oracle":
        specs = ORACLE_RULES
    else:
        specs = []
    rules = _rules(engine, specs, seqs, level) if specs else []
    adapter_meta = _adapter_meta(engine, seqs_by_level)
    extra_manual = adapter_meta.get("manual_points_by_level", {}).get(level, {})
    lines = [
        f"# {meta['name']} {level} 级数据库规则域覆盖报告",
        "",
        "本报告由 `tools/build_database_pack.py` 从数据库指导书自动生成。",
        "采集命令、判定规则与人工核查点只适用于本引擎，不能复制给其他引擎。",
    ]
    if meta.get("manual_all"):
        lines.append("")
        lines.append(
            "该引擎指导书未提供可直接执行的采集命令，整包按人工核查模板处理。"
        )
    lines.extend(
        [
            "",
            "| 项 | 控制点 | 模式 | 自动实施点 | 人工核查点 |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for item in items:
        seq = item["seq"]
        auto_points = sorted({rule["point"] for rule in rules if rule["item"] == seq})
        manual_points = {entry["point"] for entry in item.get("manual_points", [])}
        manual_points.update(
            entry["point"] for entry in extra_manual.get(seq, [])
        )
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


def build(guide: Path, out: Path) -> None:
    records = _all_records(guide)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    for level in LEVELS:
        _dump(out / f"items_L{level}.yaml", build_items(records, level))

    seqs_by_level = {level: seq_by_key(records, level) for level in LEVELS}
    all_texts = _texts(records)
    # 根级整改建议使用通用模板，供未指定适配器的调用方回退；不含任何厂商命令。
    _dump(out / "remediation.yaml", _remediation("generic", records))

    _dump(
        out / "pack.yaml",
        {
            "name": "database",
            "version": "0.1.0",
            "levels": list(LEVELS),
            "os_family": ["database"],
            "asset_types": ["数据库"],
            "guides": [
                "二级-安全通用要求",
                "三级-安全通用要求",
                "四级-安全通用要求",
            ],
            "items": {
                f"level_{level}": f"items_L{level}.yaml" for level in LEVELS
            },
            "adapters": {
                "mysql": "adapters/mysql",
                "oracle": "adapters/oracle",
                "sqlserver": "adapters/sqlserver",
                "generic": "adapters/generic",
            },
            "default_adapter": "generic",
        },
    )
    _dump(
        out / "library.yaml",
        {
            "version": "0.1.0",
            "libraries": {
                "capture": {
                    "title": "数据采集命令库",
                    "status": "active",
                    "paths": [
                        "adapters/mysql/capture.yaml",
                        "adapters/oracle/capture.yaml",
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
                        f"adapters/{engine}/rules/level{level}.yaml"
                        for engine in ("mysql", "oracle")
                        for level in LEVELS
                    ],
                },
                "remediation": {
                    "title": "风险分析与整改建议库",
                    "status": "active",
                    "paths": [
                        f"adapters/{engine}/remediation.yaml"
                        for engine in ("mysql", "oracle", "sqlserver", "generic")
                    ],
                },
                "high_risk": {
                    "title": "高风险判定规则库",
                    "status": "active",
                    "paths": [
                        "adapters/mysql/high_risk.yaml",
                        "adapters/oracle/high_risk.yaml",
                    ],
                },
                "major": {
                    "title": "重大风险隐患规则库",
                    "status": "active",
                    "paths": [
                        "adapters/mysql/major.yaml",
                        "adapters/oracle/major.yaml",
                    ],
                },
            },
        },
    )
    shutil.copyfile(NETWORK_PACK / "record.yaml", out / "record.yaml")

    for engine in ENGINES:
        root = out / "adapters" / engine
        _dump(root / "adapter.yaml", _adapter_meta(engine, seqs_by_level))
        _dump(root / "remediation.yaml", _remediation(engine, records))
        if ENGINES[engine].get("manual_all"):
            continue
        if engine == "mysql":
            blocks = MYSQL_BLOCKS
            specs = MYSQL_RULES
        else:
            blocks = ORACLE_BLOCKS
            specs = ORACLE_RULES
        _dump(root / "checks_map.yaml", {"checks": _checks(engine, blocks, seqs_by_level)})
        _dump(root / "capture.yaml", _capture(blocks))
        _dump(root / "texts" / "library.yaml", {"texts": all_texts})
        high_risk = _high_risk(records)
        _dump(root / "high_risk.yaml", high_risk)
        shutil.copyfile(NETWORK_PACK / "adapters" / "h3c" / "major.yaml", root / "major.yaml")
        for level in LEVELS:
            _dump(
                root / "rules" / f"level{level}.yaml",
                {"rules": _rules(engine, specs, seqs_by_level[level], level)},
            )

    # SQL Server 与通用模板也保留文案，便于人工核查时生成问题描述。
    for engine in ("sqlserver", "generic"):
        _dump(out / "adapters" / engine / "texts" / "library.yaml", {"texts": all_texts})

    reports = REPO_ROOT / "guides" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    for engine in ENGINES:
        for level in LEVELS:
            (reports / f"database_{engine}_L{level}.md").write_text(
                _coverage(records, engine, level, seqs_by_level),
                encoding="utf-8",
            )

def main() -> None:
    parser = argparse.ArgumentParser(description="生成数据库设备规则域")
    parser.add_argument("--guide", type=Path, default=REPO_ROOT / "guides" / "database.json")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "packs" / "database")
    args = parser.parse_args()
    build(args.guide, args.out)
    print(f"已生成 {args.out}")


if __name__ == "__main__":
    main()
