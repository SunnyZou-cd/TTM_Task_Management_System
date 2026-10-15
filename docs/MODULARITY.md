# 技术栈与后续模块化

结论：继续使用 Electron + React + TypeScript + Vite。它们能承载主题、自定义视图、Markdown 编辑和 Windows 原生扩展，本轮无需更换框架。

| 能力 | 当前边界 | 后续扩展入口 |
| --- | --- | --- |
| 主题 | CSS 语义变量；系统/浅色/深色 | 在变量上增加经过校验的主题配置、字号和密度，不允许主题执行脚本 |
| 任务规则 | AppService + shared task-rules | 单独测试规则，UI 只提交结构化输入 |
| 内容编辑 | Markdown 渲染和源位置编辑模块 | 新编辑器替换 renderer 组件，数据仍为 Markdown |
| 管理视图 | MainView、Management、ItemEditor 分离 | 通过类型化 props 加入视图，避免跨模块修改数据库 |
| Windows 集成 | WindowManager + 桌面宿主适配器 | 与 React 隔离，只通过有限的 preload/IPC API 调用 |
| 文件与同步 | 本地持久化、ObsidianBridge、CloudAdapter | 新同步源实现独立适配器，保留工作区隔离 |

## 正式版前的决策

当前适合继续增加内置主题和第一方模块。若要让第三方插件运行代码，需另建插件清单、权限声明、沙箱和 API 版本管理；现有 preload 不应直接开放给插件。用户主题和第三方插件平台是两种独立能力。

Electron 适合现有 React 和 Markdown 功能复用，代价是随包携带 Chromium。Windows 桌面层由原生宿主接口实现，和网页主题独立。桌面模式只在显式选择后启用，失败时返回普通窗口。

代码与预览版本可持续同步 GitHub；正式版发布前由用户确认这一技术方向及验收结果。
