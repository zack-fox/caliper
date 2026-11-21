# Caliper

把等保现场采集日志转换成四张可直接导入融合测评平台（测评能手 2.0）的 xlsx。纯规则、可解释，规则库可整体替换，全程离线，单机一次完成。

本工具不是该平台的替代品：只做「采集解析 → 规则判定 → 四表生成 → 导出」这一段，界面与文档只说「供其导入」。

## 当前阶段

V1.0.1 测试运行版：以「设备与证据包」为主入口——导入设备证据目录 → 核对识别结果 →
开始核查 → 结果记录 / 问题汇总 / 重大隐患 / 四表导出。设备支持添加、编辑、删除，
双击表格行即可修改；证据根目录、输出目录、规则包目录收进「设置…」。
macOS 双击工作区根目录的 `Caliper.app` 即可打开。大模型、报告合成、验收材料只预留端口。
规则库是初版（三级 14 项、二级 14 项自动判定），按现场反馈继续迭代。

## 目录

```
core/        contracts model evidence checks items rules judge issues major render store ports cli
packs/       linux_os（items / rules / checks_map / high_risk / texts）
templates/   四张母版（只读，只填单元格，不改列与样式）
adapters/    noop（默认空实现）、llm（仅占位说明）
app/         桌面 UI：screens / theme / app.qss；入口 caliper-gui
tests/       contracts / golden / negative
fixtures/    evidence / scripts / samples / golden（均不入库）
```

## 快速开始

```bash
cd caliper
make setup       # 建 .venv 并安装运行时与测试依赖
make setup-gui   # 可选：安装 PySide6-Essentials
make check       # 语法 + 静态自检 + 契约比对 + 测试

# 解析证据包（89 块）
make parse

# 跑判定并导出结果记录表（三级样例）
make run

# 跑二级样例
make run PROJECT=fixtures/samples/project_L2.yaml

# 读入人工资产表并导出补全版（只补空白）
make assets ASSETS=fixtures/samples/asset_record.xlsx

# 导出安全问题汇总 / 重大安全隐患
# 重大隐患只收界面「问题与重大」页勾选确认的行，未确认时导出 0 行属正常
make export TABLE=issue
make export TABLE=major

# 解释单个测评项
make explain ITEM=1

# 校验规则库
make lint-rules

# 金标准逐格回归（期望表含项目/资产信息，不入库；首次先 --update 生成）
.venv/bin/python -m core.cli golden --dir fixtures/golden
.venv/bin/python -m core.cli golden --dir fixtures/golden --update

# 启动桌面界面
.venv/bin/caliper-gui
```

macOS 上也可直接双击工作区根目录的 `Caliper.app`（内部调用同一个 `.venv/bin/python -m app.main`）。

### 界面主流程

1. 「设备与证据」→「导入设备证据」：选择采集输出目录（含 `manifest.json`），
   弹窗会即时解析并显示检查块数量；设备名称可自动带出 manifest 的 host。
2. 表格「证据识别」列显示「可核查：N 块」或不可用原因；双击任意行可编辑设备与证据包。
3. 「开始核查」跑判定，随后在「结果记录」「问题与重大」查看并保存备注/重大确认。
4. 「导出与设置」导出四张表；「设置…」里可改证据根目录、输出目录、规则包目录。

样例项目在 `fixtures/samples/project.yaml`，样例证据包在 `fixtures/evidence/pkg-A01/`，
两者都被 `.gitignore` 忽略，需要时从内网开发包复制。证据包必须带 `manifest.json`
（字段与校验规则见 `docs/FORMAT.md` 第 7 节），从开发包拷贝时一并带上。

## 范围

- 等级：二级、三级；安全类：安全通用要求 → 安全计算环境。
- 资产：服务器 / 存储设备；系统：Ubuntu/Debian、CentOS/RHEL。
- 当前不实现：大模型、图片证据识别、管理制度核查、资产拓扑、数据库/中间件/网络设备 pack。

## V1.0 边界

- 校正与备注保存在项目文件同目录的 `corrections.db`（sqlite），随项目迁移，不入库。
- 重大安全隐患只收人工勾选「符合重大判定原则」的问题；高风险命中仅作候选提示。
- 金标准期望表含项目与资产信息，按红线不入库；`fixtures/golden/` 无用例时 `make golden` 返回 2 并提示生成方式。
- macOS 双击入口为工作区根目录 `Caliper.app`；PyInstaller 打包（`make build`）保留为可选项，未纳入 V1.0 验收。

## 数据与提交约束

仓库里不出现敏感数据：系统名称、具体公网 IP、账户与个人信息、真实资产与项目编号一律用占位值（`192.0.2.0/24`、`203.0.113.0/24`、`example.com`、示例系统 A）。提交前逐项检查，命中即替换或剔除。
