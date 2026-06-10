from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.config import load_config
from backend.app.job_alert import build_job_alert_notifier
from backend.app.ingest import DataIngestionService, print_sync_summary
from backend.app.job_lock import JobLock
from backend.app.job_log import JobRunLogger
from backend.app.job_stage_log import JobStageLogger
from backend.app.job_table_log import JobTableLogger
from backend.app.runtime import build_client, build_client_factory, build_database


def main() -> None:
    trade_date = sys.argv[1] if len(sys.argv) > 1 else None
    config = load_config(ROOT / 'config.yaml')
    database = build_database(config)
    database.init_schema()
    lock = JobLock(database, "job_daily")
    if not lock.acquire():
        raise SystemExit("job_daily is already running")
    logger = JobRunLogger(database)
    target_range = trade_date or "latest"
    notifier = build_job_alert_notifier(config)
    run_id = logger.start("job_daily", "daily", target_range, config.jobs.max_workers, config.jobs.timeout_seconds)
    stage_logger = JobStageLogger(database, run_id, "job_daily")
    table_logger = JobTableLogger(database, run_id, "job_daily")
    client = build_client(config)

    def on_stage(stage_name, duration_seconds, status, extra, message):
        try:
            stage_logger.log(stage_name, duration_seconds, status=status, extra=extra, message=message)
        except Exception as stage_exc:
            print(f"job_daily stage log warning: {stage_exc}")

    try:
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
        summary = service.run_full_sync(trade_date=trade_date, stage_callback=on_stage)
        print_sync_summary(summary, job_name='job_daily')
        table_logger.log_summary(summary)
        finish_meta = logger.finish("success", f"synced {len(summary)} tables")
        if finish_meta['timed_out']:
            notifier.notify_job_issue(
                "job_daily",
                "daily",
                target_range,
                "success",
                "job exceeded timeout threshold",
                finish_meta['duration_seconds'],
                True,
            )
    except BaseException as exc:
        table_logger.log_table('__job__', 0, status='failed', message=str(exc))
        finish_meta = logger.finish("failed", str(exc))
        notifier.notify_job_issue(
            "job_daily",
            "daily",
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
