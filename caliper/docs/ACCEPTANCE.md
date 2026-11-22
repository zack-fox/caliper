# ACCEPTANCE · 第一版验收标准

> 对应 `.trae/specs/build-evidence-pipeline/checklist.md` 的验收项。每条给出可执行命令
> 与可观察结果；命令默认在 `caliper/` 目录执行，使用仓库内虚拟环境。
> `fixtures/` 下是本地脱敏样例（不入库）；若样例缺失，用第 14 条的合成回归等价验证。
> 验收记录以命令输出为准，不以「应该可以」代替。

## 0. 准备

```bash
cd caliper
make setup          # 首次
make setup-gui      # 第 13 条需要
```

## 1. 六库清单与 active 规则

```bash
make library-lint
```

可观察结果：

- 输出 6 行，键为 `capture / record / judge / remediation / high_risk / major`，六个库均为 `active`；
- `active` 的库条数均大于 0（当前 capture 54、record 5、judge 78、remediation 18、high_risk 16、major 16）；
- 任一 `active` 库条数为 0 时，命令必须非零退出；
- 末行 `六库校验通过：6 个库，共 187 条规则`，退出码 0。

## 2. 两族采集脚本与无真实信息

```bash
make capture FAMILY=server LEVEL=3 > /tmp/caliper-server.sh
make capture FAMILY=database LEVEL=3 > /tmp/caliper-mysql.sh
grep -c '^\[[0-9][0-9]\] ' /tmp/caliper-server.sh
grep -c '^\[[0-9][0-9]\] ' /tmp/caliper-mysql.sh
grep -Ec '([0-9]{1,3}\.){3}[0-9]{1,3}' /tmp/caliper-server.sh /tmp/caliper-mysql.sh || true
```

可观察结果：

- server 脚本 46 个块，database 脚本 8 个块（与 `capture.yaml` 中对应族/等级的条目数一致）；
- IP 正则匹配数为 0；脚本中不出现真实主机名、账号或口令，连接凭据只提示从只读配置文件读取；
- 两个脚本均以 `===== RESULTS (collected) =====` 开头结果段，以 `===== END OF REPORT =====` 结束。

## 3. 脱敏环境执行与块数一致

> 仅在已授权的脱敏实验机执行；脚本只读，不修改目标系统。

```bash
sh /tmp/caliper-server.sh > /tmp/caliper-server.log
sh /tmp/caliper-mysql.sh  > /tmp/caliper-mysql.log
.venv/bin/python -m core.cli parse --pkg /tmp/caliper-server.log
.venv/bin/python -m core.cli parse --pkg /tmp/caliper-mysql.log
```

可观察结果：

- 服务器日志 `检查块总数：46`、`会话数：1`；MySQL 日志 `检查块总数：8`；
- 块数与脚本条目数完全一致（命令失败或输出为空仍保留块，状态为 `failed/empty`）；
- 无 `[提示]` 输出；若有提示，必须能解释为采集环境问题，而不是结构缺失。

## 4. 样例日志零「未映射」与显式结论

```bash
cd fixtures/samples
PYTHONPATH=../.. ../../.venv/bin/python -m core.cli run \
  --project project.yaml --out /tmp/caliper-accept-run | tee /tmp/caliper-run.log
cd ../..
grep -c '未映射' /tmp/caliper-run.log || true
```

可观察结果：

- `未映射` 计数为 0；
- 输出 34 行测评项，每行都有结论（符合/部分符合/不符合/不适用）或 `[提示]` 中的明确原因
  （未采集、规则库无对应条目等），不存在既无结论又无诊断的行；
- 结果记录表自检行 `字段自检：行数/序号/符合情况文本/列宽 全部通过`。

## 5. 公司记录表版式

```bash
cd fixtures/samples
PYTHONPATH=../.. ../../.venv/bin/python -m core.cli records \
  --project project.yaml --out /tmp/caliper-accept
cd ../..
.venv/bin/python - <<'PY'
import openpyxl
path = "/tmp/caliper-accept/示例-2026-001_结果记录表.xlsx"
wb = openpyxl.load_workbook(path)
for ws in wb:
    print(ws.title, ws.max_row, [cell.value for cell in ws[7]])
    print("表头", ws["C2"].value, ws["F2"].value, ws["C4"].value, ws["F4"].value, ws["C5"].value)
    print("合并", sorted(str(r) for r in ws.merged_cells.ranges))
    print("列宽", {k: ws.column_dimensions[k].width for k in "ABCDEFGHI"})
PY
```

可观察结果：

- 每个资产一张 sheet；
- 第 7 行恰好 9 列：`序号/控制点/控制项/结果记录/符合情况/备注/重要程度/检查内容/判断标准`；
- 表头 `C2/F2/C3/F3/C4/F4/C5/F5` 八个字段齐全，合并区为
  `A1:I1、A8:I8、C2:D2、F2:G2 … C5:D5、F5:G5`；
- 列宽 A 9.5、B 28.5、C 38、D 33.1640625、E 28.5、F 33.1640625、G 14.1640625、
  H 14.234375、I 14.234375；数据从第 9 行开始，三级共 34 行（`max_row=42`）。

## 6. 符合情况四种字面值

```bash
.venv/bin/python - <<'PY'
import openpyxl
ws = openpyxl.load_workbook("/tmp/caliper-accept/示例-2026-001_结果记录表.xlsx").worksheets[0]
values = {ws.cell(row, 5).value for row in range(9, ws.max_row + 1)}
print(values)
assert values <= {"符合(1分)", "不符合(0分)", "不适用", None}
print("OK")
PY
```

可观察结果：

- 输出集合只包含 `符合(1分)`、`不符合(0分)`、`不适用`、`None`（空）；
- 不出现 `部分符合(0.5分)`；部分符合已收敛为 `不符合(0分)`，原因仍保留在结果记录列。

## 7. 结果记录句式

```bash
.venv/bin/python - <<'PY'
import re
import openpyxl
ws = openpyxl.load_workbook("/tmp/caliper-accept/示例-2026-001_结果记录表.xlsx").worksheets[0]
texts = [ws.cell(row, 4).value or "" for row in range(9, ws.max_row + 1)]
assert all(text.startswith("经核查：") for text in texts)
failed = [text for text in texts if "未通过" in text]
assert failed
for text in failed:
    body = text[len("经核查："):]
    for line in body.splitlines():
        assert re.match(r"^\d+\) (通过|未通过)：", line), line
print(len(texts), "行均以经核查：起句；未通过行按实施点编号逐条陈述")
PY
```

可观察结果：

- 34 行全部以 `经核查：` 起句；
- 未通过项逐条形如 `N) 通过：…` / `N) 未通过：…`，实施点编号从 1 起连续，
  并带证据锚点（文件:行号 片段）；编号不因前面有通过项而重排。

## 8. 不符合项的整改建议

```bash
.venv/bin/python -m pytest \
  tests/test_pipeline.py::test_remediation_for_non_compliant_item \
  tests/test_remediation.py::test_suggest_for_non_compliant -q
```

可观察结果：

- 2 passed；
- 断言覆盖 `rule_id`、`problem`、`cause`、`action`、`priority`、`clause` 均非空，
  优先级只取高/中/低；无命中时返回空列表，不编造问题或条款。

## 9. 云端润色白名单与预览

```bash
.venv/bin/python -m pytest \
  tests/test_remediation.py::test_payload_whitelist_and_no_network -q
.venv/bin/python - <<'PY'
from adapters.llm.polish import PAYLOAD_FIELDS, build_payload, polish
from core.remediation import Advice

advice = Advice(
    rule_id="REM-示例", item_id="L3-CES1-01", seq=1, title="示例",
    problem="示例问题", cause="示例成因", action="示例动作",
    priority="高", clause="示例条款",
)
payload = build_payload(advice)
print(sorted(payload))
print(polish(advice) is advice)
assert set(payload) == set(PAYLOAD_FIELDS)
assert not any(key in payload for key in ("evidence", "note", "host", "ip", "log"))
PY
```

可观察结果：

- 请求体只有 6 个结构化字段：`action / cause / clause / priority / problem / title`；
- 不含证据原文、备注、日志、主机名、IP；`polish()` 在无客户端时原样返回，默认不发起网络调用；
- 预览值来自整改建议库，原始证据不出机。

## 10. 高风险条目的降风险字段

```bash
.venv/bin/python -m pytest \
  tests/test_major_scoring.py::test_high_risk_entries_have_reduction_fields -q
```

可观察结果：

- 1 passed；
- 16 条高风险判例均含布尔 `可降风险` 与字符串 `降风险前提`；
- `可降风险=true` 的条目前提非空；未人工确认前只作为候选，不直接入表。

## 11. 重大隐患三维评分

```bash
.venv/bin/python -m pytest \
  tests/test_major_scoring.py::test_assessment_is_deterministic_and_threshold_boundary \
  tests/test_major_scoring.py::test_major_rows_fill_three_dimension_scores -q
```

可观察结果：

- 2 passed；
- 每条候选含相关性、严重性、高发性三项得分与理由；
- 加权口径 0.4/0.4/0.2，阈值 2.4，达到即候选（MR-12 恰好 2.4 为候选，MR-06 低于 2.4 为非候选）；
- 同一输入重复评估结果完全一致。

## 12. 导出闸门与确认失效

```bash
.venv/bin/python -m pytest \
  tests/test_major_scoring.py::test_export_gate_blocks_unconfirmed_and_stale_entries \
  tests/test_major_scoring.py::test_confirmation_version_or_fingerprint_mismatch_is_invalid \
  tests/test_pipeline.py::test_major_scoring_is_deterministic_and_gates_export -q
```

可观察结果：

- 3 passed；
- 未确认导出报 `还有 N 条重大隐患候选未完成有效人工确认，暂不能导出`；
- 确认后放行；改规则版本报 `规则版本已变更，需重新确认`，改判定依据指纹报
  `判定依据已变化，需重新确认`，均阻止导出；
- 记录表人工修改会删除对应重大确认，必须重新判定/确认。

## 13. 桌面端预览与生成

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_gui_records.py -q
QT_QPA_PLATFORM=offscreen .venv/bin/python -m app.main --smoke
```

可观察结果：

- GUI 测试全部通过：结果页有「记录表预览」「生成记录表」按钮；预览 9 列、行序与
  `build_sheet` 完全一致；生成的文件落在输出目录；
- smoke 输出 `[smoke] pages=7 keys=overview evidence results issues risk export rules`、
  `templates=4`，退出码 0；
- 侧栏为「项目」（项目概述 / 材料与资产 / 现场核查 / 问题与整改 / 风险与结论 / 导出交付）
  与「工具」（规则库）两组；窗口最小 1280×800，宽度小于 1360px 时侧栏自动折叠且内容不横向溢出。

## 14. 全链路回归与全量检查

```bash
.venv/bin/python -m pytest tests/test_pipeline.py -q
make check
```

可观察结果：

- `tests/test_pipeline.py` 6 passed：合成日志解析无「未映射」、判定有结论、
  记录表 9 列可回读、整改建议非空、重大评分确定、确认门禁有效；
- `make check` 的 syntax / lint / library-lint / contracts / test 全部通过，退出码 0；
- 不依赖案例模版、不联网、不读取真实项目数据。

## 15. 三份文档与 README 引用

```bash
ls -l docs/FORMAT.md docs/RULES.md docs/ACCEPTANCE.md
grep -n "FORMAT.md\|RULES.md\|ACCEPTANCE.md" README.md
```

可观察结果：

- 三个文件均存在且非空；
- README 至少各有一处链接：证据格式 `FORMAT.md`、规则编写 `RULES.md`、验收标准 `ACCEPTANCE.md`；
- 文档中的命令与本文一致，未引用真实项目编号、IP、主机名或账号。

## 16. 脱敏案例回归库

```bash
.venv/bin/python -m pytest tests/test_regression_cases.py -q
```

可观察结果：

- 4 个参数化用例（`server_l3_compliant`、`server_l3_noncompliant`、`database_l3`、
  `multi_script`）全部通过；
- 每个用例的会话数、块数、「未映射」条数、指定测评项结论、记录表符合情况、
  整改建议规则编号与重大隐患候选 `HR-*` 均与 `tests/cases/<case>/case.yaml` 的
  `expect` 一致；
- 每例都能 `write_record_book` 写出 xlsx，回读第 7 行 9 列，符合情况只出现
  `符合(1分) / 不符合(0分) / 不适用 / 空`；
- 用例只依赖 `tests/cases/` 与仓库 `packs/linux_os`，不依赖 `fixtures/`；
- 案例内 IP 仅使用 `192.0.2.x` 文档保留地址，资产名、项目编号与账号均为示例占位。
