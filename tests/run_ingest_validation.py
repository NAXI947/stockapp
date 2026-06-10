from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.config import load_config
from backend.app.ingest import ALL_DROP_TABLES, DataIngestionService
from backend.app.runtime import build_client, build_client_factory, build_database


def main() -> int:
    config = load_config()
    database = build_database(config)
    database.drop_tables(ALL_DROP_TABLES)
    database.init_schema()

    client = build_client(config)
    service = DataIngestionService(
        client,
        database,
        max_workers=config.jobs.max_workers,
        client_factory=build_client_factory(config),
        qps_limit=config.jobs.qps_limit,
        qps_burst=config.jobs.qps_burst,
        retry_max_attempts=config.jobs.retry_max_attempts,
        retry_base_delay=config.jobs.retry_base_delay,
        retry_max_delay=config.jobs.retry_max_delay,
        api_concurrency_limits=config.jobs.api_concurrency_limits,
    )
    summary = service.run_full_sync()

    stored_counts = {table: database.fetch_count(table) for table in summary.keys()}
    result = {
        'summary': summary,
        'stored_counts': stored_counts,
        'strategy_preview': [
            dict(row) for row in database.fetch_all(
                'SELECT * FROM t_strategy_daily ORDER BY trade_date DESC, ts_code LIMIT 5'
            )
        ],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    errors = {
        table: {
            'missing_fields': stats['missing_fields'],
            'null_fields': stats['null_fields'],
            'fetched_rows': stats['rows'],
            'stored_rows': stored_counts[table],
        }
        for table, stats in summary.items()
        if stats['missing_fields'] or stored_counts[table] > stats['rows']
    }
    warnings = {
        table: {
            'null_fields': stats['null_fields'],
            'fetched_rows': stats['rows'],
            'stored_rows': stored_counts[table],
            'deduplicated_rows': stats['rows'] - stored_counts[table],
        }
        for table, stats in summary.items()
        if stats['null_fields'] or stored_counts[table] < stats['rows']
    }
    database.close()
    if errors or warnings:
        print(json.dumps({'errors': errors, 'warnings': warnings}, ensure_ascii=False, indent=2, default=str))
    if errors:
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
