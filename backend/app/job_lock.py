from __future__ import annotations

import json
import os
import socket
from datetime import UTC, datetime, timedelta
from uuid import uuid4


class JobLock:
    def __init__(self, database, job_name: str, ttl_seconds: int = 21600):
        self.database = database
        self.job_name = job_name
        self.ttl_seconds = ttl_seconds
        self.host = socket.gethostname().lower()
        self.pid = os.getpid()
        self.token = self._build_token()
        self.acquired = False

    def acquire(self) -> bool:
        current = self._get()
        now = self._utcnow()
        expires_at = now + timedelta(seconds=self.ttl_seconds)
        if current:
            current_expires_at = self._parse_time(current.get('expires_at'))
            if (
                current_expires_at
                and current_expires_at > now
                and current.get('lock_token') != self.token
                and not self._is_stale_lock(current, current_expires_at, now)
            ):
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
        self._update_lock(self._utcnow() + timedelta(seconds=self.ttl_seconds))

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
            'SELECT job_name, lock_token, expires_at, updated_at FROM t_job_lock WHERE job_name = %s LIMIT 1',
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

    def _build_token(self) -> str:
        return json.dumps(
            {
                'id': uuid4().hex,
                'host': self.host,
                'pid': self.pid,
                'created_at': self._format_time(self._utcnow()),
            },
            separators=(',', ':'),
        )

    def _is_stale_lock(self, lock_row, expires_at: datetime, now: datetime) -> bool:
        owner = self._parse_owner(lock_row.get('lock_token'))
        if owner:
            return self._is_stale_local_owner(owner)
        return self._is_stale_legacy_lock(lock_row, expires_at, now)

    def _is_stale_local_owner(self, owner) -> bool:
        if owner.get('host') != self.host:
            return False
        pid = owner.get('pid')
        if not isinstance(pid, int) or pid <= 0:
            return False
        return not self._is_process_running(pid)

    def _is_stale_legacy_lock(self, lock_row, expires_at: datetime, now: datetime) -> bool:
        updated_at = self._parse_time(lock_row.get('updated_at'))
        if not updated_at:
            return False
        lock_age_seconds = (now - updated_at).total_seconds()
        remaining_seconds = (expires_at - now).total_seconds()
        legacy_takeover_seconds = max(self.ttl_seconds * 0.8, self.ttl_seconds - 1800)
        return lock_age_seconds >= legacy_takeover_seconds or remaining_seconds <= 0

    @staticmethod
    def _parse_owner(token):
        if not token:
            return None
        try:
            owner = json.loads(str(token))
        except (TypeError, ValueError):
            return None
        if not isinstance(owner, dict):
            return None
        return owner

    @staticmethod
    def _is_process_running(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(UTC).replace(tzinfo=None)
