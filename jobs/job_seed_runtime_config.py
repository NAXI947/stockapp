from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.config import load_config
from backend.app.runtime import build_database
from backend.app.runtime_config import set_runtime_jobs_config


def _runtime_seed_payload(config: Any) -> dict[str, Any]:
    return {
        'max_workers': config.jobs.max_workers,
        'timeout_seconds': config.jobs.timeout_seconds,
        'qps_limit': config.jobs.qps_limit,
        'qps_burst': config.jobs.qps_burst,
        'retry_max_attempts': config.jobs.retry_max_attempts,
        'retry_base_delay': config.jobs.retry_base_delay,
        'retry_max_delay': config.jobs.retry_max_delay,
        'api_qps_limits': dict(config.jobs.api_qps_limits or {}),
        'heartbeat_interval_seconds': config.jobs.heartbeat_interval_seconds,
        'verbose_request_logs': config.jobs.verbose_request_logs,
        'api_concurrency_limits': dict(config.jobs.api_concurrency_limits or {}),
        'table_concurrency_limits': dict(config.jobs.table_concurrency_limits or {}),
    }


def apply_runtime_config_seed(database, config: Any) -> dict[str, Any]:
    payload = _runtime_seed_payload(config)
    return set_runtime_jobs_config(database, payload)


def main() -> None:
    config = load_config(ROOT / 'config.yaml')
    database = build_database(config)
    database.init_schema()
    try:
        result = apply_runtime_config_seed(database, config)
        print(
            f"runtime config seed applied: {len(result)} keys",
            flush=True,
        )
    finally:
        database.close()


if __name__ == '__main__':
    main()
