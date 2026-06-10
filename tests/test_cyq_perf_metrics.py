from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.db import Database
from backend.app.job_table_log import JobTableLogger
from backend.app.ingest import DataIngestionService, TableSpec


class CyqPerfMetricsTest(unittest.TestCase):
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
        self.database.upsert_many(
            "t_daily_bar",
            ["ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount", "pct_chg"],
            [
                ("000001.SZ", "20260313", 10, 11, 9, 10.5, 1000, 10000, 1.0),
                ("000002.SZ", "20260313", 20, 21, 19, 20.5, 2000, 20000, 2.0),
                ("000003.SZ", "20260313", 30, 31, 29, 30.5, 3000, 30000, 3.0),
            ],
            ["ts_code", "trade_date"],
        )
        self.service = DataIngestionService(client=object(), database=self.database, max_workers=1)

    def tearDown(self) -> None:
        self.database.close()
        self.temp_db.close()
        self.temp_dir.cleanup()

    def test_cyq_perf_summary_records_coverage_metrics(self) -> None:
        spec = TableSpec(
            "cyq_perf",
            "t_cyq_perf",
            ["ts_code", "trade_date", "winner_rate", "cost_50", "cost_85", "concentration"],
            ["ts_code", "trade_date"],
            source_map={"cost_50": "cost_50pct", "cost_85": "cost_85pct", "concentration": "cost_50pct"},
        )
        records = [
            {"ts_code": "000001.SZ", "trade_date": "20260313", "winner_rate": 81.0, "cost_50": 10.1, "cost_85": 10.8},
            {"ts_code": "000002.SZ", "trade_date": "20260313", "winner_rate": 65.0, "cost_50": 20.2, "cost_85": 21.1},
        ]

        with patch.object(self.service, "_fetch_records", return_value=records):
            summary = self.service._sync_spec_in_batches(spec, [{"trade_date": "20260313"}])

        metrics = summary["metrics"]
        self.assertEqual(metrics["target_total"], 3)
        self.assertEqual(metrics["covered_total"], 2)
        self.assertEqual(metrics["missing_total"], 1)
        self.assertAlmostEqual(metrics["coverage_ratio"], 0.6667, places=4)
        self.assertEqual(metrics["per_trade_date"]["20260313"]["missing_count"], 1)

        logger = JobTableLogger(self.database, 1, "job_daily_featured")
        with patch("backend.app.local_job_log_store.LOG_DIR", self.log_dir):
            logger.log_summary({"t_cyq_perf": summary})

        table_log = [json.loads(line) for line in (self.log_dir / "job_table.log").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(table_log[0]["metrics"]["target_total"], 3)
        self.assertEqual(table_log[0]["metrics"]["missing_total"], 1)


if __name__ == "__main__":
    unittest.main()
