from __future__ import annotations

import json
from typing import Any, Dict

try:
    import pymysql
    from pymysql.cursors import DictCursor
except ImportError:  # pragma: no cover - runtime dependency
    pymysql = None
    DictCursor = None

from .utils import parse_bool, parse_dict_int, parse_dict_float

RUNTIME_KEY_PREFIX = 'jobs.'
RUNTIME_JOB_KEYS = {
    'max_workers',
    'timeout_seconds',
    'qps_limit',
    'qps_burst',
    'retry_max_attempts',
    'retry_base_delay',
    'retry_max_delay',
    'heartbeat_interval_seconds',
    'verbose_request_logs',
    'api_qps_limits',
    'api_concurrency_limits',
    'table_concurrency_limits',
}


def normalize_job_runtime_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for key, value in payload.items():
        if key not in RUNTIME_JOB_KEYS:
            continue
        if key == 'max_workers':
            parsed = int(value)
            if parsed not in {10, 20, 50, 70}:
                raise ValueError('jobs.max_workers must be one of: 10, 20, 50, 70')
            normalized[key] = parsed
        elif key in {'timeout_seconds', 'qps_burst', 'retry_max_attempts', 'heartbeat_interval_seconds'}:
            parsed = int(value)
            if parsed <= 0:
                raise ValueError(f'jobs.{key} must be > 0')
            if key == 'heartbeat_interval_seconds':
                parsed = max(parsed, 5)
            normalized[key] = parsed
        elif key in {'qps_limit', 'retry_base_delay', 'retry_max_delay'}:
            parsed = float(value)
            if parsed <= 0:
                raise ValueError(f'jobs.{key} must be > 0')
            normalized[key] = parsed
        elif key == 'verbose_request_logs':
            normalized[key] = parse_bool(value)
        elif key == 'api_qps_limits':
            normalized[key] = parse_dict_float(value)
        elif key in {'api_concurrency_limits', 'table_concurrency_limits'}:
            normalized[key] = parse_dict_int(value)
        else:
            normalized[key] = value
    if 'retry_base_delay' in normalized and 'retry_max_delay' in normalized:
        if float(normalized['retry_max_delay']) < float(normalized['retry_base_delay']):
            raise ValueError('jobs.retry_max_delay must be >= jobs.retry_base_delay')
    return normalized


def _safe_normalize(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return normalize_job_runtime_settings(payload)
    except Exception:
        return {}


def encode_runtime_value(key: str, value: Any) -> str:
    if key in {'api_qps_limits', 'api_concurrency_limits', 'table_concurrency_limits'}:
        return json.dumps(value or {}, ensure_ascii=True, separators=(',', ':'))
    if key == 'verbose_request_logs':
        return 'true' if parse_bool(value) else 'false'
    return str(value)


def decode_runtime_value(key: str, raw_value: Any) -> Any:
    if key == 'api_qps_limits':
        return parse_dict_float(raw_value)
    if key in {'api_concurrency_limits', 'table_concurrency_limits'}:
        return parse_dict_int(raw_value)
    if key == 'max_workers':
        return int(raw_value)
    if key in {'timeout_seconds', 'qps_burst', 'retry_max_attempts', 'heartbeat_interval_seconds'}:
        return int(raw_value)
    if key in {'qps_limit', 'retry_base_delay', 'retry_max_delay'}:
        return float(raw_value)
    if key == 'verbose_request_logs':
        return parse_bool(raw_value)
    return raw_value


def ensure_runtime_config_table(database) -> None:
    if database.driver == 'sqlite':
        database.execute(
            '''
            CREATE TABLE IF NOT EXISTS t_runtime_config (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              config_key TEXT NOT NULL,
              config_value TEXT NOT NULL,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              UNIQUE (config_key)
            )
            '''
        )
        database.execute('CREATE INDEX IF NOT EXISTS idx_runtime_config_updated_at ON t_runtime_config (updated_at)')
        return
    database.execute(
        '''
        CREATE TABLE IF NOT EXISTS t_runtime_config (
          id BIGINT NOT NULL AUTO_INCREMENT,
          config_key VARCHAR(128) NOT NULL,
          config_value TEXT NOT NULL,
          updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          UNIQUE KEY uq_runtime_config_key (config_key),
          KEY idx_runtime_config_updated_at (updated_at)
        )
        '''
    )


def get_runtime_jobs_config(database) -> Dict[str, Any]:
    ensure_runtime_config_table(database)
    sql = "SELECT config_key, config_value FROM t_runtime_config WHERE config_key LIKE %s"
    params = (f'{RUNTIME_KEY_PREFIX}%',)
    rows = database.fetch_all(sql, params)
    jobs: Dict[str, Any] = {}
    for row in rows:
        config_key = str(row['config_key'])
        if not config_key.startswith(RUNTIME_KEY_PREFIX):
            continue
        key = config_key[len(RUNTIME_KEY_PREFIX):]
        if key not in RUNTIME_JOB_KEYS:
            continue
        jobs[key] = decode_runtime_value(key, row['config_value'])
    return _safe_normalize(jobs)


def set_runtime_jobs_config(database, updates: Dict[str, Any]) -> Dict[str, Any]:
    ensure_runtime_config_table(database)
    normalized = normalize_job_runtime_settings(updates)
    if not normalized:
        return get_runtime_jobs_config(database)
    if database.driver == 'sqlite':
        sql = (
            "INSERT INTO t_runtime_config (config_key, config_value) VALUES (%s, %s) "
            "ON CONFLICT(config_key) DO UPDATE SET "
            "config_value=excluded.config_value, updated_at=CURRENT_TIMESTAMP"
        )
    else:
        sql = (
            "INSERT INTO t_runtime_config (config_key, config_value) VALUES (%s, %s) "
            "ON DUPLICATE KEY UPDATE config_value=VALUES(config_value)"
        )
    for key, value in normalized.items():
        database.execute(sql, (f'{RUNTIME_KEY_PREFIX}{key}', encode_runtime_value(key, value)))
    return get_runtime_jobs_config(database)


def load_runtime_jobs_overrides_from_storage(
    driver: str,
    host: str,
    port: int,
    user: str,
    password: str,
    name: str,
    path: str = '',
) -> Dict[str, Any]:
    if driver != 'mysql' or pymysql is None:
        return {}
    try:
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=name,
            charset='utf8mb4',
            autocommit=True,
            cursorclass=DictCursor,
        )
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_schema=%s AND table_name='t_runtime_config' LIMIT 1",
                (name,),
            )
            if cursor.fetchone() is None:
                return {}
            cursor.execute(
                "SELECT config_key, config_value FROM t_runtime_config WHERE config_key LIKE %s",
                (f'{RUNTIME_KEY_PREFIX}%',),
            )
            rows = cursor.fetchall()
        finally:
            cursor.close()
            conn.close()
    except Exception:
        return {}

    jobs: Dict[str, Any] = {}
    for row in rows:
        config_key = str(row['config_key'])
        key = config_key[len(RUNTIME_KEY_PREFIX):]
        if key not in RUNTIME_JOB_KEYS:
            continue
        try:
            jobs[key] = decode_runtime_value(key, row['config_value'])
        except Exception:
            continue
    try:
        return _safe_normalize(jobs)
    except Exception:
        return {}
