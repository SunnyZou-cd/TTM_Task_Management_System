# 课程版重构验收 · 2026-11-16

## 结构变化

根目录demo1.py已从约2500行的生成文件变成简短启动入口，保留用户原文件头。实际程序是course_demo/ui.py、scheduler.py、storage.py三个普通模块；__init__.py为空包标记。没有dataclasses、协议、自定义时区、Fraction、AST生成或旧Workspace/Store运行依赖。

界面一个主要类，调度和存储为普通函数；状态只有一个字典，任务和区间是列表/字典，时间为整数分钟。本轮没有以密集单行或编码载荷隐藏复杂度，也没有声称复杂度减少就自动证明用户掌握代码。

原python_scheduler实现保留供历史参考；其生成脚本默认只写work/advanced-demo/demo1.py，不再覆盖根入口。用户开始前对旧根文件的本地修改完整备份在work/course-refactor/original_demo1.py。

## 实测

Windows / Python 3.14.3 / Tk 8.6。

- 课程测试29项通过：手算EDF/importance/risk、动态risk重新排序、区间busy合并扣除、拆分尾段/连续任务、锁定和当前时间、指标、损坏JSON/备份/磁盘修改保护/旧数据只读导入。
- 11项真实Tk操作涵盖任务CRUD/进度/完成、任务编辑保留锁、忙碌增改删、三策略比较、生成和定位、过去块拒锁、未排详情、中英、保存重载/取消关闭/旧导入另存保护。
- 新入口隔离进程只复制demo1.py和course_demo/，禁用site-packages后真实Tk启动成功，未导入academic_scheduler；--help可用，默认不写入工作区。
- 历史高级版104项回归通过；这些数量与课程版测试分开，不冒充新版本覆盖了全部历史边界。
- 中英与小窗口真实可见截图检查完成，截图work/course-refactor/course-english.png、course-chinese.png、course-small.png，布局报告未发现控件越界；已检查英文截图并缩短分钟列标题。机械界面检测空发现。

日志work/course-refactor/course-test.log、advanced-test.log；临时产物和存档均不进Git。测试没有读取或修改真实用户工作区。

## 有意收敛的边界

课程版不使用旧存档作为默认主库；显式导入会清空旧自动计划，保留显式锁。只支持文档中的任务字段和课程格式，遇到不支持的旧记录报错。没有后台同步、自动恢复残留锁文件或高级并发事务协议；仅保存前检查原始字节、备份和临时替换，不能声称对所有同时写入场景提供完整事务保证。

本机不存在或重复的钟面时间拒绝输入；不再自建时区类型。旧偏移时间导入保持绝对时刻。未实测其他Python版本/系统，也未进行真实课程现场验收。
