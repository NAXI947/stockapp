from __future__ import annotations

import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

os.environ.setdefault("API_AUTH_ENABLED", "false")

from fastapi.testclient import TestClient

from backend.app.config import AiConfig
from backend.core.deps import get_database
from backend.main import create_app


class FakeDatabase:
    driver = "sqlite"

    def fetch_all(self, sql: str, params=()):
        compact_sql = " ".join(str(sql).split())
        if "SELECT MAX(trade_date) AS trade_date FROM t_strategy_daily" in compact_sql and "WHERE ts_code" not in compact_sql:
            return [{"trade_date": "20260310"}]
        if "FROM t_strategy_daily s LEFT JOIN t_stock_basic b" in compact_sql:
            return [
                {
                    "ts_code": "000001.SZ",
                    "name": "平安银行",
                    "industry": "银行",
                    "pct_chg": 1.23,
                    "turnover_rate": 4.56,
                    "volume_ratio": 1.12,
                    "winner_rate": 78.9,
                    "final_score": 65,
                }
            ]
        if "FROM t_daily_bar d LEFT JOIN t_strategy_daily s" in compact_sql:
            return [
                {
                    "trade_date": "20260310",
                    "open": 11.0,
                    "close": 12.0,
                    "low": 10.5,
                    "high": 12.2,
                    "vol": 1000,
                    "ma5": 10.1,
                    "ma20": 9.9,
                    "ma60": 9.5,
                },
                {
                    "trade_date": "20260309",
                    "open": 10.0,
                    "close": 11.0,
                    "low": 9.8,
                    "high": 11.1,
                    "vol": 900,
                    "ma5": 10.0,
                    "ma20": 9.8,
                    "ma60": 9.4,
                },
            ]
        if "SELECT MAX(trade_date) AS trade_date FROM t_strategy_daily WHERE ts_code = ?" in compact_sql:
            if params and params[0] == "404.SZ":
                return [{"trade_date": None}]
            return [{"trade_date": "20260310"}]
        if "FROM t_cyq_perf c LEFT JOIN t_strategy_daily s" in compact_sql:
            return [{"cost_50": 10.5, "cost_85": 11.8, "winner_rate": 76.2, "float_risk_7d": 1}]
        if "FROM t_top_list" in compact_sql:
            return [{"trade_date": "20260310", "name": "机构专用", "net": 1200.0, "buy": 3000.0, "sell": 1800.0, "reason": "日涨幅偏离值达7%"}]
        if "FROM t_share_float" in compact_sql:
            return [{"ann_date": "20260308", "float_date": "20260312", "float_share": 5000.0, "float_ratio": 2.3, "holder_name": "某股东", "share_type": "首发原股东限售股份"}]
        if "FROM t_fin_indicator" in compact_sql:
            return [{"ann_date": "20251231", "end_date": "20251231", "debt_to_assets": 62.1, "roe": 11.3}]
        if "FROM t_daily_bar" in compact_sql:
            return [
                {"trade_date": "20260310", "open": 11.0, "close": 12.0, "low": 10.5, "high": 12.2, "pct_chg": 1.9, "vol": 1000},
                {"trade_date": "20260309", "open": 10.0, "close": 11.0, "low": 9.8, "high": 11.1, "pct_chg": 1.2, "vol": 900},
            ]
        if "SELECT DISTINCT trade_date FROM t_strategy_daily WHERE trade_date <= ?" in compact_sql:
            return [{"trade_date": "20260310"}]
        if "FROM t_strategy_daily WHERE trade_date IN (" in compact_sql:
            return [{"ts_code": "000001.SZ", "trade_date": "20260310", "final_score": 65}]
        if "FROM t_sniper_daily" in compact_sql:
            if "WHERE ts_code = ?" in compact_sql:
                # Detail sniper history query
                if "LIMIT 7" in compact_sql:
                    return [{
                        "trade_date": "20260310",
                        "final_score": 75,
                        "pct_chg": 3.21,
                        "turnover_rate": 4.2,
                        "volume_ratio": 1.3,
                        "rejected": 0,
                        "reject_reason": "",
                        "sniper_score": 75,
                        "sniper_rejected": 0,
                        "sniper_reject_reason": "",
                        "s_holder_score": 10,
                        "s_chip_vacuum_score": 10,
                        "s_ma_state_score": 10,
                        "s_safety_margin_score": 10,
                        "s_macd_weekly_score": 5,
                        "s_low_volume_score": 5,
                        "s_golden_pit_score": 5,
                        "s_ignition_score": 5,
                        "s_top_list_score": 5,
                        "s_news_score": 10,
                        "s_base_total": 50,
                        "s_dynamic_total": 25,
                    }]
                return [{
                    "trade_date": "20260310",
                    "final_score": 75,
                    "pct_chg": 3.21,
                    "turnover_rate": 4.2,
                    "volume_ratio": 1.3,
                    "rejected": 0,
                    "reject_reason": "",
                    "sniper_score": 75,
                    "sniper_rejected": 0,
                    "sniper_reject_reason": "",
                    "s_holder_score": 10,
                    "s_chip_vacuum_score": 10,
                    "s_ma_state_score": 10,
                    "s_safety_margin_score": 10,
                    "s_macd_weekly_score": 5,
                    "s_low_volume_score": 5,
                    "s_golden_pit_score": 5,
                    "s_ignition_score": 5,
                    "s_top_list_score": 5,
                    "s_news_score": 10,
                    "s_base_total": 50,
                    "s_dynamic_total": 25,
                }]
        if "FROM t_strategy_daily" in compact_sql:
            if "WHERE ts_code = ?" in compact_sql:
                if params and params[0] == "404.SZ":
                    return []
                # Check if this is the 7-day trend query or single-day query
                if "LIMIT 7" in compact_sql:
                    return [{
                        "trade_date": "20260310",
                        "final_score": 70,
                        "pct_chg": 3.21,
                        "winner_rate": 80.5,
                        "float_risk_7d": 1,
                        "ma5": 10.1,
                        "ma10": 10.0,
                        "ma20": 9.8,
                        "ma60": 9.5,
                        "turnover_rate": 4.2,
                        "volume_ratio": 1.3,
                        "upper_space": 12.5,
                        "vol_score": 85.0,
                        "trend_baseline": 1,
                        "chip_vacuum": 1,
                        "kline_body": 1,
                        "liquidity_base": 1,
                        "safety_margin": 1,
                        "top_list_3d": 0,
                        "st_risk": 0,
                        "rejected": 0,
                        "reject_reason": "",
                        "limit_up_20d": 0,
                        "is_limit_up": 0,
                        "bull_trend": 0,
                    }]
                return [{
                    "trade_date": "20260310",
                    "final_score": 70,
                    "pct_chg": 3.21,
                    "winner_rate": 80.5,
                    "float_risk_7d": 1,
                    "ma5": 10.1,
                    "ma10": 10.0,
                    "ma20": 9.8,
                    "ma60": 9.5,
                    "turnover_rate": 4.2,
                    "volume_ratio": 1.3,
                    "upper_space": 12.5,
                    "vol_score": 85.0,
                    "trend_baseline": 1,
                    "chip_vacuum": 1,
                    "kline_body": 1,
                    "liquidity_base": 1,
                    "safety_margin": 1,
                    "top_list_3d": 0,
                    "st_risk": 0,
                    "rejected": 0,
                    "reject_reason": "",
                    "limit_up_20d": 0,
                    "is_limit_up": 0,
                    "bull_trend": 0,
                }]
        if "FROM t_concept_detail" in compact_sql:
            return [{"ts_code": "000001.SZ", "concept_name": "银行改革"}]
        if "c.cost_50, c.cost_85, c.winner_rate, s.float_risk_7d" in compact_sql:
            return [{
                "cost_50": 10.5,
                "cost_85": 11.8,
                "winner_rate": 76.2,
                "float_risk_7d": 1,
                "limit_up_20d": 0,
                "is_limit_up": 0,
                "bull_trend": 0,
                "final_score": 70,
                "pct_chg": 3.21,
                "turnover_rate": 4.2,
                "volume_ratio": 1.3,
                "upper_space": 12.5,
                "vol_score": 85.0,
                "trend_baseline": 1,
                "chip_vacuum": 1,
                "kline_body": 1,
                "liquidity_base": 1,
                "safety_margin": 1,
                "top_list_3d": 0,
                "st_risk": 0,
                "rejected": 0,
                "reject_reason": "",
            }]
        if "FROM t_stock_basic WHERE ts_code = ?" in compact_sql:
            return [{"name": "平安银行", "industry": "银行"}]
        raise AssertionError(f"unexpected sql: {compact_sql} params={params}")


@contextmanager
def api_client(database=None):
    app = create_app()
    app.dependency_overrides[get_database] = lambda: database or FakeDatabase()
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


class CoreApiTest(unittest.TestCase):
    def test_health(self) -> None:
        with api_client() as client:
            response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_get_picks_uses_latest_trade_date(self) -> None:
        with api_client() as client:
            response = client.get("/api/v1/picks")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"][0]["ts_code"], "000001.SZ")

    def test_get_kline_returns_chronological_rows(self) -> None:
        with api_client() as client:
            response = client.get("/api/v1/kline/000001.SZ", params={"limit": 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"][0]["trade_date"], "20260309")
        self.assertEqual(response.json()["data"][1]["trade_date"], "20260310")

    def test_get_detail_returns_payload(self) -> None:
        with api_client() as client:
            response = client.get("/api/v1/detail/000001.SZ")
        payload = response.json()["data"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["ts_code"], "000001.SZ")
        self.assertEqual(payload["float_risk_7d"], 1)
        self.assertEqual(len(payload["top_list"]), 1)
        self.assertEqual(len(payload["upcoming_float"]), 1)
        self.assertEqual(payload["fin_indicator"]["roe"], 11.3)

    def test_get_detail_returns_404_when_stock_missing(self) -> None:
        with api_client() as client:
            response = client.get("/api/v1/detail/404.SZ")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "stock not found")

    def test_stock_advice_returns_rule_based_markdown(self) -> None:
        mocked_advice = {
            "symbol": "000001.SZ",
            "current_price": None,
            "advice_markdown": "### 平安银行分析\n- 综合评分: 70\n- 当前输出为本地规则分析。",
            "risk_warning": "当前未启用 LLM 分析。",
            "analysis_mode": "rule_fallback",
            "analysis_meta": {"prompt_variant": "risk_guarded", "model": None},
        }
        with patch("backend.app.api.load_config") as config_mock:
            config_mock.return_value.ai = AiConfig(enabled=False)
            with patch("backend.app.api.generate_stock_advice", return_value=mocked_advice):
                with api_client() as client:
                    response = client.post("/api/v1/analysis/stock_advice", json={"symbol": "000001.SZ", "market": "CN"})
        payload = response.json()["data"]
        self.assertEqual(response.status_code, 200)
        self.assertIn("综合评分: 70", payload["advice_markdown"])
        self.assertIn("LLM", payload["risk_warning"])
        self.assertEqual(payload["analysis_mode"], "rule_fallback")

    def test_stock_advice_returns_404_when_stock_missing(self) -> None:
        with api_client() as client:
            response = client.post("/api/v1/analysis/stock_advice", json={"symbol": "404.SZ", "market": "CN"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "stock not found")

    def test_stock_advice_returns_llm_output_when_enabled(self) -> None:
        mocked_advice = {
            "symbol": "000001.SZ",
            "current_price": None,
            "advice_markdown": "### 结论\n适合观察回踩后的承接。",
            "risk_warning": "LLM 输出仅供辅助判断，不构成投资建议。",
            "analysis_mode": "llm",
            "analysis_meta": {"prompt_variant": "momentum", "model": "gpt-4.1-mini"},
        }
        with patch("backend.app.api.load_config") as config_mock:
            config_mock.return_value.ai = AiConfig(enabled=True, base_url="https://example.com/v1", api_key="k", model="m")
            with patch("backend.app.api.generate_stock_advice", return_value=mocked_advice):
                with api_client() as client:
                    response = client.post("/api/v1/analysis/stock_advice", json={"symbol": "000001.SZ", "market": "CN"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("结论", response.json()["data"]["advice_markdown"])
        self.assertEqual(response.json()["data"]["analysis_meta"]["model"], "gpt-4.1-mini")

    def test_job_stages_returns_items_and_summary(self) -> None:
        mocked_payload = {
            "items": [
                {
                    "id": 1,
                    "run_id": 101,
                    "job_name": "job_history",
                    "stage_name": "sync_daily",
                    "status": "failed",
                    "duration_ms": 1234,
                    "created_at": "2026-03-10T12:00:00+00:00",
                    "extra": {"trade_date": "20260310"},
                    "message": "network timeout",
                }
            ],
            "summary": [
                {
                    "stage_name": "sync_daily",
                    "total_count": 2,
                    "failed_count": 1,
                    "total_duration_ms": 3456,
                    "avg_duration_ms": 1728.0,
                    "max_duration_ms": 2234,
                }
            ],
        }
        with patch("backend.app.api.build_job_stage_metrics", return_value=mocked_payload) as metrics_mock:
            with api_client() as client:
                response = client.get(
                    "/api/v1/job/stages",
                    params={"job_name": "job_history", "run_id": 101, "limit": 5000, "days": 999, "status": "FAILED"},
                )
        payload = response.json()["data"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["items"][0]["extra"]["trade_date"], "20260310")
        self.assertEqual(payload["summary"][0]["failed_count"], 1)
        metrics_mock.assert_called_once_with(days=90, limit=1000, job_name="job_history", run_id=101, status="failed")

    def test_job_stages_rejects_invalid_status(self) -> None:
        with api_client() as client:
            response = client.get("/api/v1/job/stages", params={"status": "broken"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "status must be one of: running, success, failed, unknown")


if __name__ == "__main__":
    unittest.main()
