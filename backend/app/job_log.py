from __future__ import annotations

import math
import time
from typing import Optional

from .local_job_log_store import next_run_id, write_json_log


class JobRunLogger:
    def __init__(self, database):
        self.database = database
        self.run_id: Optional[int] = None
        self.timeout_seconds: int = 21600
        self.started_at_monotonic: Optional[float] = None

    def start(self, job_name: str, run_mode: str, target_range: str, max_workers: int, timeout_seconds: int) -> int:
        self.timeout_seconds = timeout_seconds
        self.started_at_monotonic = time.monotonic()
        self.run_id = next_run_id()
        write_json_log(
            'job_run.log',
            {
                'event': 'start',
                'run_id': self.run_id,
                'job_name': job_name,
                'run_mode': run_mode,
                'target_range': target_range,
                'max_workers': int(max_workers),
                'timeout_seconds': int(timeout_seconds),
                'status': 'running',
                'ts': int(time.time()),
            },
        )
        return self.run_id

    def finish(self, status: str, message: str = "") -> dict:
        if self.run_id is None:
            return {'timed_out': False, 'duration_seconds': None}
        duration_seconds = None
        elapsed_seconds = None
        if self.started_at_monotonic is not None:
            elapsed_seconds = max(time.monotonic() - self.started_at_monotonic, 0.0)
            duration_seconds = int(math.ceil(elapsed_seconds))
        timed_out = bool(elapsed_seconds is not None and elapsed_seconds > self.timeout_seconds)
        write_json_log(
            'job_run.log',
            {
                'event': 'finish',
                'run_id': self.run_id,
                'status': status,
                'timed_out': bool(timed_out),
                'duration_seconds': duration_seconds,
                'message': message,
                'ts': int(time.time()),
            },
        )
        return {'timed_out': timed_out, 'duration_seconds': duration_seconds}
