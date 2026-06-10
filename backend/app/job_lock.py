from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4


class JobLock:
    def __init__(self, database, job_name: str, ttl_seconds: int = 21600):
        self.database = database
        self.job_name = job_name
        self.ttl_seconds = ttl_seconds
        self.token = uuid4().hex
        self.acquired = False

    def acquire(self) -> bool:
        current = self._get()
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=self.ttl_seconds)
        if current:
            current_expires_at = self._parse_time(current.get('expires_at'))
            if current_expires_at and current_expires_at > now and current.get('lock_token') != self.token:
                return False
            self._update_lock(expires_at)
            self.acquired = True
            return True
        try:
            self._insert_lock(expires_at)
            self.acquired = True
            return True
        except Exception:
            current = self._get()
            current_expires_at = self._parse_time(current.get('expires_at')) if current else None
            if current and current_expires_at and current_expires_at <= now:
                self._update_lock(expires_at)
                self.acquired = True
                return True
            return False

    def refresh(self) -> None:
        if not self.acquired:
            return
        self._update_lock(datetime.utcnow() + timedelta(seconds=self.ttl_seconds))

    def release(self) -> None:
        if not self.acquired:
            return
        self.database.execute(
            'DELETE FROM t_job_lock WHERE job_name = %s AND lock_token = %s',
            (self.job_name, self.token),
        )
        self.acquired = False

    def _get(self):
        rows = self.database.fetch_all(
            'SELECT job_name, lock_token, expires_at FROM t_job_lock WHERE job_name = %s LIMIT 1',
            (self.job_name,),
        )
        return dict(rows[0]) if rows else None

    def _insert_lock(self, expires_at: datetime) -> None:
        expires_value = self._format_time(expires_at)
        self.database.execute(
            'INSERT INTO t_job_lock (job_name, lock_token, expires_at, updated_at) VALUES (%s, %s, %s, CURRENT_TIMESTAMP)',
            (self.job_name, self.token, expires_value),
        )

    def _update_lock(self, expires_at: datetime) -> None:
        expires_value = self._format_time(expires_at)
        self.database.execute(
            'UPDATE t_job_lock SET lock_token = %s, expires_at = %s, updated_at = CURRENT_TIMESTAMP WHERE job_name = %s',
            (self.token, expires_value, self.job_name),
        )

    @staticmethod
    def _format_time(value: datetime) -> str:
        return value.strftime('%Y-%m-%d %H:%M:%S')

    @staticmethod
    def _parse_time(value):
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f'):
            try:
                return datetime.strptime(str(value), fmt)
            except ValueError:
                continue
        return None
