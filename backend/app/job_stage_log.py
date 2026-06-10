from __future__ import annotations

import math
import time
from typing import Any

from .local_job_log_store import write_json_log


class JobStageLogger:
    def __init__(self, database, run_id: int | None, job_name: str):
        self.database = database
        self.run_id = run_id
        self.job_name = job_name

    def log(
        self,
        stage_name: str,
        duration_seconds: float,
        status: str = 'success',
        extra: dict[str, Any] | None = None,
        message: str = '',
    ) -> None:
        duration_ms = max(int(math.ceil(duration_seconds * 1000)), 0)
        write_json_log(
            'job_stage.log',
            {
                'run_id': self.run_id,
                'job_name': self.job_name,
                'stage_name': stage_name,
                'status': status,
                'duration_ms': duration_ms,
                'extra': extra or {},
                'message': message,
                'ts': int(time.time()),
            },
        )
