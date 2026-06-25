from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from backend.app.job_lock import JobLock


class _LockDatabase:
    def __init__(self, row=None):
        self.row = row
        self.executed = []

    def fetch_all(self, sql, params=()):
        return [dict(self.row)] if self.row else []

    def execute(self, sql, params=()):
        self.executed.append((sql, tuple(params)))
        if sql.startswith('INSERT'):
            self.row = {
                'job_name': params[0],
                'lock_token': params[1],
                'expires_at': params[2],
            }
        elif sql.startswith('UPDATE'):
            self.row = {
                'job_name': params[2],
                'lock_token': params[0],
                'expires_at': params[1],
            }
        elif sql.startswith('DELETE'):
            self.row = None


def _future_time():
    return (datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')


def _time_ago(seconds):
    return (datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=seconds)).strftime('%Y-%m-%d %H:%M:%S')


def test_acquire_replaces_stale_local_process_lock(monkeypatch):
    lock = JobLock(_LockDatabase(), 'job_daily')
    owner = {
        'id': 'old',
        'host': lock.host,
        'pid': 999999,
        'created_at': '2026-06-24 00:00:00',
    }
    database = _LockDatabase(
        {
            'job_name': 'job_daily',
            'lock_token': json.dumps(owner),
            'expires_at': _future_time(),
        }
    )
    lock = JobLock(database, 'job_daily')
    monkeypatch.setattr(lock, '_is_process_running', lambda pid: False)

    assert lock.acquire() is True
    assert database.executed[-1][0].startswith('UPDATE')


def test_acquire_keeps_live_local_process_lock(monkeypatch):
    lock = JobLock(_LockDatabase(), 'job_daily')
    owner = {
        'id': 'old',
        'host': lock.host,
        'pid': 1234,
        'created_at': '2026-06-24 00:00:00',
    }
    database = _LockDatabase(
        {
            'job_name': 'job_daily',
            'lock_token': json.dumps(owner),
            'expires_at': _future_time(),
        }
    )
    lock = JobLock(database, 'job_daily')
    monkeypatch.setattr(lock, '_is_process_running', lambda pid: True)

    assert lock.acquire() is False
    assert database.executed == []


def test_acquire_preserves_foreign_or_legacy_active_lock():
    database = _LockDatabase(
        {
            'job_name': 'job_daily',
            'lock_token': 'legacy-token',
            'expires_at': _future_time(),
            'updated_at': _time_ago(60),
        }
    )
    lock = JobLock(database, 'job_daily')

    assert lock.acquire() is False
    assert database.executed == []


def test_acquire_replaces_legacy_lock_near_timeout():
    database = _LockDatabase(
        {
            'job_name': 'job_daily',
            'lock_token': 'legacy-token',
            'expires_at': _future_time(),
            'updated_at': _time_ago(5 * 60 * 60 + 40 * 60),
        }
    )
    lock = JobLock(database, 'job_daily')

    assert lock.acquire() is True
    assert database.executed[-1][0].startswith('UPDATE')
