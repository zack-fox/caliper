# RULES · 规则库编写指南

> 规则库是 Caliper 的唯一判定依据：采集什么、如何判定、如何整改、何时候选重大隐患，
> 都由 `packs/<pack>/` 下的 YAML 决定。本文说明六个库的位置与状态、字段约定、条件 DSL、
> 评分口径、版本失效机制，以及新增规则必须补齐的回归。
> 证据格式见 [FORMAT.md](FORMAT.md)，验收命令见 [ACCEPTANCE.md](ACCEPTANCE.md)。

## 1. 六个库的位置与状态

以 `packs/linux_os/` 为例，六库清单固定为 `library.yaml`，缺库或多登记都会让
`make library-lint` 失败：

| key | 文件 | 当前 status | 规则数 | 作用 |
|---|---|---|---|---|
| capture | `capture.yaml` | active | 54 | 生成 server / database 两族采集脚本 |
| record | `record.yaml` | active | 5 | 公司记录表的符合情况文案与 9 列口径 |
| judge | `rules/level2.yaml`、`rules/level3.yaml` | active | 78 | 把证据块判定到测评项实施点 |
| remediation | `remediation.yaml` | active | 18 | 不符合 / 部分符合项的整改建议 |
| high_risk | `high_risk.yaml` | active | 16 | 高风险判例与降风险前提 |
| major | `major.yaml` | active | 16 | 高风险命中后的三维评分与候选阈值 |

`status` 只有两种：

- `active`：必须有规则，且能被对应装载器解析；`library-lint` 会统计条数并拒绝空库。
- `scaffold`：框架已就位，允许 `rules: []`；但口径字段仍要能通过严格校验。
  `record` 已为 active：`rules` 共 5 条，五值判定各一条（`match` → `text`），
  `text` 只能是四种字面值；缺值、重复、未知 `match` 或非法文案都会被 `RecordError` 拒绝。

新增一个库不在本文范围内；替换或下线库只改 `library.yaml` 的 `status` 与 `paths`，
装载器会拒绝未登记的文件。

## 2. 统一字段约定

六个库的结构不同，但以下约定一致；新增规则时先按库查表，再遵守通用约束。

| 语义 | capture | judge | remediation | high_risk | major | record |
|---|---|---|---|---|---|---|
| 标识 | `title` | `rule_id`（可省略，自动生成） | `id` | `hr_id` | `id` | `id` |
| 版本 | `version` | 由 `library.yaml` 汇总 | `version` | 由 `library.yaml` 汇总 | `version` | `version` |
| 状态 | `status` | 由 `library.yaml` 汇总 | `status` | 由 `library.yaml` 汇总 | `status` | `status` |
| 适用等级 | `levels` | 文件名 `level2/level3.yaml` | `applies_to.level` | `level_min` | 通过 `hr_ids` 继承 | 全等级 |
| 适用资产族 | `families` | 由映射块 `os_family` 决定 | `applies_to.family` | `binds_items` 所属资产 | 通过 `hr_ids` 继承 | 全资产 |
| 关联测评项 | 标题映射 | `item` / `point` | `applies_to.item_seqs` | `binds_items` | `hr_ids` | 全部 |
| 输入块 | `section` / `title` | `block` | 按测评项命中 | 无 | 无 | 无 |
| 条件 | `expect`（仅注释） | `expect`（DSL） | `item_seqs` + 控制点兜底 | `binds_items` | `hr_ids` | `rules.match` |
| 输出文案 | 脚本注释 | `pass_reason` / `fail_reason` | `problem/cause/action/clause` | `问题描述/整改建议/…` | `scores.*.reason` | `rules.text`（四种字面值） |

通用约束：

- **不得写入真实数据**：IP、主机名、账号、口令、项目编号、客户名称一律使用文档保留地址
  （如 `192.0.2.10`）与示例占位。
- **active 库不得为空**；`library-lint` 先看 `status` 再看条数。
- **引用必须存在**：judge 的 `item/point` 必须落在 items 表中；remediation 的 `item_seqs`、
  high_risk 的 `binds_items` 必须指向真实测评项；major 的 `hr_ids` 必须覆盖全部高风险判例。
- **标题逐字一致**：capture 的 `title`、judge 的 `block` 与 `checks_map.yaml` 的 `title`
  必须逐字相同，不允许缩写、改大小写或补空格。
- **文案字段必填**：`pass_reason/fail_reason`、`problem/cause/action/clause`、评分 `reason`
  不得为空；空文案会让规则检查或装载直接失败。

## 3. 判定规则 DSL

judge 的 `expect` 是一个**只含一个键**的对象。组合器只有 `all` / `any`，嵌套最多两层；
`and / or / not / all_of / any_of / expected` 等字段会被 `validate_expect` 直接拒绝，
不做容错兜底。

### 3.1 原子操作

以下语义以 `core/rules/dsl.py` 为准，行文本已去掉采集缩进与行尾空白：

| 写法 | 语义 |
|---|---|
| `{contains: "no duplicate uid"}` | 任一行包含该子串 |
| `{not_contains: "0002"}` | 所有行都不包含该子串 |
| `{eq: "UID=0: <账号占位>"}` | 存在某一行（去空白后）完全等于该串 |
| `{ne: "no"}` | 不存在完全等于该串的行 |
| `{in: ["ok", "pass"]}` | 存在某行完全等于列表中的一项 |
| `{not_in: ["fail"]}` | 不存在完全等于列表项的行 |
| `{exists: "AllowUsers"}` | 同 `contains`，强调「出现即通过」 |
| `{not_exists: "NOPASSWD:"}` | 同 `not_contains` |
| `{regex_empty: true}` | 块状态是否为 `empty`（输出全是 `no ...`）；`false` 表示必须非空 |
| `{gt: {prefix: "rotate", value: 26}}` | 任一行以 `rotate` 开头，且其后第一个数字 > 26 |
| `{lt: {prefix: "PASS_MAX_DAYS", value: 91}}` | 任一行以 `PASS_MAX_DAYS` 开头，且其后第一个数字 < 91 |

`gt/lt` 的 `prefix` 匹配发生在 `strip()` 之后，`value` 必须是数字；同一块内多个匹配行
取「任一满足」即可。`contains/exists` 区分大小写，规则里需要兼容不同写法时用 `any` 展开。

### 3.2 组合与真实例子

`all` 表示同一实施点的多个条件必须同时成立；`any` 表示满足其一即可。来自
`rules/level3.yaml` 的真实写法：

```yaml
# 1.4 口令有效期：login.defs 中 PASS_MAX_DAYS 必须小于 91 天
- item: 1
  point: 4
  block: Password policy (login.defs)
  expect: {lt: {prefix: "PASS_MAX_DAYS", value: 91}}
  pass_reason: 口令最长使用期限小于 90 天
  fail_reason: 口令最长使用期限未限制或超过 90 天

# 2.2 登录失败锁定：必须同时配置 deny 与 unlock_time
- item: 2
  point: 2
  block: Login failure lockout (faillock)
  expect:
    all:
      - {contains: "deny="}
      - {contains: "unlock_time="}
  pass_reason: 已配置登录失败处理与锁定时间
  fail_reason: 未同时配置登录失败次数与锁定时间

# 18.1 远程登录源限制：AllowUsers / AllowGroups / hosts.deny 任一即可
- item: 18
  point: 1
  block: Remote login source restriction
  expect:
    any:
      - {contains: "AllowUsers"}
      - {contains: "AllowGroups"}
      - {contains: "hosts.deny"}
  pass_reason: 已限制远程登录来源
  fail_reason: 未限制远程登录来源

# 中间件/数据库按部署情况出现的块，缺失时跳过该实施点，不判未采集
- item: 1
  point: 4
  block: MySQL 口令复杂度策略
  optional_block: true
  expect:
    any:
      - {all: [{contains: "validate_password"}, {contains: "ACTIVE"}]}
      - {contains: "not detected"}
      - {contains: "skipped"}
  pass_reason: 数据库口令复杂度策略已启用或不适用
  fail_reason: 数据库口令复杂度策略未启用
```

### 3.3 求值前置条件

证据块状态为 `failed` / `skipped`，或没有任何输出时，任何原子条件都返回 false
（包括 `not_contains`、`not_in`、`regex_empty`），不会因为「没扫到坏东西」而误判通过。
因此采集失败必须表现为「未采集」，不能靠否定条件洗成「符合」。

`optional_block: true` 只用于中间件/数据库这类「部署了才有块」的证据。服务器核心检查块
不得标 optional，否则漏采会被静默跳过。

## 4. 评分口径

`major.yaml` 只对高风险命中做二次评分，命中本身不直接等于重大隐患：

- 维度与权重：相关性 0.4、严重性 0.4、高发性 0.2，权重和必须为 1（容差 0.001）。
- 每个维度得分 0—3 的整数，必须写明 `reason`，理由要能落到问题描述或风险评价原文。
- 加权总分：`round(0.4×相关性 + 0.4×严重性 + 0.2×高发性, 2)`。
- 阈值：`threshold: 2.4`；`总分 >= 2.4` 才是候选，低于阈值仍可在人工确认后处理，
  但不得自动列入重大隐患。
- 每个高风险判例至少被一条 major 规则覆盖；`lint-rules` 会对漏覆盖的 `hr_id` 报错。
- 同一输入、同一规则文件必须得到完全相同的候选列表与顺序；评分逻辑不得依赖时间、
  随机数、字典遍历顺序或外部环境。

当前 16 条规则的分数与理由见 `packs/linux_os/major.yaml`；修改权重或阈值必须同步更新
`docs/FORMAT.md`、本文件与 `tests/test_major_scoring.py`。

## 5. 版本与失效机制

- `library.yaml` 的 `version` 是六库清单版本；各文件另有自己的 `version`。
  内容变化应同时提升对应版本，便于人工追溯。
- 导出重大隐患 / 问题汇总前，`compute_rule_version()` 对 `high_risk.yaml` 与
  `major.yaml` 的**字节内容**按固定顺序做 sha256，取前 12 位作为规则版本。
- 人工确认写入 `corrections.db` 时同时保存 `rule_version` 与 `basis_fingerprint`。
- `basis_fingerprint` 由判定依据计算：测评项与映射、当前等级规则、资产信息（不含证据目录名）、
  证据包系统类型/等级/主机、每个证据文件的路径与 sha256。任一项变化都会失效。
- 导出校验顺序：先比规则版本（“规则版本已变更，需重新确认”），再比判定依据
  （“判定依据已变化，需重新确认”）；任一不一致即阻止导出，不会带旧确认放行。
- 记录表人工修改（带资产类型保存）会删除对应 `field=major` 的确认，迫使重新判定与确认。
- 因此：改规则、改证据、改资产信息、重跑判定后，都必须重新人工确认；不要手工改
  `corrections.db` 绕过。

## 6. 新增或修改规则的回归要求

每次改动规则库，至少完成以下检查：

1. `make lint-rules`：检查块引用、实施点与 checks_map 完全一致、二值口径、高风险引用。
2. `make library-lint`：六库齐全、active 非空、条数可统计。
3. `make check`：语法、规则、契约与全量测试；不允许用跳过用例换绿。
4. **judge 新规则**：同时准备通过与不通过两份合成证据，断言实施点结论与理由；
   若新增检查块，`capture.yaml` 的服务器标题必须与 `checks_map.yaml` 逐字一致。
5. **remediation 新规则**：`item_seqs` 必须引用真实测评项；用不符合项断言建议非空，
   优先级只取高/中/低。
6. **high_risk / major 新规则**：保持 1:1 覆盖；同步更新评分测试，确认候选与非候选
   都能出现且重复评估结果一致。
7. **record 文案**：四种字面值不得新增；部分符合仍收敛为 `不符合(0分)`。
8. 全链路回归：`pytest tests/test_pipeline.py -q` 必须通过，且诊断中不得出现「未映射」。
9. 输出文案变化会影响金标准：先人工复核差异，再决定是否 `caliper golden --update`，
   不得为了让用例通过而反向改规则。

### 6.1 脱敏案例回归库

`tests/cases/` 是入库的静态回归库，用完整案例覆盖「通过 / 不通过 / 数据库 / 多脚本」四类场景。
每个用例一个目录，结构固定：

```text
tests/cases/<case_id>/
  case.yaml
  evidence/<包名>/raw/*.log
```

`case.yaml` 字段：

| 字段 | 说明 |
|---|---|
| `id` | 用例标识，必须与目录名一致 |
| `title` | 用例说明 |
| `level` | 项目等级，2 或 3 |
| `project_code` | 可选，项目编号，默认 `示例-回归-001` |
| `system_name` | 可选，系统名称，默认 `示例系统A` |
| `assets` | 资产列表；字段与 `project.yaml` 的 `assets` 相同，`evidence_package` 由测试注入 |
| `evidence` | `evidence/` 下的证据包目录名 |
| `expect.sessions` | 期望解析出的采集会话数 |
| `expect.blocks` | 期望检查块总数 |
| `expect.block_titles` | 每个会话内的块标题顺序；跨会话重复时按 `sessions` 展开 |
| `expect.os_family_by_session` | 各会话识别出的系统类型（`debian` / `rhel`） |
| `expect.unmapped` | 允许出现的「未映射」诊断条数，回归用例固定为 0 |
| `expect.verdicts` | 指定测评项序号 → 判定结论（`符合/部分符合/不符合/不适用/未采集`） |
| `expect.compliance` | 指定测评项序号 → 记录表「符合情况」字面值；空串表示空单元格 |
| `expect.remediation` | 期望整改建议规则编号列表，按测评项序号排序 |
| `expect.major_candidates` | 由实际不符合项触发并达到阈值的重大隐患候选 `HR-*` 集合 |

新增用例：

1. 新建 `tests/cases/<case_id>/`，复制一个现有用例的目录结构与命令输出格式；
2. 日志必须是脱敏后的 uniTerm 原始日志（`===== RESULTS (collected) =====`、
   `===== n. SECTION =====`、`[NN] 标题`、两空格缩进输出、`===== END OF REPORT =====`），
   不放 `manifest.json`，走原始日志解析；
3. 按实际运行结果填写 `expect`，不要为让用例通过而改规则或改日志；
4. 运行 `pytest tests/test_regression_cases.py -q`，四个及以上用例必须全部通过。

红线：案例内不得写入真实 IP、主机名、账号、口令、项目编号或客户名称，IP 只允许
`192.0.2.10` / `192.0.2.11` 等文档保留地址；测试只依赖 `tests/cases/` 与仓库
`packs/linux_os`，不得依赖被 `.gitignore` 排除的 `fixtures/`。
