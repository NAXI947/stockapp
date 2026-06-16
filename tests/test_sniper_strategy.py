from __future__ import annotations

import unittest

from backend.app.strategy.sniper_strategy import SniperStrategy


class SniperStrategyTest(unittest.TestCase):
    def test_expected_fields_include_rejection_columns(self) -> None:
        strategy = SniperStrategy()

        self.assertIn("sniper_rejected", strategy.expected_fields)
        self.assertIn("sniper_reject_reason", strategy.expected_fields)

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
        holder_data = [
            {"end_date": "20251231", "holder_num": 10000},
            {"end_date": "20260131", "holder_num": 9200}, # Decreasing
        ]
        block_trade_data = [
            {"trade_date": "20260105", "premium": 0.02}
        ]

        result = strategy.calculate(
            series, len(series) - 1, float_risk=0, top_list_data=[], stock_name="平安银行",
            weekly_series=weekly_series, holder_data=holder_data, block_trade_data=block_trade_data
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.extra_fields["sniper_rejected"], 0)
        self.assertGreater(result.score, 0)


if __name__ == "__main__":
    unittest.main()
