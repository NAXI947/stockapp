from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.config import (
    AiConfig,
    AlertConfig,
    AppConfig,
    DatabaseConfig,
    JobsConfig,
    SecurityConfig,
    TushareConfig,
)
from backend.app.db import Database
from backend.app.job_checkpoint import JobCheckpointStore
from jobs import job_history


class DummyHistoryService:
    def __init__(self, client, database, **kwargs):
        self.database = database

    def run_history_sync(self, start_date, end_date, progress_callback, stage_callback):
        progress_callback("20260305")
        progress_callback("20260306")
        stage_callback("history_sync_market_by_date", 1.2, "success", {"trade_date": "20260305"}, "")
        self.database.upsert_many(
            "t_strategy_daily",
            [
                "ts_code",
                "trade_date",
                "ma5",
                "ma20",
                "ma60",
                "upper_space",
                "vol_score",
                "is_limit_up",
                "limit_up_20d",
                "bull_trend",
                "avg_price_support",
                "float_risk_7d",
                "final_score",
                "pct_chg",
                "turnover_rate",
                "volume_ratio",
                "winner_rate",
            ],
            [
                (
                    "000001.SZ",
                    "20260306",
                    10.1,
                    9.9,
                    9.5,
                    None,
                    None,
                    0,
                    0,
                    1,
                    1,
                    0,
                    66,
                    1.23,
                    4.56,
                    1.11,
                    78.9,
                )
            ],
            ["ts_code", "trade_date"],
        )
        return {
            "t_strategy_daily": {
                "rows": 1,
                "missing_fields": [],
                "null_fields": {},
            }
        }


class JobHistoryMinIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db")
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name) / "logs"
        self.database = Database(
            driver="sqlite",
            sqlite_path=self.temp_db.name,
            host="",
            port=0,
            user="",
            password="",
            name="",
        )
        self.database.init_schema()
        self.config = AppConfig(
            environment="test",
            database=DatabaseConfig(
                driver="sqlite",
                sqlite_path=self.temp_db.name,
                host="",
                port=0,
                user="",
                password="",
                name="",
                pool_size=1,
                pool_timeout=1,
            ),
            tushare=TushareConfig(token="", base_url="http://example.com", use_mock=True),
            jobs=JobsConfig(max_workers=10, timeout_seconds=300),
            alert=AlertConfig(enabled=False, webhook_url=""),
            security=SecurityConfig(auth_enabled=False, api_token="", rate_limit_per_minute=120, cors_origins=[]),
            ai=AiConfig(enabled=False),
        )

    def tearDown(self) -> None:
        self.database.close()
        self.temp_db.close()
        self.temp_dir.cleanup()

    def test_job_history_writes_checkpoint_logs_and_result_rows(self) -> None:
        with patch("jobs.job_history.load_config", return_value=self.config), \
             patch("jobs.job_history.build_database", return_value=self.database), \
             patch("jobs.job_history.build_client", return_value=object()), \
             patch("jobs.job_history.build_client_factory", return_value=lambda: object()), \
             patch("jobs.job_history.DataIngestionService", DummyHistoryService), \
             patch("backend.app.local_job_log_store.LOG_DIR", self.log_dir), \
             patch("sys.argv", ["job_history.py", "20260305", "20260306"]):
            job_history.main()

        verify_db = Database(
            driver="sqlite",
            sqlite_path=self.temp_db.name,
            host="",
            port=0,
            user="",
            password="",
            name="",
        )
        checkpoint = dict(
            verify_db.fetch_all(
                "SELECT job_name, target_range, last_completed_trade_date, status FROM t_job_checkpoint WHERE job_name = ?",
                ("job_history",),
            )[0]
        )
        stored_row = dict(
            verify_db.fetch_all(
                "SELECT ts_code, trade_date, final_score FROM t_strategy_daily WHERE ts_code = ? AND trade_date = ?",
                ("000001.SZ", "20260306"),
            )[0]
        )
        self.assertEqual(checkpoint["target_range"], "20260305:20260306")
        self.assertEqual(checkpoint["last_completed_trade_date"], "20260306")
        self.assertEqual(checkpoint["status"], "success")
        self.assertEqual(stored_row["final_score"], 66)

        run_log = [json.loads(line) for line in (self.log_dir / "job_run.log").read_text(encoding="utf-8").splitlines()]
        stage_log = [json.loads(line) for line in (self.log_dir / "job_stage.log").read_text(encoding="utf-8").splitlines()]
        table_log = [json.loads(line) for line in (self.log_dir / "job_table.log").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(run_log[-1]["status"], "success")
        self.assertEqual(stage_log[0]["stage_name"], "history_sync_market_by_date")
        self.assertEqual(table_log[0]["table_name"], "t_strategy_daily")
        verify_db.close()

    def test_incremental_checkpoint_resumes_failure_and_skips_completed_horizon(self) -> None:
        store = JobCheckpointStore(self.database)
        target = "share_float:ann_date"
        store.mark_progress("job_monthly", target, "20260605")
        store.mark_failed("job_monthly", target)

        self.assertEqual(
            store.start_incremental_run(
                "job_monthly",
                target,
                "20260508",
                requested_end="20260607",
            ),
            "20260606",
        )

        store.mark_progress("job_monthly", target, "20260607")
        store.mark_success("job_monthly", target)
        self.assertEqual(
            store.get_incremental_start(
                "job_monthly",
                target,
                "20260508",
                requested_end="20260607",
            ),
            "20260608",
        )


if __name__ == "__main__":
    unittest.main()
