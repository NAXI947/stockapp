from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.job_log_report import (
    DEFAULT_LOG_DIR,
    _build_run_records,
    _filter_runs,
    _read_json_lines,
    _timestamp_to_iso,
)


def list_job_runs(
    *,
    log_dir: str | Path | None = None,
    days: int = 7,
    limit: int = 20,
    job_name: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    base_dir = Path(log_dir) if log_dir else DEFAULT_LOG_DIR
    run_records = _read_json_lines(base_dir / "job_run.log")
    runs = _build_run_records(run_records)
    filtered_runs = _filter_runs(runs, days=days, job_name=job_name, status=status)

    return {
        "log_dir": str(base_dir),
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "window_days": max(days, 1),
        "job_name": job_name,
        "status": status,
        "items": filtered_runs[:limit],
        "total": len(filtered_runs),
    }


def get_job_failure_detail(
    *,
    run_id: int,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    base_dir = Path(log_dir) if log_dir else DEFAULT_LOG_DIR
    run_records = _read_json_lines(base_dir / "job_run.log")
    stage_records = _read_json_lines(base_dir / "job_stage.log")
    table_records = _read_json_lines(base_dir / "job_table.log")
    runs = _build_run_records(run_records)
    target_run = next((run for run in runs if int(run.get("run_id") or 0) == run_id), None)
    if not target_run:
        raise ValueError(f"run_id {run_id} not found")

    failed_stages = []
    for record in stage_records:
        try:
            current_run_id = int(record.get("run_id"))
        except Exception:
            continue
        if current_run_id != run_id or str(record.get("status") or "success") == "success":
            continue
        failed_stages.append(
            {
                "stage_name": str(record.get("stage_name") or ""),
                "status": str(record.get("status") or "unknown"),
                "duration_ms": int(record.get("duration_ms") or 0),
                "message": str(record.get("message") or ""),
                "logged_at": _timestamp_to_iso(record.get("ts")),
                "extra": record.get("extra") or {},
            }
        )

    failed_tables = []
    for record in table_records:
        try:
            current_run_id = int(record.get("run_id"))
        except Exception:
            continue
        if current_run_id != run_id or str(record.get("status") or "success") == "success":
            continue
        failed_tables.append(
            {
                "table_name": str(record.get("table_name") or ""),
                "fetched_rows": int(record.get("fetched_rows") or 0),
                "status": str(record.get("status") or "unknown"),
                "message": str(record.get("message") or ""),
                "missing_fields": record.get("missing_fields") or [],
                "null_fields": record.get("null_fields") or {},
                "metrics": record.get("metrics") or {},
                "logged_at": _timestamp_to_iso(record.get("ts")),
            }
        )

    recent_failures = [
        run
        for run in runs
        if run.get("job_name") == target_run.get("job_name")
        and run.get("status") == "failed"
        and int(run.get("run_id") or 0) != run_id
    ][:10]

    return {
        "log_dir": str(base_dir),
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "run": target_run,
        "failed_stages": failed_stages,
        "failed_tables": failed_tables,
        "recent_failures": recent_failures,
    }


def summarize_table_trends(
    *,
    log_dir: str | Path | None = None,
    days: int = 7,
    limit: int = 20,
    job_name: str | None = None,
) -> dict[str, Any]:
    base_dir = Path(log_dir) if log_dir else DEFAULT_LOG_DIR
    run_records = _read_json_lines(base_dir / "job_run.log")
    table_records = _read_json_lines(base_dir / "job_table.log")
    runs = _build_run_records(run_records)
    selected_runs = _filter_runs(runs, days=days, job_name=job_name, status=None)
    selected_run_ids = {int(run["run_id"]) for run in selected_runs if run.get("run_id") is not None}

    trends: dict[str, dict[str, Any]] = {}
    for record in table_records:
        try:
            run_id = int(record.get("run_id"))
        except Exception:
            continue
        if selected_run_ids and run_id not in selected_run_ids:
            continue
        table_name = str(record.get("table_name") or "")
        if not table_name:
            continue
        current = trends.setdefault(
            table_name,
            {
                "table_name": table_name,
                "run_count": 0,
                "failed_count": 0,
                "total_rows": 0,
                "avg_rows": 0.0,
                "max_rows": 0,
                "total_null_field_count": 0,
                "latest_run_id": run_id,
                "latest_at": None,
                "latest_status": "unknown",
                "latest_message": "",
                "latest_null_fields": {},
                "latest_metrics": {},
            },
        )
        fetched_rows = int(record.get("fetched_rows") or 0)
        null_fields = record.get("null_fields") or {}
        current["run_count"] += 1
        current["total_rows"] += fetched_rows
        current["max_rows"] = max(current["max_rows"], fetched_rows)
        current["total_null_field_count"] += sum(int(value or 0) for value in null_fields.values())
        if str(record.get("status") or "success") != "success":
            current["failed_count"] += 1

        ts_value = int(record.get("ts") or 0)
        latest_run_id = int(current.get("latest_run_id") or 0)
        latest_at = current.get("_latest_ts") or 0
        if ts_value > latest_at or (ts_value == latest_at and run_id >= latest_run_id):
            current["_latest_ts"] = ts_value
            current["latest_run_id"] = run_id
            current["latest_at"] = _timestamp_to_iso(ts_value)
            current["latest_status"] = str(record.get("status") or "unknown")
            current["latest_message"] = str(record.get("message") or "")
            current["latest_null_fields"] = null_fields
            current["latest_metrics"] = record.get("metrics") or {}

    items = []
    for item in trends.values():
        run_count = int(item["run_count"] or 0)
        item["avg_rows"] = round(item["total_rows"] / run_count, 2) if run_count else 0.0
        item.pop("_latest_ts", None)
        items.append(item)

    items.sort(key=lambda item: (-int(item["total_rows"]), item["table_name"]))
    return {
        "log_dir": str(base_dir),
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "window_days": max(days, 1),
        "job_name": job_name,
        "items": items[:limit],
        "total": len(items),
    }


def summarize_failure_trends(
    *,
    log_dir: str | Path | None = None,
    days: int = 7,
    job_name: str | None = None,
) -> dict[str, Any]:
    base_dir = Path(log_dir) if log_dir else DEFAULT_LOG_DIR
    run_records = _read_json_lines(base_dir / "job_run.log")
    runs = _build_run_records(run_records)
    selected_runs = _filter_runs(runs, days=days, job_name=job_name, status=None)

    daily_summary: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"date": "", "total_runs": 0, "failed_runs": 0, "failure_rate": 0.0}
    )
    job_summary: dict[str, dict[str, Any]] = {}
    streak_runs = [
        run for run in runs if (not job_name or run.get("job_name") == job_name)
    ]

    current_streak = 0
    max_streak = 0
    for run in streak_runs:
        status = str(run.get("status") or "unknown")
        if status == "failed":
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            break
    rolling_streak = 0
    for run in reversed(streak_runs):
        status = str(run.get("status") or "unknown")
        if status == "failed":
            rolling_streak += 1
            max_streak = max(max_streak, rolling_streak)
        else:
            rolling_streak = 0

    for run in selected_runs:
        run_date = str(run.get("finished_at") or run.get("started_at") or "")[:10]
        if run_date:
            daily = daily_summary[run_date]
            daily["date"] = run_date
            daily["total_runs"] += 1
            if str(run.get("status") or "unknown") == "failed":
                daily["failed_runs"] += 1

        current_job_name = str(run.get("job_name") or "unknown")
        summary = job_summary.setdefault(
            current_job_name,
            {
                "job_name": current_job_name,
                "total_runs": 0,
                "failed_runs": 0,
                "latest_status": "unknown",
                "latest_run_id": int(run.get("run_id") or 0),
                "latest_at": run.get("finished_at") or run.get("started_at"),
            },
        )
        summary["total_runs"] += 1
        if str(run.get("status") or "unknown") == "failed":
            summary["failed_runs"] += 1

    daily_items = []
    for item in daily_summary.values():
        total_runs = int(item["total_runs"] or 0)
        item["failure_rate"] = round((int(item["failed_runs"] or 0) / total_runs) if total_runs else 0.0, 4)
        daily_items.append(item)
    daily_items.sort(key=lambda item: item["date"], reverse=True)

    job_items = []
    for item in job_summary.values():
        total_runs = int(item["total_runs"] or 0)
        item["failure_rate"] = round((int(item["failed_runs"] or 0) / total_runs) if total_runs else 0.0, 4)
        job_items.append(item)
    job_items.sort(key=lambda item: (-int(item["failed_runs"]), item["job_name"]))

    latest_failure = next((run for run in selected_runs if str(run.get("status") or "unknown") == "failed"), None)

    return {
        "log_dir": str(base_dir),
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "window_days": max(days, 1),
        "job_name": job_name,
        "current_failure_streak": current_streak,
        "max_failure_streak": max_streak,
        "latest_failure": latest_failure,
        "daily": daily_items,
        "jobs": job_items,
    }


def build_job_stage_metrics(
    *,
    log_dir: str | Path | None = None,
    days: int = 7,
    limit: int = 200,
    job_name: str | None = None,
    run_id: int | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    base_dir = Path(log_dir) if log_dir else DEFAULT_LOG_DIR
    run_records = _read_json_lines(base_dir / "job_run.log")
    stage_records = _read_json_lines(base_dir / "job_stage.log")
    runs = _build_run_records(run_records)
    selected_runs = _filter_runs(runs, days=days, job_name=job_name, status=None)
    allowed_run_ids = {int(run["run_id"]) for run in selected_runs if run.get("run_id") is not None}

    items = []
    summary_map: dict[str, dict[str, Any]] = {}
    for record in reversed(stage_records):
        try:
            current_run_id = int(record.get("run_id"))
        except Exception:
            continue
        if allowed_run_ids and current_run_id not in allowed_run_ids:
            continue
        if run_id is not None and current_run_id != run_id:
            continue
        current_job_name = str(record.get("job_name") or "")
        if job_name and current_job_name != job_name:
            continue
        current_status = str(record.get("status") or "unknown")
        if status and current_status != status:
            continue
        stage_name = str(record.get("stage_name") or "")
        duration_ms = int(record.get("duration_ms") or 0)
        item = {
            "id": len(items) + 1,
            "run_id": current_run_id,
            "job_name": current_job_name,
            "stage_name": stage_name,
            "status": current_status,
            "duration_ms": duration_ms,
            "created_at": _timestamp_to_iso(record.get("ts")),
            "extra": record.get("extra") or {},
            "message": record.get("message"),
        }
        items.append(item)

        summary = summary_map.setdefault(
            stage_name,
            {
                "stage_name": stage_name,
                "total_count": 0,
                "failed_count": 0,
                "total_duration_ms": 0,
                "avg_duration_ms": 0.0,
                "max_duration_ms": 0,
            },
        )
        summary["total_count"] += 1
        if current_status != "success":
            summary["failed_count"] += 1
        summary["total_duration_ms"] += duration_ms
        summary["max_duration_ms"] = max(summary["max_duration_ms"], duration_ms)

    limited_items = list(reversed(items[-limit:]))
    summary_items = []
    for item in summary_map.values():
        total_count = int(item["total_count"] or 0)
        item["avg_duration_ms"] = round(item["total_duration_ms"] / total_count, 2) if total_count else 0.0
        summary_items.append(item)
    summary_items.sort(key=lambda entry: (-int(entry["total_duration_ms"]), entry["stage_name"]))

    return {
        "log_dir": str(base_dir),
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "window_days": max(days, 1),
        "job_name": job_name,
        "run_id": run_id,
        "status": status,
        "items": limited_items,
        "summary": summary_items,
    }
