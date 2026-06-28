from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db import Database
from backend.app.ingest import DataIngestionService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="回填极简狙击手主力控盘度")
    parser.add_argument(
        "--database",
        default=str(ROOT / "dist" / "data" / "stocknew.db"),
        help="SQLite 数据库路径",
    )
    parser.add_argument("--days", type=int, default=7, help="回填最近交易日数量")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    database_path = Path(args.database).resolve()
    if not database_path.exists():
        raise SystemExit(f"数据库不存在: {database_path}")
    if args.days <= 0:
        raise SystemExit("--days 必须大于 0")

    database = Database(
        driver="sqlite",
        host="",
        port=0,
        user="",
        password="",
        name="",
        sqlite_path=str(database_path),
        pool_size=2,
        pool_timeout=60,
    )
    try:
        database.init_schema()
        rows = database.fetch_all(
            "SELECT DISTINCT trade_date FROM t_daily_bar ORDER BY trade_date DESC LIMIT %s",
            (args.days,),
        )
        trade_dates = list(reversed([str(row["trade_date"]) for row in rows]))
        if not trade_dates:
            raise SystemExit("t_daily_bar 没有可回填交易日")

        service = DataIngestionService(client=object(), database=database, max_workers=1)
        total = 0
        for index, trade_date in enumerate(trade_dates, start=1):
            print(f"[chaos-backfill] {index}/{len(trade_dates)} trade_date={trade_date}", flush=True)
            result = service._build_sniper_daily(trade_date=trade_date)
            rows_written = int(result.get("rows", 0) or 0)
            total += rows_written
            print(f"[chaos-backfill] trade_date={trade_date} rows={rows_written}", flush=True)

        print(
            f"[chaos-backfill] completed database={database_path} "
            f"dates={len(trade_dates)} rows={total}",
            flush=True,
        )
    finally:
        database.close()


if __name__ == "__main__":
    main()
