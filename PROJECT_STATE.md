# 项目状态 · 2026-11-13

## Python 学业调度 CLI Demo 1

- 已实现独立可安装 Python 包：严格 dataclasses 输入、UTC/IANA 时区、区间合并扣除、任务拆分与连续任务、now/截止约束、未排原因、锁定重排、独立输出校验和计划指标。
- EDF、Importance First 和动态 Risk-Aware 共用一个分配器；CLI 支持 `schedule`、同输入 `compare`、`validate`、文件和 stdin/stdout JSON、明确退出码与原子输出文件。
- 2026-11-13 Windows / Python 3.14.3 / tzdata 2026.6 的全新虚拟环境安装通过，命令行入口与 `python -m` 均通过。44 项 unittest 全通过，包含 160 份固定种子输入 × 3 策略的 480 组合法性和确定性检查；`pip check` 通过。
- 三份合成案例实测：可行 150/150 分钟；超载 120/180 分钟，缺口60；重排 150/150 分钟并原样保留两块锁定（其中空白预留30分钟）。非法输入退出2，篡改结果退出3，正常 stdout 为可解析 JSON。
- 运行指南：[python_scheduler/README.md](python_scheduler/README.md)；契约、计划和详细证据见 [docs/scheduler](docs/scheduler/DEMO1_VERIFICATION.md)。所有案例是合成数据，未连接真实应用数据库或云服务。
- 本轮没有实现 UI、Electron 联动或正式大规模实验；没有发布稳定版。Python 3.11–3.13 和非 Windows 系统未实测，课程选题/AI使用/最终演示要求仍需课程方确认，不影响本次已授权 Demo 的实现。

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
