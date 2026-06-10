from __future__ import annotations

import unittest

from backend.app.strategy.vacuum_strategy import VacuumStrategy


class VacuumStrategyTest(unittest.TestCase):
    def test_expected_fields_include_rejection_columns(self) -> None:
        strategy = VacuumStrategy()

        self.assertIn("rejected", strategy.expected_fields)
        self.assertIn("reject_reason", strategy.expected_fields)

    def test_rejected_stock_keeps_ma_fields(self) -> None:
        strategy = VacuumStrategy()
        series = []
        for index in range(60):
            series.append(
                {
                    "trade_date": f"202601{index + 1:02d}",
                    "close": 10.0 + index * 0.1,
                    "low": 9.5 + index * 0.1,
                    "high": 10.5 + index * 0.1,
                    "vol": 1000000,
                    "amount": 10000000,
                    "pct_chg": 1.0,
                    "adj_factor": 1.0,
                    "turnover_rate": 1.0,  # force liquidity_base=False
                    "volume_ratio": 1.0,
                    "winner_rate": 75.0,
                }
            )

        result = strategy.calculate(series, len(series) - 1, float_risk=0, top_list_data=[], stock_name="平安银行")

        self.assertIsNotNone(result)
        self.assertEqual(result.score, 0)
        self.assertEqual(result.extra_fields["rejected"], 1)
        self.assertIsNotNone(result.extra_fields["ma5"])
        self.assertIsNotNone(result.extra_fields["ma20"])
        self.assertIsNotNone(result.extra_fields["ma60"])


if __name__ == "__main__":
    unittest.main()
