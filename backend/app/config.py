from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from .paths import project_root, resource_path, runtime_root
from .runtime_config import load_runtime_jobs_overrides_from_storage
from .utils import parse_bool as _parse_bool, parse_list as _parse_list, parse_dict_int as _parse_dict_int, parse_dict_float as _parse_dict_float

@dataclass
class DatabaseConfig:
    driver: str
    host: str
    port: int
    user: str
    password: str
    name: str
    pool_size: int
    pool_timeout: int
    path: str = ''
    sqlite_path: str = ''


@dataclass
class TushareConfig:
    token: str
    base_url: str
    use_mock: bool = False
    timeout_seconds: int = 30


@dataclass
class JobsConfig:
    max_workers: int = 10
    timeout_seconds: int = 21600
    qps_limit: float = 3.0
    qps_burst: int = 6
    retry_max_attempts: int = 3
    retry_base_delay: float = 0.5
    retry_max_delay: float = 8.0
    api_qps_limits: Dict[str, float] | None = None
    api_concurrency_limits: Dict[str, int] | None = None
    table_concurrency_limits: Dict[str, int] | None = None
    heartbeat_interval_seconds: int = 30
    verbose_request_logs: bool = False


@dataclass
class AlertConfig:
    enabled: bool = False
    webhook_url: str = ''


@dataclass
class SecurityConfig:
    auth_enabled: bool = False
    api_token: str = ''
    rate_limit_per_minute: int = 120
    cors_origins: List[str] | None = None


@dataclass
class AiConfig:
    enabled: bool = False
    provider: str = 'openai_compatible'
    base_url: str = ''
    api_key: str = ''
    model: str = ''
    models: List[str] | None = None
    prompt_strategy: str = 'auto'
    timeout_seconds: int = 20


@dataclass
class AppConfig:
    environment: str
    database: DatabaseConfig
    tushare: TushareConfig
    jobs: JobsConfig
    alert: AlertConfig
    security: SecurityConfig
    ai: AiConfig


DEFAULT_CONFIG_PATH = project_root() / 'config.yaml'
SUPPORTED_ENVIRONMENTS = {'dev', 'prod', 'test', 'desktop'}


def _load_structured_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    content = path.read_text(encoding='utf-8').strip()
    if not content:
        return {}
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise ValueError(f'Unable to parse config file {path}: install PyYAML or use JSON syntax.') from exc
        loaded = yaml.safe_load(content)
        return loaded or {}


def _write_structured_config(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import yaml  # type: ignore
    except ImportError:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        return
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding='utf-8')


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _apply_env_overrides(raw: Dict[str, Any]) -> Dict[str, Any]:
    result = _deep_merge(raw, {})
    result.setdefault('database', {})
    result.setdefault('tushare', {})
    result.setdefault('jobs', {})
    result.setdefault('alert', {})
    result.setdefault('security', {})
    result.setdefault('ai', {})

    env = os.environ
    mapping = {
        ('database', 'driver'): env.get('DB_DRIVER'),
        ('database', 'host'): env.get('DB_HOST'),
        ('database', 'port'): env.get('DB_PORT'),
        ('database', 'user'): env.get('DB_USER'),
        ('database', 'password'): env.get('DB_PASSWORD'),
        ('database', 'name'): env.get('DB_NAME'),
        ('database', 'path'): env.get('DB_PATH'),
        ('database', 'pool_size'): env.get('DB_POOL_SIZE'),
        ('database', 'pool_timeout'): env.get('DB_POOL_TIMEOUT'),
        ('tushare', 'token'): env.get('TUSHARE_TOKEN'),
        ('tushare', 'base_url'): env.get('TUSHARE_BASE_URL'),
        ('tushare', 'use_mock'): env.get('TUSHARE_USE_MOCK'),
        ('tushare', 'timeout_seconds'): env.get('TUSHARE_TIMEOUT_SECONDS'),
        ('jobs', 'max_workers'): env.get('JOBS_MAX_WORKERS'),
        ('jobs', 'timeout_seconds'): env.get('JOB_TIMEOUT_SECONDS'),
        ('jobs', 'qps_limit'): env.get('JOB_QPS_LIMIT'),
        ('jobs', 'qps_burst'): env.get('JOB_QPS_BURST'),
        ('jobs', 'retry_max_attempts'): env.get('JOB_RETRY_MAX_ATTEMPTS'),
        ('jobs', 'retry_base_delay'): env.get('JOB_RETRY_BASE_DELAY'),
        ('jobs', 'retry_max_delay'): env.get('JOB_RETRY_MAX_DELAY'),
        ('jobs', 'api_qps_limits'): env.get('JOB_API_QPS_LIMITS'),
        ('jobs', 'api_concurrency_limits'): env.get('JOB_API_CONCURRENCY_LIMITS'),
        ('jobs', 'table_concurrency_limits'): env.get('JOB_TABLE_CONCURRENCY_LIMITS'),
        ('jobs', 'heartbeat_interval_seconds'): env.get('JOB_HEARTBEAT_INTERVAL_SECONDS'),
        ('jobs', 'verbose_request_logs'): env.get('JOB_VERBOSE_REQUEST_LOGS'),
        ('alert', 'enabled'): env.get('ALERT_ENABLED'),
        ('alert', 'webhook_url'): env.get('ALERT_WEBHOOK_URL'),
        ('security', 'auth_enabled'): env.get('API_AUTH_ENABLED'),
        ('security', 'api_token'): env.get('API_AUTH_TOKEN'),
        ('security', 'rate_limit_per_minute'): env.get('API_RATE_LIMIT_PER_MINUTE'),
        ('security', 'cors_origins'): env.get('API_CORS_ORIGINS'),
        ('ai', 'enabled'): env.get('AI_ENABLED'),
        ('ai', 'provider'): env.get('AI_PROVIDER'),
        ('ai', 'base_url'): env.get('AI_BASE_URL'),
        ('ai', 'api_key'): env.get('AI_API_KEY'),
        ('ai', 'model'): env.get('AI_MODEL'),
        ('ai', 'models'): env.get('AI_MODELS'),
        ('ai', 'prompt_strategy'): env.get('AI_PROMPT_STRATEGY'),
        ('ai', 'timeout_seconds'): env.get('AI_TIMEOUT_SECONDS'),
    }
    for (section, key), value in mapping.items():
        if value is not None and value != '':
            result[section][key] = value
    return result


def _load_raw_config(path: Path) -> Dict[str, Any]:
    base = _load_structured_config(path)
    file_environment = str(base.get('app', {}).get('env', 'dev')).strip().lower()
    environment = os.environ.get('APP_ENV', file_environment).strip().lower()
    if environment not in SUPPORTED_ENVIRONMENTS:
        raise ValueError(f'APP_ENV must be one of: {", ".join(sorted(SUPPORTED_ENVIRONMENTS))}')
    overlay_path = path.with_name(f'config.{environment}.yaml')
    if environment == 'desktop':
        desktop_overlay = runtime_root() / 'config.desktop.yaml'
        if desktop_overlay.exists():
            overlay_path = desktop_overlay
    if not overlay_path.exists():
        overlay_path = resource_path(f'config.{environment}.yaml')
    merged = _deep_merge(base, _load_structured_config(overlay_path))
    merged['app'] = _deep_merge(merged.get('app', {}), {'env': environment})
    with_env = _apply_env_overrides(merged)
    db = with_env.get('database', {})
    runtime_jobs = load_runtime_jobs_overrides_from_storage(
        driver=str(db.get('driver', 'mysql')),
        host=str(db.get('host', '127.0.0.1')),
        port=int(db.get('port', 3306)),
        user=str(db.get('user', 'root')),
        password=str(db.get('password', '')),
        name=str(db.get('name', 'linuxstock_db')),
        path=str(db.get('path', 'data/stocknew.db')),
    )
    if runtime_jobs:
        with_env.setdefault('jobs', {})
        with_env['jobs'] = _deep_merge(with_env.get('jobs', {}), runtime_jobs)
    return with_env


def get_desktop_config_path() -> Path:
    return runtime_root() / 'config.desktop.yaml'


def load_desktop_config_for_update() -> Dict[str, Any]:
    path = get_desktop_config_path()
    if path.exists():
        return _load_structured_config(path)
    bundled = resource_path('config.desktop.yaml')
    return _load_structured_config(bundled)


def save_desktop_tushare_token(token: str) -> Dict[str, Any]:
    value = token.strip()
    if not value:
        raise ValueError('Tushare token cannot be empty.')
    raw = load_desktop_config_for_update()
    raw.setdefault('app', {})['env'] = 'desktop'
    raw.setdefault('tushare', {})['token'] = value
    path = get_desktop_config_path()
    _write_structured_config(path, raw)
    os.environ['TUSHARE_TOKEN'] = value
    return {
        'configured': True,
        'config_path': str(path),
        'masked_token': mask_secret(value),
    }


def get_desktop_tushare_status() -> Dict[str, Any]:
    raw = load_desktop_config_for_update()
    token = str(raw.get('tushare', {}).get('token', '') or os.environ.get('TUSHARE_TOKEN', '') or '')
    return {
        'configured': bool(token.strip()),
        'config_path': str(get_desktop_config_path()),
        'masked_token': mask_secret(token),
    }


def mask_secret(value: str) -> str:
    token = value.strip()
    if not token:
        return ''
    if len(token) <= 8:
        return '*' * len(token)
    return f'{token[:4]}{"*" * (len(token) - 8)}{token[-4:]}'


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    raw = _load_raw_config(config_path)
    db = raw['database']
    ts = raw['tushare']
    jobs = raw.get('jobs', {})
    alert = raw.get('alert', {})
    security = raw.get('security', {})
    ai = raw.get('ai', {})
    max_workers = int(jobs.get('max_workers', 10))
    if max_workers not in {10, 20, 50, 70}:
        raise ValueError('jobs.max_workers must be one of: 10, 20, 50, 70')
    timeout_seconds = max(int(jobs.get('timeout_seconds', 21600)), 1)
    qps_limit = max(float(jobs.get('qps_limit', 3.0)), 0.1)
    qps_burst = max(int(jobs.get('qps_burst', 6)), 1)
    retry_max_attempts = max(int(jobs.get('retry_max_attempts', 3)), 1)
    retry_base_delay = max(float(jobs.get('retry_base_delay', 0.5)), 0.01)
    retry_max_delay = max(float(jobs.get('retry_max_delay', 8.0)), retry_base_delay)
    api_qps_limits = _parse_dict_float(jobs.get('api_qps_limits', {}))
    api_concurrency_limits = _parse_dict_int(jobs.get('api_concurrency_limits', {}))
    table_concurrency_limits = _parse_dict_int(jobs.get('table_concurrency_limits', {}))
    heartbeat_interval_seconds = max(int(jobs.get('heartbeat_interval_seconds', 30)), 5)
    verbose_request_logs = _parse_bool(jobs.get('verbose_request_logs', False))
    driver = db.get('driver', 'mysql')
    default_pool_size = max(max_workers, 10)
    return AppConfig(
        environment=str(raw.get('app', {}).get('env', 'dev')),
        database=DatabaseConfig(
            driver=driver,
            host=db.get('host', '127.0.0.1'),
            port=int(db.get('port', 3306)),
            user=db.get('user', 'root'),
            password=db.get('password', ''),
            name=db.get('name', 'linuxstock_db'),
            pool_size=max(int(db.get('pool_size', default_pool_size)), 1),
            pool_timeout=max(int(db.get('pool_timeout', 15)), 1),
            path=str(db.get('path', 'data/stocknew.db') or 'data/stocknew.db'),
            sqlite_path=str(db.get('path', 'data/stocknew.db') or 'data/stocknew.db'),
        ),
        tushare=TushareConfig(
            token=ts.get('token', ''),
            base_url=ts.get('base_url', 'https://api.tushare.pro'),
            use_mock=_parse_bool(ts.get('use_mock', False)),
            timeout_seconds=max(int(ts.get('timeout_seconds', 30)), 5),
        ),
        jobs=JobsConfig(
            max_workers=max_workers,
            timeout_seconds=timeout_seconds,
            qps_limit=qps_limit,
            qps_burst=qps_burst,
            retry_max_attempts=retry_max_attempts,
            retry_base_delay=retry_base_delay,
            retry_max_delay=retry_max_delay,
            api_qps_limits=api_qps_limits,
            api_concurrency_limits=api_concurrency_limits,
            table_concurrency_limits=table_concurrency_limits,
            heartbeat_interval_seconds=heartbeat_interval_seconds,
            verbose_request_logs=verbose_request_logs,
        ),
        alert=AlertConfig(
            enabled=_parse_bool(alert.get('enabled', False)),
            webhook_url=str(alert.get('webhook_url', '') or ''),
        ),
        security=SecurityConfig(
            auth_enabled=_parse_bool(security.get('auth_enabled', False)),
            api_token=str(security.get('api_token', '') or ''),
            rate_limit_per_minute=max(int(security.get('rate_limit_per_minute', 120)), 1),
            cors_origins=_parse_list(
                security.get(
                    'cors_origins',
                    ['http://localhost:5173', 'http://127.0.0.1:5173'],
                )
            ),
        ),
        ai=AiConfig(
            enabled=_parse_bool(ai.get('enabled', False)),
            provider=str(ai.get('provider', 'openai_compatible') or 'openai_compatible'),
            base_url=str(ai.get('base_url', '') or ''),
            api_key=str(ai.get('api_key', '') or ''),
            model=str(ai.get('model', '') or ''),
            models=_parse_list(ai.get('models', [])),
            prompt_strategy=str(ai.get('prompt_strategy', 'auto') or 'auto'),
            timeout_seconds=max(int(ai.get('timeout_seconds', 20)), 1),
        ),
    )
