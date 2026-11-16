# 课程版 Academic Task Planner

阅读顺序：scheduler.py → storage.py → ui.py。算法使用整数、列表/字典、排序和贪心；界面只有一个主要PlannerApp类。根目录demo1.py是启动入口，不是生成的大文件。保留整个course_demo文件夹，不能只复制入口。

## 运行

在项目根目录执行，要求Python 3.11+和Tkinter（标准Windows Python自带）：

```powershell
python .\demo1.py
```

成功标志：出现任务侧栏和周日历。默认英文，可选择中文；全部时间按本机设置输入和显示。界面启动不写文件，选择Save才保存。

## 使用

1. **New**：填写标题、总分钟和截止时间。剩余默认等于总分钟；Advanced可填写开始、剩余、重要性和是否可拆。

   成功标志：任务出现在左侧列表；Edit、Progress、Complete、Delete直接操作选中任务。

2. **点击日历空白**：创建忙碌时段；点击灰色块编辑或删除。Today、左右箭头、Week/Day只切换视图。

   成功标志：忙碌时段显示为灰块；不会因为翻页改变任务。

3. **Generate**：在未来若干天的日历空白排程。Settings选择edf/importance/risk、最小/最大块和规划天数。Compare可比较三策略，再Apply某个结果。

   成功标志：日历出现安排，状态区显示已排、未排和原因；不会把计划算作学习完成。空白包含夜间，请将不希望排程的时间标为忙碌。

4. **点击计划块，再Lock / unlock**：保留未来的安排。普通任务修改保留锁定并清除旧的自动安排；若剩余工作量少于锁定分钟，需要先解锁。Complete/Delete经确认后移除相关锁。

   成功标志：锁定块标识改变，重排保留其时间。已开始的块不能新锁定，已有过去锁可解除后核对进度。

5. **File → Save**：默认存入work/course-demo/workspace.json。Open加载课程版，Save as另存；关闭未保存工作会询问保存/放弃/取消。

   成功标志：标题星号清除；重启同一路径可恢复。覆盖前保留.bak，发现磁盘被修改时拒绝保存，可另存新路径。

## 导入原版本

File → Import legacy选择原work/demo1-data/workspace.json，导入后Save会要求另存。原文件不修改，旧自动计划清空，保留任务、忙碌及显式锁；旧窗口内不可用的部分转换成忙碌，窗口外仍采用课程版的规划天数。过去的锁须先解除。零总工作量或已删除等不支持的旧记录会明确报错，不静默丢弃。

默认存档与旧版本隔离。也可指定课程版路径：`python demo1.py --data work/my-course.json`。不要对旧文件使用这个选项来替代导入。

## 学习与测试

[代码阅读指南](../docs/scheduler/COURSE_CODE_GUIDE.md)提供数据结构、算法伪代码及手算例子。[本轮验收](../docs/scheduler/COURSE_REFACTOR_VERIFICATION.md)记录实际范围。

运行课程测试会在项目work/创建合成临时数据：

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
python -m unittest discover -s tests_course -v
```

成功标志：29项测试通过。原python_scheduler/仅为历史高级版本与回归参考，当前程序不导入它。
