from __future__ import annotations

import tempfile
import unittest
from backend.app.db import Database
from backend.app.ingest import DataIngestionService
from backend.app.strategy import get_all_strategies

class MockTushareClient:
    def query(self, api_name, fields, params=None):
        from backend.app.tushare_client import QueryResult
        return QueryResult(fields=[], items=[])

class IngestTrendReasonTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_db = tempfile.NamedTemporaryFile(suffix='.db')
        self.database = Database(
            driver='sqlite',
            sqlite_path=self.temp_db.name,
            host='',
            port=0,
            user='',
            password='',
            name='',
        )
        self.database.init_schema()

    def tearDown(self) -> None:
        self.database.close()
        self.temp_db.close()

    def test_trend_reason_yesterday_rollback_calculation(self) -> None:
        # 1. Insert two days of daily bars and indicators
        self.database.upsert_many(
            't_stock_basic',
            ['ts_code', 'symbol', 'name', 'industry', 'list_date'],
            [('000001.SZ', '000001', '平安银行', '银行', '19910403')],
            ['ts_code']
        )
        
        # Day 1 (20260309)
        self.database.upsert_many(
            't_daily_bar',
            ['ts_code', 'trade_date', 'open', 'high', 'low', 'close', 'vol', 'amount', 'pct_chg'],
            [('000001.SZ', '20260309', 10.0, 10.5, 9.8, 10.0, 1000, 10000, 0.0)],
            ['ts_code', 'trade_date']
        )
        self.database.upsert_many(
            't_daily_basic',
            ['ts_code', 'trade_date', 'turnover_rate', 'volume_ratio', 'circ_mv'],
            [('000001.SZ', '20260309', 1.0, 1.0, 1000000)],
            ['ts_code', 'trade_date']
        )
        self.database.upsert_many(
            't_adj_factor',
            ['ts_code', 'trade_date', 'adj_factor'],
            [('000001.SZ', '20260309', 1.0)],
            ['ts_code', 'trade_date']
        )
        
        # Day 2 (20260310) - Higher price, better safety margin or baseline
        self.database.upsert_many(
            't_daily_bar',
            ['ts_code', 'trade_date', 'open', 'high', 'low', 'close', 'vol', 'amount', 'pct_chg'],
            [('000001.SZ', '20260310', 10.0, 11.5, 9.8, 11.2, 2500, 28000, 12.0)],
            ['ts_code', 'trade_date']
        )
        self.database.upsert_many(
            't_daily_basic',
            ['ts_code', 'trade_date', 'turnover_rate', 'volume_ratio', 'circ_mv'],
            [('000001.SZ', '20260310', 2.5, 2.5, 1120000)],
            ['ts_code', 'trade_date']
        )
        self.database.upsert_many(
            't_adj_factor',
            ['ts_code', 'trade_date', 'adj_factor'],
            [('000001.SZ', '20260310', 1.0)],
            ['ts_code', 'trade_date']
        )
        
        # Rebuild strategy results
        service = DataIngestionService(MockTushareClient(), self.database)
        service._build_strategy_daily()
        
        # Fetch output strategy rows
        rows = self.database.fetch_all(
            "SELECT trade_date, final_score, trend_reason FROM t_strategy_daily ORDER BY trade_date ASC"
        )
        self.assertEqual(len(rows), 2)
        
        # Day 1 should have fallback trend_reason
        self.assertEqual(rows[0]['trend_reason'], "首日建立指标底座")
        
        # Day 2 should calculate a real trend_reason
        self.assertIsNotNone(rows[1]['trend_reason'])
        self.assertNotEqual(rows[1]['trend_reason'], "")
        self.assertNotEqual(rows[1]['trend_reason'], "首日建立指标底座")
