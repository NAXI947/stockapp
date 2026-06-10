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
    config = load_config(ROOT / 'config.yaml')
    database = build_database(config)
    database.init_schema()
    lock = JobLock(database, "job_weekly")
    if not lock.acquire():
        raise SystemExit("job_weekly is already running")
    logger = JobRunLogger(database)
    notifier = build_job_alert_notifier(config)
    run_id = logger.start("job_weekly", "weekly", "weekly", config.jobs.max_workers, config.jobs.timeout_seconds)
    stage_logger = JobStageLogger(database, run_id, "job_weekly")
    table_logger = JobTableLogger(database, run_id, "job_weekly")
    client = build_client(config)

    def on_stage(stage_name, duration_seconds, status, extra, message):
        try:
            stage_logger.log(stage_name, duration_seconds, status=status, extra=extra, message=message)
        except Exception as stage_exc:
            print(f"job_weekly stage log warning: {stage_exc}")

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
        summary = service.run_weekly_sync(stage_callback=on_stage)
        print_sync_summary(summary, job_name='job_weekly')
        table_logger.log_summary(summary)
        finish_meta = logger.finish("success", "weekly stock basic + sw industry sync complete")
        if finish_meta['timed_out']:
            notifier.notify_job_issue(
                "job_weekly",
                "weekly",
                "weekly",
                "success",
                "job exceeded timeout threshold",
                finish_meta['duration_seconds'],
                True,
            )
    except BaseException as exc:
        table_logger.log_table('__job__', 0, status='failed', message=str(exc))
        finish_meta = logger.finish("failed", str(exc))
        notifier.notify_job_issue(
            "job_weekly",
            "weekly",
            "weekly",
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
