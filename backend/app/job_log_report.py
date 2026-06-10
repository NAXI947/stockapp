from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOG_DIR = ROOT / 'logs'


def _read_json_lines(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open('r', encoding='utf-8') as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                records.append(payload)
    return records


def _timestamp_to_iso(value: Any) -> str | None:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
    except Exception:
        return None


def _build_run_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    runs: dict[int, dict[str, Any]] = {}
    for record in records:
        run_id = record.get('run_id')
        if run_id is None:
            continue
        try:
            run_id = int(run_id)
        except Exception:
            continue
        existing = runs.setdefault(
            run_id,
            {
                'run_id': run_id,
                'job_name': None,
                'run_mode': None,
                'target_range': None,
                'max_workers': None,
                'timeout_seconds': None,
                'started_ts': None,
                'started_at': None,
                'finished_ts': None,
                'finished_at': None,
                'status': 'unknown',
                'timed_out': False,
                'duration_seconds': None,
                'message': '',
            },
        )
        event = str(record.get('event') or '')
        ts_value = record.get('ts')
        if event == 'start':
            existing['job_name'] = record.get('job_name')
            existing['run_mode'] = record.get('run_mode')
            existing['target_range'] = record.get('target_range')
            existing['max_workers'] = record.get('max_workers')
            existing['timeout_seconds'] = record.get('timeout_seconds')
            existing['started_ts'] = ts_value
            existing['started_at'] = _timestamp_to_iso(ts_value)
            existing['status'] = str(record.get('status') or 'running')
        elif event == 'finish':
            existing['status'] = str(record.get('status') or existing['status'] or 'unknown')
            existing['timed_out'] = bool(record.get('timed_out'))
            existing['duration_seconds'] = record.get('duration_seconds')
            existing['message'] = str(record.get('message') or '')
            existing['finished_ts'] = ts_value
            existing['finished_at'] = _timestamp_to_iso(ts_value)
    return sorted(
        runs.values(),
        key=lambda item: (
            int(item.get('started_ts') or 0),
            int(item.get('finished_ts') or 0),
            int(item.get('run_id') or 0),
        ),
        reverse=True,
    )


def _filter_runs(
    runs: list[dict[str, Any]],
    *,
    days: int,
    job_name: str | None,
    status: str | None,
) -> list[dict[str, Any]]:
    cutoff_ts = int(datetime.now(tz=timezone.utc).timestamp()) - max(days, 1) * 86400
    filtered: list[dict[str, Any]] = []
    for run in runs:
        if job_name and run.get('job_name') != job_name:
            continue
        if status and run.get('status') != status:
            continue
        run_ts = int(run.get('finished_ts') or run.get('started_ts') or 0)
        if run_ts < cutoff_ts:
            continue
        filtered.append(run)
    return filtered


def _summarize_stage_records(
    records: list[dict[str, Any]],
    *,
    selected_run_ids: set[int],
    limit: int,
) -> list[dict[str, Any]]:
    stage_summary: dict[str, dict[str, Any]] = {}
    for record in records:
        run_id = record.get('run_id')
        if run_id is None:
            continue
        try:
            run_id = int(run_id)
        except Exception:
            continue
        if selected_run_ids and run_id not in selected_run_ids:
            continue
        stage_name = str(record.get('stage_name') or '')
        if not stage_name:
            continue
        current = stage_summary.setdefault(
            stage_name,
            {
                'stage_name': stage_name,
                'count': 0,
                'failed_count': 0,
                'total_duration_ms': 0,
                'avg_duration_ms': 0.0,
                'max_duration_ms': 0,
                'latest_status': 'unknown',
                'latest_run_id': run_id,
                'latest_ts': 0,
            },
        )
        duration_ms = int(record.get('duration_ms') or 0)
        current['count'] += 1
        current['total_duration_ms'] += duration_ms
        current['max_duration_ms'] = max(current['max_duration_ms'], duration_ms)
        if str(record.get('status') or 'success') != 'success':
            current['failed_count'] += 1
        ts_value = int(record.get('ts') or 0)
        if ts_value >= int(current['latest_ts']):
            current['latest_ts'] = ts_value
            current['latest_status'] = str(record.get('status') or 'unknown')
            current['latest_run_id'] = run_id
    items = []
    for item in stage_summary.values():
        count = int(item['count'] or 0)
        item['avg_duration_ms'] = round(item['total_duration_ms'] / count, 2) if count else 0.0
        item['latest_at'] = _timestamp_to_iso(item.get('latest_ts'))
        item.pop('latest_ts', None)
        items.append(item)
    items.sort(key=lambda item: (-int(item['total_duration_ms']), item['stage_name']))
    return items[:limit]


def _latest_run_tables(records: list[dict[str, Any]], run_id: int | None) -> list[dict[str, Any]]:
    if run_id is None:
        return []
    items = []
    for record in records:
        try:
            current_run_id = int(record.get('run_id'))
        except Exception:
            continue
        if current_run_id != run_id:
            continue
        items.append(
            {
                'table_name': str(record.get('table_name') or ''),
                'fetched_rows': int(record.get('fetched_rows') or 0),
                'status': str(record.get('status') or 'unknown'),
                'missing_fields': record.get('missing_fields') or [],
                'null_fields': record.get('null_fields') or {},
                'metrics': record.get('metrics') or {},
                'message': str(record.get('message') or ''),
                'logged_at': _timestamp_to_iso(record.get('ts')),
            }
        )
    items.sort(key=lambda item: (-int(item['fetched_rows']), item['table_name']))
    return items


def build_job_log_report(
    *,
    log_dir: str | Path | None = None,
    days: int = 7,
    limit: int = 10,
    job_name: str | None = None,
) -> dict[str, Any]:
    base_dir = Path(log_dir) if log_dir else DEFAULT_LOG_DIR
    run_records = _read_json_lines(base_dir / 'job_run.log')
    stage_records = _read_json_lines(base_dir / 'job_stage.log')
    table_records = _read_json_lines(base_dir / 'job_table.log')

    runs = _build_run_records(run_records)
    latest_run = next((run for run in runs if not job_name or run.get('job_name') == job_name), None)
    recent_failures = _filter_runs(runs, days=days, job_name=job_name, status='failed')[:limit]
    selected_runs = _filter_runs(runs, days=days, job_name=job_name, status=None)
    selected_run_ids = {int(run['run_id']) for run in selected_runs if run.get('run_id') is not None}
    stage_summary = _summarize_stage_records(stage_records, selected_run_ids=selected_run_ids, limit=limit)

    status_counts: dict[str, int] = defaultdict(int)
    for run in selected_runs:
        status_counts[str(run.get('status') or 'unknown')] += 1

    return {
        'log_dir': str(base_dir),
        'generated_at': datetime.now(tz=timezone.utc).isoformat(),
        'window_days': max(days, 1),
        'job_name': job_name,
        'latest_run': latest_run,
        'recent_failures': recent_failures,
        'stage_summary': stage_summary,
        'status_counts': dict(sorted(status_counts.items())),
        'latest_run_tables': _latest_run_tables(table_records, int(latest_run['run_id'])) if latest_run else [],
    }
