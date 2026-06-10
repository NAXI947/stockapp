from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.config import load_config
from backend.app.job_alert import build_job_alert_notifier
from backend.app.ingest import DataIngestionService, print_sync_summary
from backend.app.job_checkpoint import JobCheckpointStore
from backend.app.job_lock import JobLock
from backend.app.job_log import JobRunLogger
from backend.app.job_stage_log import JobStageLogger
from backend.app.job_table_log import JobTableLogger
from backend.app.runtime import build_client, build_client_factory, build_database


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run history sync')
    parser.add_argument('start_date', help='start date in YYYYMMDD')
    parser.add_argument('end_date', help='end date in YYYYMMDD')
    parser.add_argument('--force', action='store_true', help='ignore checkpoint and rerun full range')
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start_date, end_date = args.start_date, args.end_date
    config = load_config(ROOT / 'config.yaml')
    database = build_database(config)
    database.init_schema()
    lock = JobLock(database, "job_history")
    if not lock.acquire():
        raise SystemExit("job_history is already running")
    logger = JobRunLogger(database)
    checkpoint = JobCheckpointStore(database)
    notifier = build_job_alert_notifier(config)
    job_name = "job_history"
    target_range = f"{start_date}:{end_date}"
    run_id = logger.start(job_name, "history", target_range, config.jobs.max_workers, config.jobs.timeout_seconds)
    stage_logger = JobStageLogger(database, run_id, job_name)
    table_logger = JobTableLogger(database, run_id, job_name)
    checkpoint.mark_running(job_name, target_range)
    resume_start = start_date if args.force else checkpoint.get_resume_start(job_name, target_range, start_date)
    print(f"[history] target_range={target_range} resume_start={resume_start}", flush=True)

    def on_stage(stage_name, duration_seconds, status, extra, message):
        try:
            stage_logger.log(stage_name, duration_seconds, status=status, extra=extra, message=message)
        except Exception as stage_exc:
            print(f"job_history stage log warning: {stage_exc}")

    try:
        client = build_client(config)
        if resume_start > end_date:
            print(f"job_history: already completed for {target_range}")
            checkpoint.mark_success(job_name, target_range)
            table_logger.log_table('__job__', 0, status='success', message=f"already completed for {target_range}")
            finish_meta = logger.finish("success", f"already completed for {target_range}")
            if finish_meta['timed_out']:
                notifier.notify_job_issue(
                    job_name,
                    "history",
                    target_range,
                    "success",
                    "job exceeded timeout threshold",
                    finish_meta['duration_seconds'],
                    True,
                )
            return
        service = DataIngestionService(
            client,
            database,
            max_workers=config.jobs.max_workers,
            client_factory=build_client_factory(config),
            qps_limit=config.jobs.qps_limit,
            qps_burst=config.jobs.qps_burst,
            retry_max_attempts=config.jobs.retry_max_attempts,
            retry_base_delay=config.jobs.retry_base_delay,
            retry_max_delay=config.jobs.retry_max_delay,
            api_qps_limits=config.jobs.api_qps_limits,
            api_concurrency_limits=config.jobs.api_concurrency_limits,
            table_concurrency_limits=config.jobs.table_concurrency_limits,
            heartbeat_interval_seconds=config.jobs.heartbeat_interval_seconds,
            verbose_request_logs=config.jobs.verbose_request_logs,
        )
        summary = service.run_history_sync(
            start_date=resume_start,
            end_date=end_date,
            progress_callback=lambda trade_date: checkpoint.mark_progress(job_name, target_range, trade_date),
            stage_callback=on_stage,
        )
        print_sync_summary(summary, job_name='job_history')
        table_logger.log_summary(summary)
        checkpoint.mark_success(job_name, target_range)
        finish_meta = logger.finish("success", f"synced {len(summary)} tables")
        if finish_meta['timed_out']:
            notifier.notify_job_issue(
                job_name,
                "history",
                target_range,
                "success",
                "job exceeded timeout threshold",
                finish_meta['duration_seconds'],
                True,
            )
    except BaseException as exc:
        checkpoint.mark_failed(job_name, target_range)
        table_logger.log_table('__job__', 0, status='failed', message=str(exc))
        finish_meta = logger.finish("failed", str(exc))
        notifier.notify_job_issue(
            job_name,
            "history",
            target_range,
            "failed",
            str(exc),
            finish_meta['duration_seconds'],
            finish_meta['timed_out'],
        )
        raise
    finally:
        lock.release()
        database.close()


if __name__ == '__main__':
    main()
