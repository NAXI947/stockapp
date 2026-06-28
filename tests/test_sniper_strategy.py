from __future__ import annotations

import unittest
import tempfile

from backend.app.db import Database
from backend.app.strategy.sniper_strategy import SniperStrategy


class SniperStrategyTest(unittest.TestCase):
    def test_expected_fields_include_rejection_columns(self) -> None:
        strategy = SniperStrategy()

        self.assertIn("sniper_rejected", strategy.expected_fields)
        self.assertIn("sniper_reject_reason", strategy.expected_fields)
        self.assertIn("chaos_index_val", strategy.expected_fields)
        self.assertIn("score_chaos", strategy.expected_fields)

    @staticmethod
    def _chaos_series(size: int, *, flat: bool = False) -> list[dict]:
        rows = []
        for index in range(size):
            close = 10.0 if flat else 10.0 + index * 0.1
            rows.append(
                {
                    "trade_date": f"2026{index // 28 + 1:02d}{index % 28 + 1:02d}",
                    "close": close,
                    "open": close,
                    "high": close + (1.0 if flat else 0.005),
                    "low": close - (1.0 if flat else 0.005),
                    "vol": 1000000,
                    "amount": 10000000,
                    "pct_chg": 0.0 if flat else 1.0,
                    "adj_factor": 1.0,
                    "turnover_rate": 5.0 if flat else 0.1,
                    "volume_ratio": 1.0,
                }
            )
        return rows

    def test_chaos_score_requires_twenty_one_observations(self) -> None:
        strategy = SniperStrategy()

        self.assertEqual(strategy._compute_chaos_score(self._chaos_series(20), 19), (None, 0))
        chaos, score = strategy._compute_chaos_score(self._chaos_series(21), 20)

        self.assertIsNotNone(chaos)
        self.assertLess(chaos, 1.0)
        self.assertEqual(score, 15)

    def test_high_chaos_triggers_holder_surge(self) -> None:
        strategy = SniperStrategy()
        series = self._chaos_series(60, flat=True)

        result = strategy.calculate(series, len(series) - 1, float_risk=0, stock_name="测试股票")

        self.assertIsNotNone(result)
        self.assertGreaterEqual(result.extra_fields["chaos_index_val"], 8.0)
        self.assertEqual(result.extra_fields["score_chaos"], 0)
        self.assertEqual(result.extra_fields["s_holder_score"], 0)
        self.assertEqual(result.extra_fields["sniper_rejected"], 1)
        self.assertEqual(result.extra_fields["sniper_reject_reason"], "HOLDER_SURGE")

    def test_sqlite_schema_contains_chaos_columns(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db") as temp_db:
            database = Database(
                driver="sqlite", host="", port=0, user="", password="", name="",
                sqlite_path=temp_db.name,
            )
            try:
                database.init_schema()
                columns = {row["name"] for row in database.fetch_all("PRAGMA table_info(t_sniper_daily)")}
            finally:
                database.close()

        self.assertIn("chaos_index_val", columns)
        self.assertIn("score_chaos", columns)

    def test_calculate_sniper_score(self) -> None:
        strategy = SniperStrategy()
        series = []
        for index in range(60):
            series.append(
                {
                    "trade_date": f"202601{index + 1:02d}",
                    "close": 10.0 + index * 0.1,
                    "low": 9.5 + index * 0.1,
                    "high": 10.5 + index * 0.1,
                    "open": 9.8 + index * 0.1,
                    "vol": 1000000,
                    "amount": 10000000,
                    "pct_chg": 1.0,
                    "adj_factor": 1.0,
                    "turnover_rate": 2.0,
                    "volume_ratio": 2.5,
                }
            )

        # Mocking data structures
        weekly_series = [
            {"trade_date": "20260105", "close": 10.0},
            {"trade_date": "20260112", "close": 11.0},
            {"trade_date": "20260119", "close": 12.0},
            {"trade_date": "20260126", "close": 13.0},
        ]
        block_trade_data = [
            {"trade_date": "20260105", "premium": 0.02}
        ]

        result = strategy.calculate(
            series, len(series) - 1, float_risk=0, top_list_data=[], stock_name="平安银行",
            weekly_series=weekly_series, block_trade_data=block_trade_data
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.extra_fields["sniper_rejected"], 0)
        self.assertGreater(result.score, 0)
        self.assertEqual(result.extra_fields["score_chaos"], result.extra_fields["s_holder_score"])


if __name__ == "__main__":
    unittest.main()
