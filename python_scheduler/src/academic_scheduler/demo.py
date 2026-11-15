"""Optional fixed synthetic examples, separate from the interactive product."""

from dataclasses import replace

from .demo_cases import DEMO_EXAMPLES
from .engine import schedule
from .models import parse_request, result_to_dict
from .validation import validate_result


_CASE_TITLES = {"feasible": "可行案例", "overloaded": "超载案例", "replan": "锁定重排案例"}
_REASON_TITLES = {
    "deadline_passed": "截止时间已到", "outside_window": "任务窗口为空",
    "no_available_capacity": "任务窗口已无空闲容量",
    "insufficient_contiguous_capacity": "没有足够连续容量",
    "below_min_block": "剩余空档短于最小块长", "insufficient_capacity": "剩余容量不足",
}


class DemoValidationError(RuntimeError):
    pass


def run_demo(example="all", strategy="all"):
    """Run optional synthetic examples without changing the personal workspace."""
    names = tuple(DEMO_EXAMPLES) if example == "all" else (example,)
    strategies = ("edf", "importance", "risk") if strategy == "all" else (strategy,)
    cases = []
    for name in names:
        request = parse_request(DEMO_EXAMPLES[name])
        results = []
        for selected in strategies:
            variant = replace(request, strategy=selected)
            result = schedule(variant)
            errors = validate_result(variant, result)
            if errors:
                raise DemoValidationError("; ".join(errors))
            results.append(result_to_dict(result, variant.timezone))
        cases.append({"name": name, "title": _CASE_TITLES[name], "results": results})
    return {"demo": "Demo 1", "timezone": "UTC", "cases": cases}


def print_demo(report):
    print("Demo 1 — 合成案例演示（UTC）")
    print("个人任务请运行无参数入口进入工作区；以下指标表示计划安排。")
    for case in report["cases"]:
        print(f"\n{case['title']} ({case['name']})")
        for result in case["results"]:
            metrics = result["metrics"]
            print(f"  {result['strategy']:10} 已排 {metrics['scheduled_minutes']}/{metrics['requested_minutes']} 分钟；"
                  f"未排 {metrics['unscheduled_minutes']} 分钟；"
                  f"完整安排 {metrics['fully_scheduled_tasks']}/{metrics['eligible_tasks']} 项；校验通过")
        selected = case["results"][0]
        for block in selected["blocks"]:
            task = block["task_id"] or "固定预留"
            locked = f"，锁定 {block['locked_id']}" if block["source"] == "locked" else ""
            print(f"    {block['start']} → {block['end']}  {task}  {block['minutes']} 分钟{locked}")
        for item in selected["unscheduled"]:
            reasons = "；".join(_REASON_TITLES[r] for r in item["reasons"])
            print(f"    未排：{item['task_id']}，{item['minutes']} 分钟，{reasons}")
    print("\n演示完成：所有结果通过独立约束校验。")
