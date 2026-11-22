# FORMAT · 四表字段来源与版式口径

> 本文件只记录"每列谁来填"与版式常量来源；列名、列序、表头文案以 `templates/` 母版与 `core/contracts/columns.py` 为准，二者不一致时 `make contracts` 直接失败。

## 1. 资产记录表（18 列）

| 列 | 来源 | 说明 |
|---|---|---|
| 设备名称、IP地址、重要程度、作业指导书、测评对象、数量（台/套）、是否虚拟设备、是否热备、物理/逻辑区域、操作系统及版本、数据库管理系统及版本、中间件及版本、所属业务应用系统/平台名称、是否为测试环境 | 人工 | 读入后只补空白，不覆盖人工值 |
| 备注、扫描对象类型、行标注色、扫描地址 | 人工（可空） | 校验必填：设备名称 / IP地址 / 重要程度 / 作业指导书；IP 不得重复；指导书须在注册列表 |

原文件永不修改，输出为补全版副本。

工具按「设备名称」匹配项目资产（设备名称为空时按 IP 匹配）：只填空白单元格；
人工值与项目配置不一致时保留人工值并在报告里提示「不允许覆盖」；项目里存在、
原表里没有的资产追加到第一个空行。导出前校验必填项、IP 合法性、重复 IP 与
作业指导书注册列表（`pack.yaml` 的 `guides`），有错误则不生成文件。

## 2. 结果记录表（每设备×指导书一个 sheet）

| 区域 | 来源 | 说明 |
|---|---|---|
| B2/E2、B3/E3、B4/E4、B5/E5 八个字段标签 | 母版 | 只读，不改文案；对应合并填充区 C2:D2、F2:G2 … F5:G5 |
| C2:D2 项目编号、F2:G2 系统名称、C3:D3 核查对象、F3:G3 安全层面/安全类、C4:D4 IP地址、F4:G4 资产类别、C5:D5 核查时间、F5:G5 测评作业指导书 | 自动（允许为空） | 取项目与资产信息；为空只提示不阻止导出 |
| 第 7 行 9 列 | 母版 | 序号 / 控制点 / 控制项 / 结果记录 / 符合情况 / 备注 / 重要程度 / 检查内容 / 判断标准 |
| A8:I8 | 母版 | 合并文本「安全通用要求」 |
| 序号、控制点、控制项、重要程度、检查内容、判断标准 | 自动 | 来自 `packs/linux_os/items_L3.yaml`（34 行）或 `items_L2.yaml`（23 行），逐字一致 |
| 结果记录 | 自动 | 证据摘要与锚点；未采集留空 |
| 符合情况 | 自动 | 仅五种：`符合(1分)` / `部分符合(0.5分)` / `不符合(0分)` / `不适用` / 空；公司记录表另行收敛为四种字面值，见第 13 节 |
| 备注 | 自动 + 人工 | 未采集写 `未采集：<原因>`；人工可补 |

版式常量见 `core/contracts/layout.py`：列宽 A 9.5 / B 28.5 / C 38 / D 33.1640625 / E 28.5 / F 33.1640625 / G 14.1640625；表头行 2–5、7 行高 16；数据行高自适应；细边框、自动换行、垂直居中。

### 文本比对归一化

母版单元格内的换行以 `_x000D_` 转义存储，`items_L3.yaml` 使用纯换行。契约检查在比较前统一去掉 `_x000D_` 并把 CRLF 归一为 LF，除此之外逐字比较（含行尾空格）。

## 3. 安全问题汇总（25 列）

| 来源 | 列 |
|---|---|
| 自动 | 问题编号、安全要求（=安全通用要求）、安全层面（=安全计算环境）、安全控制点、测评项、资产类型、关联资产、问题概述、问题详述、危害分析、整改建议、关联威胁、原始风险、整改状态（=未整改）、影响的网络区域 |
| 人工 | 修正后风险、修正原因、修正类型、严重程度变化、整改后风险、修正因子、补充措施、是否触发高风险判例、是否符合重大判定原则、不符合原因分析 |

一行 = 一个测评项 × 一个资产类型；同项跨类型共用 `T` 编号（T001 起，按首次出现顺序）；关联资产用顿号连接；空值写空字符串；只收不符合 / 部分符合。样式：表头加粗 11 号居中换行细边框，全列宽 20，表头行高 23。

## 4. 重大安全隐患（19 列）

| 来源 | 列 |
|---|---|
| 自动 | 序号、安全要求、安全层面、安全控制点、测评项、资产类型、关联资产、问题概述、重大风险隐患触发项、整改建议、是否整改（=未整改）、安全问题属性（=安全技术）、影响的网络区域 |
| 人工 | 相关性、严重性、高发性、后果分析、综合分析、整改情况 |

入表门槛：人工把该问题的「是否符合重大判定原则」填为「符合」才进表；高风险命中只是候选。

## 5. 文件名

```
服务器_存储设备_资产记录表.xlsx
服务器_存储设备_结果记录表.xlsx
【安全问题汇总】_<项目编号>_<系统名称>测评_<YYYY-MM-DD>_<HHMMSS>.xlsx
【重大安全隐患】_<项目编号>_<系统名称>测评_<YYYY-MM-DD>_<HHMMSS>.xlsx
```

项目编号为空写 `未填写`。

## 6. pack 字段口径

- `items_L3.yaml`：`item_id / level / seq / unit_no / 控制点 / 控制项 / 重要程度 / 检查内容 / 判断标准 / policy / mode / binary / optional_clause`，34 项由 `docs/inputs/items_L3.csv` 逐字生成。
- `items_L2.yaml`：L2-CES1-01..23 手工录入；控制点分布 3/4/3/5/1/1/1/2/1/2；二值 8 项（03/05/09/13/14/18/20/21）；可信验证（17）为可选条款。
- `mode`：`auto` 可由采集证据判定；`manual` 需访谈或外部证据（如双因素、可信验证、数据保密性、备份恢复、热冗余）；`na` 默认不适用。
- `checks_map.yaml`：63 条检查块映射；61 条同时适配 Debian/RHEL（服务器基线 44 块、中间件与数据库扩展 17 块），2 条为 RHEL 专属；`kind: context` 的块只提供上下文，不参与判定。
- `high_risk.yaml`：16 条，`level_min` 按 `docs/inputs/high_risk_guide.xlsx` 的适用范围修正（HR-14 为四级）。
- `texts/library.yaml`：321 条文案，仅作默认建议，不参与判定。

## 7. 证据格式

支持两种装载方式，界面按所选目录自动判断：

### 7.1 结构化证据包（可自动判定）

```
pkg-<资产编号>/
  manifest.json
  raw/*.log          # 采集脚本原始输出（必需其一）
  checks/*.json      # 可选，优先于 raw
```

`manifest.json` 必需字段：`package_id / asset_id / collected_at / collector / host / os_family / level / files / status`。
`os_family` 只允许 `debian`、`rhel`；`level` 只允许 2、3；`files` 为 `{相对路径: sha256}`，装载时逐个校验。
`status` 非 `ok`/`collected` 时整包按未采集处理。

### 7.2 原始证据目录 / 单个文件（无需 manifest）

- 可直接选择采集日志目录，或单个 `.log / .txt / .out / .cmd` 文件；
- 文本文件递归扫描，按行状态机识别 `===== RESULTS (collected) =====` 结果段中的检查块；
- `.png / .jpg / .jpeg / .bmp / .gif / .webp / .heic` 计入证据附件，不参与自动判定；
- `manifest.json` 存在但校验失败时，自动回退按原始日志解析，并在诊断信息中提示；
- 未识别到检查块时，所有测评项按未采集处理（备注「未采集：<原因>」）；
- 没有结果段标记的普通命令输出、访谈记录等，目前只作为附件留存，不参与自动判定。

`checks/*.json` 推荐格式（每个文件一组块）：

```json
{"blocks": [
  {"block_index": 1, "section": "1. SYSTEM", "title": "Host / OS / kernel / time",
   "os_family": "debian", "status": "collected", "cmd": ["hostnamectl"],
   "file": ["/etc/os-release"],
   "output": [{"line": 288, "text": "Operating System: Ubuntu 24.04"}]}
]}
```

`output` 也允许直接写字符串列表（行号按 1 起顺延）。

## 8. 项目文件（project.yaml）

```yaml
project_code: "示例-2026-001"   # 可为空
system_name: "示例系统A"        # 可为空
level: 3                        # 2 或 3
check_date: "2026-11-21"
evidence_root: "../evidence"    # 相对路径按本文件所在目录解析
output_dir: "../../out"
pack_dir: "../../packs/linux_os"
assets:
  - device_name: "示例系统A-应用服务器"
    ip: "192.0.2.10"
    importance: "一般"           # 关键 / 重要 / 一般
    guide: "三级-安全通用要求"
    asset_type: "服务器"          # 服务器 / 存储设备
    evidence_package: "pkg-A01"  # 可留空；相对证据根目录或写绝对路径
```

## 9. 规则文件（packs/<pack>/rules/level3.yaml）

文件名必须是 `level2.yaml` 或 `level3.yaml`，规则按文件归到对应等级。

```yaml
rules:
  - item: 1            # 测评项 seq
    point: 1           # 实施点序号
    block: Duplicate UID / UID=0 accounts   # checks_map 里的检查块标题
    expect: {contains: "no duplicate uid"}  # 条件 DSL
    pass_reason: 未发现重复 UID
    fail_reason: 存在重复 UID，身份标识不唯一
```

同一实施点可写多条规则（不同检查块，AND 合成）；未覆盖 checks_map 的全部实施点时整项按未采集处理。
条件只允许 `all / any / eq / ne / in / not_in / contains / not_contains / exists / not_exists / regex_empty / gt / lt`，嵌套最多两层；
`gt/lt` 写法为 `{gt: {prefix: "PASS_MAX_DAYS", value: 90}}`，只比较以 `prefix` 开头的行的第一个数字。

`checks_map.yaml` 的每条 bind 可带 `level`（省略时为 3），同一个检查块可同时服务两级：

```yaml
binds:
  - {item: 1, points: [1, 2]}             # 三级 item 1 的实施点 1、2
  - {item: 1, level: 2, points: [2]}      # 二级 L2-CES1-01 的实施点 2
```

二级需要账户台账、访谈或外部报告的 L2-05/06/18/19/20 标 `mode: manual`，不写自动规则；
L2-14 的判据是「默认不适用」，`policy` 与 `mode` 均为 `na`，直接输出「不适用」。

## 10. 校正与备注（corrections.db）

存于项目文件同目录，sqlite 表 `corrections(level, item_id, asset_type, field, value, reason, updated_at)`，
主键为 `level + item_id + asset_type + field`：

- `field=note`：人工备注，运行判定后自动回填结果记录表的备注列。
- `field=major`：值为 `1` 表示人工确认符合重大判定原则，问题汇总与重大隐患导出都以它为准。
- 删除记录 = 写入空值；`reason` 上限 500 字。

## 11. 金标准用例（fixtures/golden/）

```
fixtures/golden/<用例>/
  project.yaml        # 路径按该文件所在目录解析
  assets.xlsx         # 可选，资产记录表原表
  expected/
    result.xlsx       # 期望表，固定四个文件名
    asset.xlsx
    issue.xlsx
    major.xlsx
```

`caliper golden` 重新运行用例并把四张表与 `expected/` 逐单元格比对；`--update` 以当前输出刷新期望表。
期望表含项目与资产信息，按红线不入库。金标准只覆盖规则输出：人工备注与重大确认不参与，保证结果可复现。

## 12. 采集脚本输出格式

`caliper capture`（`python -m core.cli capture --pack packs/linux_os --family server --level 3`）
生成的脚本既是可执行的 POSIX shell 脚本，也是解析器可直接读取的日志。静态结构写在带引号的
heredoc 中，命令输出用 `sed 's/^/  /'` 统一加两空格缩进，因此「执行」与「解析」共用同一份结构，
不存在两套模板。

### 12.1 骨架

```sh
#!/bin/sh
# Caliper 数据采集脚本
# 仅供已授权环境使用；请只在取得书面授权的资产上执行，采集内容仅用于等保测评。
# ===== Ubuntu/Debian baseline check (family=server, level=3) =====
...
===== RESULTS (collected) =====
===== 2. IDENTIFICATION =====
[01] Duplicate UID / UID=0 accounts
  cmd: cut -d: -f3 /etc/passwd | sort | uniq -d; awk -F: '$3==0{print $1}' /etc/passwd
  file: /etc/passwd
  no duplicate uid
  UID=0: <账号占位>
...
===== END OF REPORT =====
```

上面的片段省略了 heredoc 与重定向；真实脚本中 `===== RESULTS (collected) =====` 之前的内容
在运行时写入同一缓冲区，保证日志开头仍保留脚本标识。

### 12.2 约定与解析器对应关系

| 日志文本 | 解析器行为 | 对应模型 |
|---|---|---|
| `# ===== ... baseline check (family=server, level=3) =====` | 结果段之前扫描，按 `ubuntu/debian` → `debian`、`centos/rhel/red hat` → `rhel` 记录系统类型 | 检查块 `os_family`、证据包 `manifest.os_family` |
| `===== RESULTS (collected) =====` | 进入结果段；同一文件多次出现则 `session + 1`，不复位块序号 | `CheckBlock.session` |
| `===== 2. IDENTIFICATION =====` | 关闭当前块，更新分区；END 标记先于分区正则判断 | `CheckBlock.section` |
| `[01] Duplicate UID / UID=0 accounts` | 新建检查块；编号只用于同一会话内定位，不要求与 `checks_map.block_index` 一致 | `CheckBlock.block_index / title` |
| `  cmd: ...`、`  file: ...` | 必须恰好两个空格开头；分别追加到命令与文件引用列表，可写多行 | `commands / file_refs` |
| `  no duplicate uid` | 两个空格开头即视为输出；去掉前两个空格并 `rstrip` 行尾，记录物理行号 | `OutputLine.line / text` |
| `===== END OF REPORT =====` | 关闭当前块并离开结果段 | 解析结束 |

块在遇到下一个块/分区/END/文件末尾时落盘。输出状态按内容判定：没有任何输出 → `failed`；
所有行都以 `no ` 开头 → `empty`（确认不存在）；其余 → `collected`。分区或块标题之外、
不以两个空格开头的行一律忽略，因此脚本注释、空行不会污染证据。

### 12.3 与标题映射的关系

- 采集条目 `capture.yaml` 的 `title` 必须与 `checks_map.yaml` 的 `title` 逐字一致；同一标题在
  不同资产族/系统类型下的适用范围由 `checks_map.yaml` 的 `os_family` 决定。
- 解析后若块标题不在 `checks_map.yaml` 中，跑批诊断会写「未映射：…」并明确列出块与来源文件；
  该块不参与自动判定，不会静默丢弃。
- `capture.yaml` 的 `expect` 只用于生成脚本里的「期望输出」注释，解析器不读取该字段。
- `family=database` 使用同一骨架与同一套标记，仅命令与标题不同；其块同样按标题进入映射。

### 12.4 手工补录要求

必须保留三个标记（结果段、分区、END）和两个空格缩进；可以改命令输出内容，但不要给输出加
制表符或对齐空格（第三个空格起会进入证据文本）。标题、分区不得改写，否则会触发「未映射」。
单文件只在 `raw/` 下扫描 `*.log`（不递归）；结构化 `checks/*.json` 优先于 `raw`。

## 13. 公司记录表版式

公司格式记录表是当前主产物：一个资产一张 sheet，文件名为 `<项目编号>_结果记录表.xlsx`。
写出口径集中在 `core/records/model.py`、`core/records/writer.py`，符合情况文案来自
`packs/<pack>/record.yaml` 的 `rules` 列表（每条规则的 `match` → `text`）。

### 13.1 表头区与固定行

```
第 1 行   A1:I1 合并，标题「网络安全等级保护现场核查结果记录表」
第 2 行   B2 项目编号：  C2:D2 值      E2 系统名称：  F2:G2 值
第 3 行   B3 核查对象：  C3:D3 值      E3 安全层面/安全类：  F3:G3 值
第 4 行   B4 IP地址：    C4:D4 值      E4 资产类别：  F4:G4 值
第 5 行   B5 核查时间：  C5:D5 值      E5 测评作业指导书：  F5:G5 值
第 7 行   A7:I7 列头
第 8 行   A8:I8 合并，文本「安全通用要求」
第 9 行起 每个测评项一行
```

列头固定 9 列，顺序不可变：

| A | B | C | D | E | F | G | H | I |
|---|---|---|---|---|---|---|---|---|
| 序号 | 控制点 | 控制项 | 结果记录 | 符合情况 | 备注 | 重要程度 | 检查内容 | 判断标准 |

列宽：A 9.5、B 28.5、C 38、D 33.1640625、E 28.5、F 33.1640625、G 14.1640625、
H 14.234375、I 14.234375。表头行高 16，数据行按列宽估算换行后自适应（24—409）。

### 13.2 三值口径

内部判定保留五种状态，写入公司记录表时只收敛为四种字面值（含空）：

| 内部判定 | `record.yaml` 取值 | 单元格 |
|---|---|---|
| 符合 | 符合 | `符合(1分)` |
| 部分符合 | 不符合 | `不符合(0分)` |
| 不符合 | 不符合 | `不符合(0分)` |
| 不适用 | 不适用 | `不适用` |
| 未采集 | 空 | 空字符串，备注写 `未采集：<原因>` |

因此公司记录表不出现「部分符合(0.5分)」；部分符合的事实与未通过原因仍保留在「结果记录」列，
不会丢证据。结果记录统一以「经核查：」起句，并逐条列出未通过的实施点编号与原因。
备注列只承载不适用理由与未采集诊断，判定说明留在结果记录列。

`rules` 的 `match` 必须完整覆盖五种状态（各出现一次），`text` 只能是上表四种字面值；
缺值、重复、未知 `match` 或写出非法文案时 `RecordError` 直接失败，不会带病导出。读取 xlsx 时
第 7 行必须是上述 9 列原样顺序。

