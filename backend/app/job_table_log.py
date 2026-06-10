from __future__ import annotations

import time
from typing import Any, Dict

from .local_job_log_store import write_json_log


class JobTableLogger:
    def __init__(self, database, run_id: int | None, job_name: str):
        self.database = database
        self.run_id = run_id
        self.job_name = job_name

    def log_summary(self, summary: Dict[str, Dict[str, Any]]) -> None:
        for table_name, stats in summary.items():
            self.log_table(
                table_name=table_name,
                fetched_rows=int(stats.get('rows', 0) or 0),
                missing_fields=stats.get('missing_fields', []),
                null_fields=stats.get('null_fields', {}),
                metrics=stats.get('metrics', {}),
            )

    def log_table(
        self,
        table_name: str,
        fetched_rows: int,
        missing_fields: list[str] | None = None,
        null_fields: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        status: str = 'success',
        message: str = '',
    ) -> None:
        write_json_log(
            'job_table.log',
            {
                'run_id': self.run_id,
                'job_name': self.job_name,
                'table_name': table_name,
                'fetched_rows': int(fetched_rows),
                'missing_fields': missing_fields or [],
                'null_fields': null_fields or {},
                'metrics': metrics or {},
                'status': status,
                'message': message,
                'ts': int(time.time()),
            },
        )
