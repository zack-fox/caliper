# Caliper

把等保现场采集日志转换成公司格式记录表（主产物），并附带导出融合测评平台（测评能手 2.0）所需的四张 xlsx。纯规则、可解释，规则库可整体替换，全程离线，单机一次完成。

本工具不是该平台的替代品：只做「采集解析 → 规则判定 → 记录表生成 → 风险分析 → 附带导出」这一段，界面与文档只说「供其导入」。

## 当前阶段

V2.0.0 持续开发版：以「设备与证据包」为主入口——导入设备证据目录 → 核对识别结果 →
开始核查 → 结果记录 / 问题汇总 / 重大隐患 / 四表导出。证据支持结构化证据包
（manifest）与原始日志目录/单个日志文件两种方式，截图照片作为附件；
设备支持添加、编辑、删除，双击表格行即可修改；证据根目录、输出目录、规则包目录收进「设置…」。
macOS 开发工作区根目录的 `Caliper.app` 使用本机 `.venv` 启动；面向使用者的自包含安装包通过 `make package-macos` 构建。大模型、报告合成、验收材料只预留端口。
规则库是初版（三级 14 项、二级 14 项自动判定），按现场反馈继续迭代。

六库现状：`capture`、`record`、`judge`、`remediation`、`high_risk`、`major` 均为 active；
`record` 以 5 条规则给出符合情况文案。公司格式记录表是主产物，平台四表为附带导出。

## 目录

```
core/        contracts model evidence checks items records rules judge issues major render store ports cli
packs/       linux_os（library.yaml 六库清单 / items / rules / checks_map / high_risk / texts）
templates/   四张母版（只读，只填单元格，不改列与样式）
adapters/    noop（默认空实现）、llm（仅占位说明）
app/         桌面 UI：shell（顶栏/侧导航/状态栏）/ screens / widgets / theme；入口 caliper-gui
tests/       contracts / pipeline / gui / golden / negative
fixtures/    evidence / scripts / samples / golden（均不入库）
docs/        格式规范、规则库编写指南、验收标准与 PROJECT-PLAN.md（四步闭环与六库规划）
```

设计与开发路线以 `docs/PROJECT-PLAN.md` 为准：四步闭环（取证 → 记录表 → 判定 → 风险），
六套规则库统一由 `packs/linux_os/library.yaml` 登记，`make library-lint` 校验清单与装载。
证据格式（含采集脚本输出与公司记录表版式）见 `docs/FORMAT.md`，规则编写见 `docs/RULES.md`，
第一版验收命令与可观察结果见 `docs/ACCEPTANCE.md`。

## 快速开始

```bash
cd caliper
make setup       # 建 .venv 并安装运行时与测试依赖
make setup-gui   # 可选：安装 PySide6-Essentials
make check       # 语法 + 静态自检 + 六库清单 + 契约比对 + 测试

# 脱敏案例回归库（server 通过/不通过、database、多脚本）
.venv/bin/python -m pytest tests/test_regression_cases.py -q

# 生成采集脚本（server / database 两族；重定向为 .sh 后在授权环境执行）
make capture FAMILY=server LEVEL=3 > /tmp/caliper-server.sh
make capture FAMILY=database LEVEL=3 > /tmp/caliper-mysql.sh

# 生成公司格式记录表（主产物，每资产一张 sheet，9 列版式；pack_dir 建议绝对路径）
make records PROJECT=/path/to/project.yaml
# 样例项目的 pack_dir 是相对路径，需从项目文件所在目录运行：
(cd fixtures/samples && PYTHONPATH=../.. ../../.venv/bin/python -m core.cli records --project project.yaml)

# 解析证据（结构化证据包或原始日志目录/单个日志文件）
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

# 校验六库清单与装载（capture / record / judge / remediation / high_risk / major）
make library-lint

# 金标准逐格回归（期望表含项目/资产信息，不入库；首次先 --update 生成）
.venv/bin/python -m core.cli golden --dir fixtures/golden
.venv/bin/python -m core.cli golden --dir fixtures/golden --update

# 启动开发版桌面界面
.venv/bin/caliper-gui

# 构建无需接收方安装 Python 的 macOS 应用包（仅在 macOS 上执行，按当前机器架构构建）
make package-macos
# 输出：dist/Caliper.app 与 dist/Caliper-macos-<架构>.zip

# 构建 Windows 可执行文件（在 Windows 上执行）
.venv\Scripts\python -m PyInstaller --noconfirm --clean packaging\Caliper.spec
# 输出：dist\Caliper\Caliper.exe

# 离屏自检（校验页面装配、默认规则包和四张母版）
.venv/bin/python -m app.main --smoke

# 主题模板校验（QSS 颜色必须来自 design tokens）
make ui-lint
```

`make package-macos` 只能在 macOS 上执行（`make build` 等同 `make package-macos`），它会把桌面运行时、默认规则包和四张 Excel 母版一起装入 `dist/Caliper.app`，并生成 ZIP；接收方无需安装 Python、虚拟环境或开发依赖。默认无项目校正数据、证据目录和导出目录放在用户数据目录，项目打开后则继续把校正数据库保存在项目文件旁。构建产物按当前构建机器架构生成；工作区根目录原有的 `Caliper.app` 是开发启动器，不是交付安装包。

Windows 上执行上面的 PyInstaller 命令会跳过 `.app` 打包，直接产出 `dist\Caliper\Caliper.exe`（含同目录运行时与规则包、母版），无需接收方安装 Python。

当前打包流程未配置 Apple Developer ID 签名与公证。跨设备正式分发前仍需用组织的开发者证书完成签名和公证；否则 macOS 可能要求用户在首次打开时手动确认。Windows 可执行文件同样未签名，首次运行可能触发 SmartScreen 提示，需用户选择「更多信息 → 仍要运行」。

### 界面结构与主流程

左侧为工作流导航，顶栏固定项目上下文与主操作，右侧 AI 抽屉为规划中占位：

| 导航 | 页面 | 职责 |
| --- | --- | --- |
| 1 | 证据与资产 | 拖入采集日志/资产表即解析，自动回填资产字段，冲突项人工裁定 |
| 2 | 结果记录 | 逐项编辑结果记录 / 符合情况 / 备注，查看证据锚点并保存人工确认 |
| 3 | 问题与重大 | 不符合/部分符合汇总预览，勾选确认后进入重大安全隐患表 |
| 4 | 导出与设置 | 四张表独立导出、输出目录与规则包设置、导出日志 |
| 规则 | 规则库 | 只读浏览控制项、二值项、高风险判例与指导书 |

1. 「证据与资产」页可直接拖入采集目录或单个日志文件（`.log / .txt / .out / .cmd / .json / .xlsx`）。
   有 `manifest.json` 时走结构化校验，没有则按原始日志解析；截图、照片计入附件，不参与自动判定。
2. 表格「证据识别」列显示「可核查：N 块」「仅附件：N 张图片」或不可用原因；
   双击任意行可编辑设备与证据。
3. 顶栏「生成记录草稿」运行当前规则，随后在「结果记录」逐项编辑并确认；人工修改需要填写理由，修改历史保存在项目旁的 SQLite 数据库。
4. 「导出与设置」页仅允许在当前核查批次的记录全部人工确认后导出结果表、问题表和重大隐患表；修改记录会清除相关重大隐患确认，需重新判断。该页同时维护输出目录、证据根目录、规则包目录。
5. 顶栏「主题」切换浅色 / 深色，偏好写入系统设置，重启后保持。

样例项目在 `fixtures/samples/project.yaml`，样例证据包在 `fixtures/evidence/pkg-A01/`，
两者都被 `.gitignore` 忽略，需要时从内网开发包复制。结构化证据包带 `manifest.json`
（字段与校验规则见 `docs/FORMAT.md` 第 7 节）；现场直接采集的日志目录可以不生成
manifest，界面会自动按原始日志解析。

## 范围

- 等级：二级、三级；安全类：安全通用要求 → 安全计算环境。
- 资产：服务器 / 存储设备；系统：Ubuntu/Debian、CentOS/RHEL。
- 当前不实现：大模型、图片 OCR/内容识别（图片只作证据附件）、管理制度核查、资产拓扑、网络设备 pack；数据库与中间件只覆盖 MySQL 采集与初版规则。

## V1.0 边界

- 校正与备注保存在项目文件同目录的 `corrections.db`（sqlite），随项目迁移，不入库。
- 重大安全隐患只收人工勾选「符合重大判定原则」的问题；高风险命中仅作候选提示。
- 金标准期望表含项目与资产信息，按红线不入库；`fixtures/golden/` 无用例时 `make golden` 返回 2 并提示生成方式。
- macOS 双击入口为工作区根目录 `Caliper.app`；PyInstaller 打包（`make build`）保留为可选项，未纳入 V1.0 验收。

## 数据与提交约束

仓库里不出现敏感数据：系统名称、具体公网 IP、账户与个人信息、真实资产与项目编号一律用占位值（`192.0.2.0/24`、`203.0.113.0/24`、`example.com`、示例系统 A）。提交前逐项检查，命中即替换或剔除。
