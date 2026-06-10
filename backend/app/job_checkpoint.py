from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional


class JobCheckpointStore:
    def __init__(self, database):
        self.database = database

    def get_resume_start(self, job_name: str, target_range: str, requested_start: str) -> str:
        row = self._get(job_name, target_range)
        if not row or not row.get("last_completed_trade_date"):
            return requested_start
        try:
            next_day = (
                datetime.strptime(row["last_completed_trade_date"], "%Y%m%d").date() + timedelta(days=1)
            ).strftime("%Y%m%d")
            return max(requested_start, next_day)
        except Exception:
            return requested_start

    def get_incremental_start(
        self,
        job_name: str,
        target_range: str,
        requested_start: str,
        requested_end: str | None = None,
    ) -> str:
        row = self._get(job_name, target_range)
        if not row:
            return requested_start
        if row.get("status") == "success":
            completed = str(row.get("last_completed_trade_date") or "")
            if requested_end and completed >= requested_end:
                return self.get_resume_start(job_name, target_range, requested_start)
            return requested_start
        return self.get_resume_start(job_name, target_range, requested_start)

    def start_incremental_run(
        self,
        job_name: str,
        target_range: str,
        requested_start: str,
        requested_end: str | None = None,
    ) -> str:
        row = self._get(job_name, target_range)
        start_date = self.get_incremental_start(
            job_name,
            target_range,
            requested_start,
            requested_end=requested_end,
        )
        if row and row.get("status") in {"running", "failed"}:
            self.mark_running(job_name, target_range)
            return start_date
        try:
            baseline = (
                datetime.strptime(start_date, "%Y%m%d").date() - timedelta(days=1)
            ).strftime("%Y%m%d")
        except Exception:
            self.mark_running(job_name, target_range)
            return start_date
        self.mark_progress(job_name, target_range, baseline)
        return start_date

    def mark_running(self, job_name: str, target_range: str) -> None:
        current = self._get(job_name, target_range)
        if current:
            self.database.execute(
                "UPDATE t_job_checkpoint SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                ("running", current["id"]),
            )
            return
        self.database.execute(
            "INSERT INTO t_job_checkpoint (job_name, target_range, status) VALUES (%s, %s, %s)",
            (job_name, target_range, "running"),
        )

    def mark_progress(self, job_name: str, target_range: str, trade_date: str) -> None:
        if self.database.driver == 'sqlite':
            sql = """
                INSERT INTO t_job_checkpoint (job_name, target_range, last_completed_trade_date, status)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT(job_name, target_range) DO UPDATE SET
                  last_completed_trade_date = excluded.last_completed_trade_date,
                  status = excluded.status,
                  updated_at = CURRENT_TIMESTAMP
                """
        else:
            sql = """
                INSERT INTO t_job_checkpoint (job_name, target_range, last_completed_trade_date, status)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  last_completed_trade_date = VALUES(last_completed_trade_date),
                  status = VALUES(status),
                  updated_at = CURRENT_TIMESTAMP
                """
        self.database.execute(sql, (job_name, target_range, trade_date, "running"))

    def mark_success(self, job_name: str, target_range: str) -> None:
        current = self._get(job_name, target_range)
        if not current:
            return
        self.database.execute(
            "UPDATE t_job_checkpoint SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            ("success", current["id"]),
        )

    def mark_failed(self, job_name: str, target_range: str) -> None:
        current = self._get(job_name, target_range)
        if not current:
            return
        self.database.execute(
            "UPDATE t_job_checkpoint SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            ("failed", current["id"]),
        )

    def _get(self, job_name: str, target_range: str) -> Optional[dict]:
        rows = self.database.fetch_all(
            "SELECT * FROM t_job_checkpoint WHERE job_name = %s AND target_range = %s LIMIT 1",
            (job_name, target_range),
        )
        return dict(rows[0]) if rows else None
