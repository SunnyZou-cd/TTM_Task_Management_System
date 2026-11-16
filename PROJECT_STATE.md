# 项目状态 · 2026-11-16

## Tkinter GUI 更新 · 2026-11-16

- Demo 1 已切换为Tkinter图形界面默认入口：`python demo1.py` 打开窗口，`--terminal` 保留终端菜单，`--demo` 显式运行合成案例。
- 窗口默认英文，并提供 English / 简体中文切换。任务、时间和计划分成三个主要页面，继续使用本地 Workspace / Store；默认个人存档仍为 `work/demo1-data/workspace.json`。
- 本轮88项测试通过，含5项真实Tk控件测试、单文件窗口启动检查和两种尺寸可见截图。测试只使用合成数据；语言切换仅当前会话生效。
- GUI 操作计划：[DEMO1_GUI_PLAN.md](docs/scheduler/DEMO1_GUI_PLAN.md)；验收记录：[DEMO1_GUI_VERIFICATION.md](docs/scheduler/DEMO1_GUI_VERIFICATION.md)。

## Demo 1 Workspace 与终端界面（GUI 前验收记录）

- Workspace API 和终端菜单可管理任务、记录进度/完成、设置窗口/时区/可用和忙碌时段、选择策略/块长、生成查看和比较计划、锁定解锁重排、保存加载和另存。GUI版本的默认入口另见上节。
- 个人存档默认work/demo1-data/workspace.json；备份.bak、原子保存和并发冲突保护，保存失败保留内存；10另存为可转存到新路径。原有预设案例改为显式`--demo`，不再是默认产品流程。
- 工作区编辑成功才更新版本并使旧计划失效；生成使用不早于实际当前分钟的起点，过期锁定需人工解锁和核对进度；计划不改变完成状态。
- Windows / Python 3.14.3全套81项终端/Workspace测试通过；真实独立单文件进程完成录入→生成→多块锁定→编辑→重排→保存→重启恢复及进度/完成/删除流程。新虚拟环境安装与命令入口通过，pip check通过；独立审查实际双进程确认冲突不会覆盖新数据。以上记录不涵盖 Tkinter GUI。
- 本轮目标和计划：[DEMO1_PRODUCT_PLAN.md](docs/scheduler/DEMO1_PRODUCT_PLAN.md)；实际证据：[DEMO1_PRODUCT_VERIFICATION.md](docs/scheduler/DEMO1_PRODUCT_VERIFICATION.md)。仅测试合成数据，未操作真实数据库。

以下2026-11-13/14记录是调度组件与预设案例基础的历史交付；本次软件使用流程以上述新验收为准。

## Demo 1 单文件版（GUI 前的案例模式证据）

- GUI 更新前，根目录 `demo1.py` 的默认模式是显示三个合成案例和九份策略结果；该行为现由显式 `--demo` 保留，不能视为个人工作区的默认启动方式。
- 内置演示使用UTC，复制单个文件后无需安装模块或读取外部示例。自定义IANA时区继续使用系统时区库或tzdata；JSON文件的schedule/compare/validate接口保留。
- 2026-11-14在Windows / Python 3.14.3通过51项测试：新增7项检查覆盖复制到临时目录、`-I -S -B`禁用项目路径和第三方包、九结果与模块版逐项一致、确定性、JSON子命令、错误码和生成同步。该历史测试不覆盖本次 Tkinter 窗口。
- 单文件由可读模块源码生成，无运行时exec、编码载荷或项目导入；`python_scheduler/scripts/build_single_file.py --check`检查同步。生成命令会覆盖demo1.py，个人试验应另存副本。
- 该阶段仅新增案例单文件交付和测试/文档，没有改动已有调度核心或真实用户数据。原有平台与课程验收限制继续适用。

## Python 学业调度 CLI Demo 1

- 已实现独立可安装 Python 包：严格 dataclasses 输入、UTC/IANA 时区、区间合并扣除、任务拆分与连续任务、now/截止约束、未排原因、锁定重排、独立输出校验和计划指标。
- EDF、Importance First 和动态 Risk-Aware 共用一个分配器；CLI 支持 `schedule`、同输入 `compare`、`validate`、文件和 stdin/stdout JSON、明确退出码与原子输出文件。
- 2026-11-13 Windows / Python 3.14.3 / tzdata 2026.6 的全新虚拟环境安装通过，命令行入口与 `python -m` 均通过。44 项 unittest 全通过，包含 160 份固定种子输入 × 3 策略的 480 组合法性和确定性检查；`pip check` 通过。
- 三份合成案例实测：可行 150/150 分钟；超载 120/180 分钟，缺口60；重排 150/150 分钟并原样保留两块锁定（其中空白预留30分钟）。非法输入退出2，篡改结果退出3，正常 stdout 为可解析 JSON。
- 运行指南：[python_scheduler/README.md](python_scheduler/README.md)；契约、计划和详细证据见 [docs/scheduler](docs/scheduler/DEMO1_VERIFICATION.md)。所有案例是合成数据，未连接真实应用数据库或云服务。
- CLI交付阶段没有实现 UI、Electron 联动或正式大规模实验；GUI 正在单独推进。没有发布稳定版。Python 3.11–3.13 和非 Windows 系统未实测，课程选题/AI使用/最终演示要求仍需课程方确认，不影响本次已授权 Demo 的实现。

以下 Electron 0.3 状态保留为 2026-10-15 历史记录；本轮未重跑其测试。

## 0.3 预览版

0.3 扩展任务管理、日程、Markdown 和桌面便笺工作流，当前作为预览版验证，尚未进入正式稳定发布。

- 默认显示待办任务，完成后自动归档；可切换到已归档并恢复，支持标签筛选、搜索、排序和每页 50 条分页。
- 侧栏与设置窗口提供固定入口。
- 每天、每周、每月固定日程按日程生成，不依赖前次完成状态；每 30 秒检查。下次启动最多补最近 30 次；停止循环后不再生成后续任务。
- Markdown 主界面提供源码和预览；固定便笺可直接修改渲染后的文字并保留结构，格式操作通过主界面完成。
- 日历支持选择日期放大和月视图缩略概览；Ctrl/Shift 多选日期，也可切换单日选择。
- 设置可选择主界面普通窗口或桌面模式。桌面模式使用真实 HWND attach/detach；辅助进程退出后的恢复已验证。Win+D 行为尚待实机验收。
- 首次写入数据库前备份为 `database.pre-0.3.json`。
- 安装包：`release/Pinboard-0.3.0-Setup.exe`。

## 验证状态

- 已通过 50 项单元测试、生产构建和运行时依赖审计（0 项报告）。
- 桌面两轮关闭/恢复、355 条任务工作流、日历多选、Markdown 编辑保留格式及打包程序启动与保存已通过。
- Win+D 尚未实测。
- 邮箱投递、SQL 执行、跨设备同步及线上账号隔离仍需使用真实 Supabase 项目验收。

## 0.2 历史记录

0.2 增加概览、截止日期月历、当前任务完成比例、主题适配及 Obsidian 导入和按需写回。该版本的详细记录见 [UPGRADE-0.2.md](docs/UPGRADE-0.2.md)。

## 项目基线

- 技术栈和模块边界见 [MODULARITY.md](docs/MODULARITY.md)：Electron、React、TypeScript、Vite；Supabase 作为可选云服务。
- 云端配置与未验收事项见 [CLOUD_SETUP.md](docs/CLOUD_SETUP.md)。
- 待验收：真实邮件投递、schema 执行、跨设备同步和线上账号隔离。
- Windows 安装包目标：`release/Pinboard-0.3.0-Setup.exe`；生成或安装验收以实际发行文件和状态记录为准。
