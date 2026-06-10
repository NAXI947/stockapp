from __future__ import annotations

import contextlib
import os
import re
import runpy
import sys
import threading
import time
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.app.paths import resource_path, runtime_root


@dataclass
class ManualJobTask:
    task_id: str
    job_name: str
    label: str
    status: str
    started_at: str
    finished_at: str | None = None
    return_code: int | None = None
    message: str = ""
    log_file: str = ""


JOB_DEFINITIONS: dict[str, dict[str, Any]] = {
    "daily": {
        "label": "日更",
        "steps": [
            ("job_daily_common.py", []),
            ("job_daily_featured.py", []),
            ("job_daily_strategy.py", ["--latest-only"]),
        ],
    },
    "update_date": {
        "label": "按日期更新",
        "steps": [
            ("job_daily_common.py", ["{date}", "--light"]),
            ("job_daily_featured.py", ["{date}"]),
            ("job_daily_strategy.py", ["{date}"]),
        ],
    },
    "weekly": {"label": "全量周更", "steps": [("job_weekly.py", [])]},
    "monthly": {"label": "全量月更", "steps": [("job_monthly.py", [])]},
    "yearly": {"label": "全量年更", "steps": [("job_quarterly.py", []), ("job_yearly.py", [])]},
}

_TASKS: dict[str, ManualJobTask] = {}
_TASK_LOCK = threading.Lock()
_RUN_LOCK = threading.Lock()
MAX_MANUAL_TASKS = 6


def list_job_definitions() -> list[dict[str, str]]:
    return [{"name": name, "label": definition["label"]} for name, definition in JOB_DEFINITIONS.items()]


def list_manual_tasks() -> list[dict[str, Any]]:
    with _TASK_LOCK:
        _prune_tasks_locked()
        return [_task_payload(task) for task in _sorted_tasks_locked()]


def run_manual_job(job_name: str, args: list[str] | None = None) -> ManualJobTask:
    if job_name not in JOB_DEFINITIONS:
        raise ValueError(f"Unknown job: {job_name}")
    if _has_running_task(job_name):
        raise RuntimeError(f"{JOB_DEFINITIONS[job_name]['label']} 正在运行")

    task_id = str(int(time.time() * 1000))
    log_dir = runtime_root() / "logs" / "manual_jobs"
    log_dir.mkdir(parents=True, exist_ok=True)
    safe_args = args or []
    task_label = JOB_DEFINITIONS[job_name]["label"]
    if job_name == "history" and len(safe_args) >= 2:
        task_label = f"{task_label} {safe_args[0]}-{safe_args[1]}"
    elif job_name == "update_date" and safe_args:
        task_label = f"{task_label} {safe_args[0]}"
    task = ManualJobTask(
        task_id=task_id,
        job_name=job_name,
        label=task_label,
        status="running",
        started_at=_now(),
        log_file=str(log_dir / f"{task_id}_{job_name}.log"),
    )
    with _TASK_LOCK:
        _TASKS[task_id] = task
        _prune_tasks_locked()

    thread = threading.Thread(target=_run_task, args=(task, safe_args), name=f"manual-job-{job_name}", daemon=True)
    thread.start()
    return task


def _has_running_task(job_name: str) -> bool:
    with _TASK_LOCK:
        return any(task.job_name == job_name and task.status == "running" for task in _TASKS.values())


def _sorted_tasks_locked() -> list[ManualJobTask]:
    return sorted(_TASKS.values(), key=lambda item: item.started_at, reverse=True)


def _prune_tasks_locked() -> None:
    if len(_TASKS) <= MAX_MANUAL_TASKS:
        return
    sorted_tasks = _sorted_tasks_locked()
    keep_ids = {task.task_id for task in sorted_tasks[:MAX_MANUAL_TASKS]}
    for task_id in list(_TASKS):
        if task_id not in keep_ids:
            del _TASKS[task_id]


def _run_task(task: ManualJobTask, args: list[str]) -> None:
    try:
        with _RUN_LOCK:
            _execute_steps(task, args)
        _finish_task(task, "success", 0, "完成")
    except SystemExit as exc:
        code = int(exc.code) if isinstance(exc.code, int) else 1
        _finish_task(task, "success" if code == 0 else "failed", code, str(exc))
    except Exception as exc:
        _append_log(task, traceback.format_exc())
        _finish_task(task, "failed", 1, str(exc))


def _execute_steps(task: ManualJobTask, run_args: list[str]) -> None:
    os.environ.setdefault("APP_ENV", "desktop")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    steps = JOB_DEFINITIONS[task.job_name]["steps"]
    with Path(task.log_file).open("a", encoding="utf-8") as log:
        for index, (script_name, args) in enumerate(steps, start=1):
            step_args = list(args)
            if task.job_name == "history":
                step_args.extend(run_args)
            elif task.job_name == "update_date":
                if not run_args:
                    raise ValueError("update_date requires YYYYMMDD")
                step_args = [arg.replace("{date}", run_args[0]) for arg in step_args]
            script_path = resource_path(f"jobs/{script_name}")
            log.write(f"[{_now()}] step {index}/{len(steps)} start: {script_name} {' '.join(step_args)}\n")
            log.flush()
            original_argv = sys.argv[:]
            sys.argv = [str(script_path), *step_args]
            try:
                with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                    runpy.run_path(str(script_path), run_name="__main__")
            finally:
                sys.argv = original_argv
            log.write(f"[{_now()}] step {index}/{len(steps)} success: {script_name}\n")
            log.flush()


def _finish_task(task: ManualJobTask, status: str, return_code: int, message: str) -> None:
    with _TASK_LOCK:
        task.status = status
        task.return_code = return_code
        task.message = message
        task.finished_at = _now()
    _append_log(task, f"[{task.finished_at}] {status}: {message}\n")


def _append_log(task: ManualJobTask, text: str) -> None:
    Path(task.log_file).parent.mkdir(parents=True, exist_ok=True)
    with Path(task.log_file).open("a", encoding="utf-8") as log:
        log.write(text)


def _task_payload(task: ManualJobTask) -> dict[str, Any]:
    payload = asdict(task)
    payload["progress"] = _parse_log_progress(Path(task.log_file))
    return payload


def _parse_log_progress(log_path: Path) -> dict[str, Any]:
    progress: dict[str, Any] = {
        "percent": None,
        "current": "",
        "detail": "",
        "stage": "",
        "updated_at": "",
    }
    if not log_path.exists():
        return progress

    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-120:]
    except OSError:
        return progress

    latest_heartbeat: str | None = None
    for line in lines:
        if "[stage] start " in line:
            stage_match = re.search(r"\[stage\] start ([^\s]+)", line)
            if stage_match:
                progress["stage"] = stage_match.group(1)
                progress["current"] = _stage_label(progress["stage"])
            trade_date_match = re.search(r"'trade_date': '(\d{8})'", line)
            if trade_date_match:
                progress["detail"] = f"交易日 {trade_date_match.group(1)}"
        elif "[progress]" in line:
            _apply_progress_line(progress, line)
        elif "[heartbeat]" in line:
            latest_heartbeat = line

    if latest_heartbeat and not progress["detail"]:
        fetched = _extract_int(latest_heartbeat, "fetched")
        upserted = _extract_int(latest_heartbeat, "upserted")
        if upserted is not None:
            progress["detail"] = f"已入库 {upserted} 行"
        elif fetched is not None:
            progress["detail"] = f"已获取 {fetched} 行"
        heartbeat_percent = re.search(r"progress=([\d.]+)%", latest_heartbeat)
        if heartbeat_percent and progress["percent"] is None:
            progress["percent"] = round(float(heartbeat_percent.group(1)))

    progress["updated_at"] = _extract_log_time(lines[-1]) if lines else ""
    return progress


def _apply_progress_line(progress: dict[str, Any], line: str) -> None:
    table_match = re.search(
        r"\[progress\]\s+(\w+)\s+batch\s+(\d+)/(\d+).*?\(([\d.]+)%\).*?inserted=(\d+)",
        line,
    )
    if table_match:
        table_name, batch, total, percent, inserted = table_match.groups()
        progress["current"] = table_name
        progress["percent"] = round(float(percent))
        progress["detail"] = f"批次 {batch}/{total}，已入库 {inserted} 行"
        return

    history_match = re.search(
        r"\[progress\]\s+history trade_date\s+(\d+)/(\d+).*?\(([\d.]+)%\)\s+current=(\d{8})",
        line,
    )
    if history_match:
        done, total, percent, trade_date = history_match.groups()
        progress["current"] = "历史交易日"
        progress["percent"] = round(float(percent))
        progress["detail"] = f"交易日 {done}/{total}，当前 {trade_date}"
        return

    strategy_match = re.search(
        r"\[progress\]\s+t_strategy_daily batch\s+(\d+)/(\d+).*?inserted=(\d+)",
        line,
    )
    if strategy_match:
        batch, total, inserted = strategy_match.groups()
        progress["current"] = "t_strategy_daily"
        progress["percent"] = round(int(batch) / max(int(total), 1) * 100)
        progress["detail"] = f"批次 {batch}/{total}，已入库 {inserted} 行"
        return

    impact_match = re.search(
        r"\[progress\]\s+t_strategy_daily impact_date\s+(\d+)/(\d+)\s+current=(\d{8}).*?inserted=(\d+)",
        line,
    )
    if impact_match:
        done, total, trade_date, inserted = impact_match.groups()
        progress["current"] = "局部重算策略"
        progress["percent"] = round(int(done) / max(int(total), 1) * 100)
        progress["detail"] = f"交易日 {done}/{total}，当前 {trade_date}，已入库 {inserted} 行"


def _stage_label(stage: str) -> str:
    return {
        "sync_reference_tables": "更新基础参考表",
        "history_sync_market_by_date": "更新行情数据",
        "history_sync_date_supplemental": "更新补充指标",
        "build_strategy_daily": "计算策略分数",
        "sync_market_tables": "更新行情数据",
        "sync_common_date_supplemental_tables": "更新龙虎榜",
        "sync_featured_date_supplemental_tables": "更新特色指标",
        "sync_static_supplemental_tables": "更新静态补充表",
        "sync_t_concept_detail": "更新概念明细",
        "sync_t_share_float": "更新限售解禁",
        "sync_t_fin_indicator": "更新财务指标",
        "sync_sw_industry_mapping": "更新申万行业",
        "rebuild_strategy_daily_full": "全量重算策略",
    }.get(stage, stage)


def _extract_int(text: str, key: str) -> int | None:
    match = re.search(rf"{re.escape(key)}=(\d+)", text)
    return int(match.group(1)) if match else None


def _extract_log_time(text: str) -> str:
    match = re.match(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]", text)
    return match.group(1) if match else ""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
