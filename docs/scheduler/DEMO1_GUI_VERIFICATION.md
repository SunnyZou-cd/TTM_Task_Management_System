# Demo 1 GUI 验收 · 2026-11-16

实测 Windows / Python 3.14.3 / Tk 8.6。默认 `python demo1.py` 打开英文 Tkinter 窗口；顶部 Language / 语言可切换 English / 简体中文。语言仅在当前会话生效，用户任务名称和表单内容保持原样。终端模式仍为中文，通过 --terminal 启动。

## 自动测试证据

在项目根目录设置 PYTHONDONTWRITEBYTECODE=1、PYTHONPATH=python_scheduler/src，执行 work/demo1-acceptance/venv/Scripts/python.exe -m unittest discover -s python_scheduler/tests -v。

最终结果：88项通过，日志 work/gui-review/final-test.log。其中5项真实Tk控件测试使用隐藏根窗口，覆盖录入任务、时间/可用时段、生成、锁定、保存恢复、中英文切换保持草稿、保存冲突和取消关闭、未应用表单禁止静默保存/关闭、刷新后重选任务保留草稿、双列表最后选择决定解锁目标。既有工作区/存档测试继续覆盖备份、并发冲突、损坏文件与事务回滚。

单文件测试创建真实Tk根窗口并通过after关闭，验证默认GUI/显式GUI入口；隔离第三方包和项目路径后可运行。屏蔽tkinter时，JSON子命令和--terminal仍可用。生成文件同步检查通过。

## 可见窗口与截图

创建并前置显示真实Windows窗口，截图在work/gui-review/：tasks-english.png、time-english.png、plan-english.png、tasks-chinese.png、tasks-minimum.png、plan-minimum.png。检查1100×700及820×600逻辑尺寸，布局报告layout-report.json未发现越界控件；主agent查看英文任务页和修正后最小计划页，底部锁定列表可见，指标以一位百分比显示。

这是合成工作区的自动控件操作与可见截图检查，并非用户真实学业数据或全部对话框的人工验收。系统文件选择/确认按钮语言可能跟随Windows。

## 已修复问题

- 未点击Add/Apply/Update的表单草稿在关闭、加载、保存及重选任务时得到保护。
- 计划和锁定两个列表选择互斥，避免解锁错误对象。
- 损坏存档启动错误与常见工作区错误在英文界面显示英文。
- 小窗口缩短摘要区并保留锁定列表空间，比例显示为百分比。

## 范围

实现Tasks/Time/Plan及任务管理、时间配置、三策略生成比较、锁定重排、保存/另存/打开/重载，沿用本地备份和冲突保护。默认存档work/demo1-data/workspace.json，测试仅使用work/合成数据。

未实测其他Python版本/系统；没有用户真实数据验收。语言偏好不跨会话保存。没有发布安装包或稳定版。
