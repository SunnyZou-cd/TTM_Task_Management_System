# 项目接续入口

Python Demo 1 现在面向实际任务管理操作：默认进入本地空白工作区菜单，不自动运行内置案例。项目根目录的 `demo1.py` 支持录入任务和时间、生成与比较计划、锁定计划块、保存并重新打开存档。2026-11-15本轮81项测试和真实独立进程完整流程通过，证据见[软件验收](docs/scheduler/DEMO1_PRODUCT_VERIFICATION.md)。操作步骤见下文；预设案例演示需显式使用 `--demo`。

## Python Demo 1：交互式任务管理

在项目根目录 `C:\codex\TTM_Task_Management_System` 使用 Python 3.11 或更新版本。无需编辑 JSON 或安装项目包。

1. **检查版本并启动。**

   ```powershell
   python --version
   python .\demo1.py
   ```

   **成功标志：** 版本为 Python 3.11+；终端进入主菜单并显示当前存档路径、时区、规划窗口和未保存状态。首次运行默认空白，不会把演示案例加入任务。

2. **按菜单录入任务。** 主菜单选择 `1`（任务管理），再选择新增，按提示输入标题、总/剩余分钟、重要性、截止、最早开始及是否可拆分。时间支持 `YYYY-MM-DD HH:MM`，以工作区时区解释。

   **成功标志：** 任务列表出现新任务，字段与录入一致。菜单也支持编辑、删除、记录剩余分钟和明确标记完成。

3. **设置窗口和日程。** 选择 `2`（时间设置），设置规划起止和时区，添加可用及忙碌时段。默认 UTC；夏令时重复时刻须带明确偏移，不存在的本地时间会被拒绝。

   **成功标志：** 时间设置页显示所选时区、规划窗口和录入区间。改用其他 IANA 时区时，Windows需要时区数据；`python -m pip install tzdata`会联网并给当前Python环境安装数据包。

4. **生成、查看或比较计划。** 选择 `3` 设置 EDF / Importance First / Risk-Aware 和块长；选择 `4` 生成或重排，再选择 `5` 查看。选择 `7` 可比较三种策略。

   **成功标志：** 计划显示任务标题、时间块、未排分钟及原因；策略比较显示三份结果。计划只是安排建议，不代表完成。

5. **管理锁定并保存。** 选择 `6` 查看、锁定或解锁计划块；只锁当前有效计划中尚未开始的块。已开始的锁定块要先解锁，再核对进度并更新剩余分钟。选择 `8` 保存；默认位置是 `work\demo1-data\workspace.json`。

   **成功标志：** 锁定块在后续重排中保留；保存后未保存状态清除。已有存档会创建 `.bak` 备份；冲突或损坏存档不会被静默覆盖。保存失败可用`10`另存到新文件，保留当前修改。

6. **重启恢复。** 选择 `0` 退出，再运行 `python .\demo1.py`。也可用 `--data PATH` 指定其他存档，例如 `python .\demo1.py --data .\work\my-demo\workspace.json`。退出或重新加载时，若存在未保存更改，会提示保存、放弃或取消。

   **成功标志：** 重新打开同一路径后，保存的任务、日程和计划恢复。默认 UTC 不需要时区依赖；只读写本机存档，不连接真实数据库或外部账号。退出未保存时输入`s`保存、`d`放弃、`c`取消；重新加载前确认是否放弃当前修改。

要查看可行、超载和锁定重排的预设案例，请显式运行 `python .\demo1.py --demo`。这些演示数据不代表实际完成。完整步骤及包版 JSON CLI 说明见 [python_scheduler/README.md](python_scheduler/README.md)。三策略正式实验及 Pinboard 集成按 [PROJECT_PLAN.md](PROJECT_PLAN.md) 后续推进。

本项目作为中期项目继续开发。应用名 Pinboard，仓库名 TTM_Task_Management_System。

## 工作目录

- 后续开发目录：`C:\codex\TTM_Task_Management_System`。
- 原目录 `C:\codex\Pinboard` 保留作历史工作副本；后续修改集中在新目录。
- Git 历史已完整复制，origin 指向既有 GitHub 仓库。
- 新目录未复制 node_modules、安装包、临时测试数据或用户应用数据。

## 导入 Codex Desktop

1. 在 Codex Desktop 添加项目并选择本文件所在目录。成功标志：项目工作目录为 `C:\codex\TTM_Task_Management_System`。
2. 新建项目内聊天，让 Codex 先阅读 `AGENTS.md`、本文件、`PROJECT_STATE.md` 和 `docs/MODULARITY.md`。成功标志：后续操作使用新目录，并区分历史测试结果和本次验证。

## 开发基线

复制时本地提交为 `6d9a7fa`，版本为 0.3.0 预览版。历史实现和验证见 `PROJECT_STATE.md`；本次目录整理没有重新执行应用功能测试。

当前使用 Electron + React + TypeScript + Vite，可选 Supabase 云同步。正式发布前待确认技术方向，桌面模式 Win+D 与真实云端登录、跨设备同步仍需验收。

## 包版 JSON CLI（可选）

以下命令用于包版 JSON CLI 自定义输入；交互式个人任务管理请使用上面的单文件菜单。命令在本目录执行：建立虚拟环境并安装本地 Python 模块，随后比较相同输入的三种策略。安装会联网下载构建依赖和 Windows 时区数据；环境只写入项目 `work/`，调度不访问真实任务数据库。

```powershell
python -m venv work\python-scheduler-venv
.\work\python-scheduler-venv\Scripts\python.exe -m pip install .\python_scheduler
.\work\python-scheduler-venv\Scripts\python.exe -m academic_scheduler compare .\python_scheduler\examples\feasible.json
```

成功标志：退出码为 `0`，JSON 的 `results` 有三个策略结果。Python 需 3.11+；逐步操作和各步成功标志见模块 README。

## Electron 开发启动

在本目录执行 `npm ci` 安装依赖，再执行 `npm run dev`。安装会联网下载依赖并写入本目录的 node_modules。成功标志：Pinboard 开发窗口打开。

功能调整前先确定具体目标；测试使用项目内独立数据目录。已授权在完成工作并验证后自动提交和推送 GitHub，推送前排除凭据、个人数据和构建临时文件。
