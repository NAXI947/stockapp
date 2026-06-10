from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import HTTPException

from backend.app.analysis_service import (
    _candidate_models,
    _select_prompt_variant,
    build_stock_analysis_context,
    generate_stock_advice,
)
from backend.app.config import AiConfig


class FakeAnalysisDatabase:
    driver = "sqlite"

    def fetch_all(self, sql: str, params=()):
        compact_sql = " ".join(str(sql).split())
        if "FROM t_strategy_daily" in compact_sql:
            if params and params[0] == "404.SZ":
                return []
            return [
                {
                    "trade_date": "20260310",
                    "final_score": 72,
                    "pct_chg": 2.34,
                    "winner_rate": 79.8,
                    "float_risk_7d": 1,
                    "ma5": 10.1,
                    "ma20": 9.8,
                    "ma60": 9.2,
                    "turnover_rate": 4.6,
                    "volume_ratio": 1.2,
                }
            ]
        if "FROM t_stock_basic" in compact_sql:
            return [{"ts_code": "000001.SZ", "symbol": "000001", "name": "平安银行", "industry": "银行", "sw_level1_name": "金融", "sw_level2_name": "银行", "list_date": "19910403"}]
        if "FROM t_cyq_perf" in compact_sql:
            return [{"winner_rate": 79.8, "cost_50": 10.4, "cost_85": 11.3, "concentration": 18.2}]
        if "FROM t_fin_indicator" in compact_sql:
            return [{"ann_date": "20251231", "end_date": "20251231", "debt_to_assets": 61.2, "roe": 10.8}]
        if "FROM t_top_list" in compact_sql:
            return [{"trade_date": "20260309", "name": "机构专用", "net": 1000, "buy": 3000, "sell": 2000, "reason": "日涨幅偏离值达7%"}]
        if "FROM t_share_float" in compact_sql:
            return [{"ann_date": "20260308", "float_date": "20260318", "float_share": 5000, "float_ratio": 2.1, "holder_name": "某股东", "share_type": "首发原股东限售股份"}]
        if "FROM t_daily_bar" in compact_sql:
            return [
                {"trade_date": "20260310", "open": 10.2, "close": 10.8, "low": 10.0, "high": 10.9, "pct_chg": 2.3, "vol": 1000},
                {"trade_date": "20260309", "open": 10.0, "close": 10.4, "low": 9.8, "high": 10.5, "pct_chg": 1.8, "vol": 900},
                {"trade_date": "20260308", "open": 9.8, "close": 10.0, "low": 9.7, "high": 10.2, "pct_chg": 1.2, "vol": 850},
            ]
        raise AssertionError(f"unexpected sql: {compact_sql}")


class AnalysisServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.database = FakeAnalysisDatabase()

    def test_generate_stock_advice_raises_404_when_missing(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            generate_stock_advice(self.database, AiConfig(enabled=False), "404.SZ", "CN")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_build_stock_analysis_context_contains_retrieval_snapshot(self) -> None:
        context = build_stock_analysis_context(self.database, "000001.SZ")
        self.assertIn("recent_bars", context)
        self.assertEqual(len(context["recent_bars"]), 3)
        self.assertIn("trend_snapshot", context)
        self.assertEqual(context["trend_snapshot"]["latest_trade_date"], "20260310")

    def test_generate_stock_advice_uses_rule_fallback_when_ai_disabled(self) -> None:
        payload = generate_stock_advice(self.database, AiConfig(enabled=False), "000001.SZ", "CN")
        self.assertIn("本地规则分析", payload["advice_markdown"])
        self.assertIn("未启用 LLM", payload["risk_warning"])
        self.assertEqual(payload["analysis_mode"], "rule_fallback")

    def test_generate_stock_advice_returns_llm_content_when_ai_enabled(self) -> None:
        ai_config = AiConfig(
            enabled=True,
            base_url="https://example.com/v1",
            api_key="token",
            model="gpt-primary",
            models=["gpt-fallback"],
        )
        with patch("backend.app.analysis_service._call_openai_compatible", return_value="### 结论\n关注回踩后的承接。") as llm_mock:
            payload = generate_stock_advice(self.database, ai_config, "000001.SZ", "CN")
        self.assertIn("结论", payload["advice_markdown"])
        self.assertIn("辅助判断", payload["risk_warning"])
        self.assertEqual(payload["analysis_mode"], "llm")
        self.assertEqual(payload["analysis_meta"]["model"], "gpt-primary")
        self.assertEqual(payload["analysis_meta"]["prompt_variant"], "risk_guarded")
        llm_mock.assert_called_once()

    def test_generate_stock_advice_falls_back_when_llm_fails(self) -> None:
        ai_config = AiConfig(
            enabled=True,
            base_url="https://example.com/v1",
            api_key="token",
            model="gpt-primary",
            models=["gpt-fallback"],
        )
        with patch("backend.app.analysis_service._call_openai_compatible", side_effect=RuntimeError("network error")):
            payload = generate_stock_advice(self.database, ai_config, "000001.SZ", "CN")
        self.assertIn("本地规则分析", payload["advice_markdown"])
        self.assertIn("network error", payload["risk_warning"])
        self.assertEqual(payload["analysis_mode"], "rule_fallback")

    def test_generate_stock_advice_uses_fallback_model_after_primary_failure(self) -> None:
        ai_config = AiConfig(
            enabled=True,
            base_url="https://example.com/v1",
            api_key="token",
            model="gpt-primary",
            models=["gpt-fallback"],
        )
        with patch(
            "backend.app.analysis_service._call_openai_compatible",
            side_effect=[RuntimeError("primary down"), "### 结论\n使用后备模型成功。"],
        ) as llm_mock:
            payload = generate_stock_advice(self.database, ai_config, "000001.SZ", "CN")
        self.assertEqual(payload["analysis_meta"]["model"], "gpt-fallback")
        self.assertEqual(llm_mock.call_count, 2)

    def test_candidate_models_puts_primary_model_first(self) -> None:
        ai_config = AiConfig(model="gpt-primary", models=["gpt-fallback", "gpt-primary"])
        self.assertEqual(_candidate_models(ai_config), ["gpt-primary", "gpt-fallback"])

    def test_select_prompt_variant_supports_auto_and_explicit(self) -> None:
        context = build_stock_analysis_context(self.database, "000001.SZ")
        self.assertEqual(_select_prompt_variant(context, "auto"), "risk_guarded")
        self.assertEqual(_select_prompt_variant(context, "momentum"), "momentum")


if __name__ == "__main__":
    unittest.main()
