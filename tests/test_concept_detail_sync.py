from __future__ import annotations

import tempfile
import unittest
from datetime import date

from backend.app.db import Database
from backend.app.ingest import (
    DataIngestionService,
    FULL_MARKET_SUPPLEMENTAL_SPECS,
    STATIC_SUPPLEMENTAL_SPECS,
)
from backend.app.tushare_client import QueryResult


class EastMoneyConceptClient:
    def query(self, api_name, fields, params=None):
        params = params or {}
        if api_name == 'dc_index':
            self.assert_fields(fields, ['ts_code', 'trade_date', 'name', 'idx_type'])
            self.assertEqual(params, {'idx_type': '概念板块', 'trade_date': '20260304'})
            return QueryResult(
                fields=['ts_code', 'trade_date', 'name', 'idx_type'],
                items=[
                    ['BK1001.DC', '20260304', 'AI金融', '概念板块'],
                    ['BK1002.DC', '20260304', '低空经济', '概念板块'],
                ],
            )
        if api_name == 'dc_member':
            self.assert_fields(fields, ['trade_date', 'ts_code', 'con_code', 'name'])
            mapping = {
                'BK1001.DC': [['20260304', 'BK1001.DC', '000001.SZ', '平安银行']],
                'BK1002.DC': [['20260304', 'BK1002.DC', '000001.SZ', '平安银行']],
            }
            return QueryResult(
                fields=['trade_date', 'ts_code', 'con_code', 'name'],
                items=mapping.get(params.get('ts_code'), []),
            )
        raise AssertionError(f'unexpected api: {api_name}')

    @staticmethod
    def assert_fields(actual, expected):
        if actual != expected:
            raise AssertionError(f'fields mismatch: {actual} != {expected}')

    @staticmethod
    def assertEqual(actual, expected):
        if actual != expected:
            raise AssertionError(f'value mismatch: {actual} != {expected}')


class ConceptDetailSyncTest(unittest.TestCase):
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
        self.database.upsert_many(
            't_stock_basic',
            ['ts_code', 'symbol', 'name', 'industry', 'sw_level1_name', 'sw_level2_name', 'list_date'],
            [('000001.SZ', '000001', '平安银行', '银行', None, None, '19910403')],
            ['ts_code'],
        )
        self.database.upsert_many(
            't_daily_bar',
            ['ts_code', 'trade_date', 'open', 'high', 'low', 'close', 'vol', 'amount', 'pct_chg'],
            [('000001.SZ', '20260304', 12.31, 12.88, 12.20, 12.78, 1854321.0, 236512.4, 4.52)],
            ['ts_code', 'trade_date'],
        )

    def tearDown(self) -> None:
        self.database.close()
        self.temp_db.close()

    def test_concept_detail_sync_uses_eastmoney_dc_index_and_member(self) -> None:
        service = DataIngestionService(
            EastMoneyConceptClient(),
            self.database,
            max_workers=1,
            retry_max_attempts=1,
        )
        concept_spec = next(item for item in STATIC_SUPPLEMENTAL_SPECS if item.api_name == 'dc_member')
        summary = service._sync_spec_in_batches(concept_spec, service._build_query_param_list('dc_member', None))
        rows = [
            dict(row) for row in self.database.fetch_all(
                'SELECT id, concept_name, ts_code, name FROM t_concept_detail ORDER BY id, ts_code'
            )
        ]

        self.assertEqual(summary['rows'], 2)
        self.assertEqual(rows, [
            {'id': 'BK1001.DC', 'concept_name': 'AI金融', 'ts_code': '000001.SZ', 'name': '平安银行'},
            {'id': 'BK1002.DC', 'concept_name': '低空经济', 'ts_code': '000001.SZ', 'name': '平安银行'},
        ])

    def test_share_float_incremental_queries_dates_instead_of_all_stocks(self) -> None:
        requested_params = []

        class IncrementalClient:
            def query(self, api_name, fields, params=None):
                requested_params.append(dict(params or {}))
                return QueryResult(fields=fields, items=[])

        class Checkpoints:
            def start_incremental_run(self, job_name, target_range, requested_start, requested_end=None):
                return {
                    'share_float:ann_date': '20260606',
                    'share_float:float_date': '20260610',
                }[target_range]

            def mark_progress(self, *args):
                return None

            def mark_success(self, *args):
                return None

            def mark_failed(self, *args):
                return None

        service = DataIngestionService(IncrementalClient(), self.database, max_workers=1)
        spec = next(item for item in FULL_MARKET_SUPPLEMENTAL_SPECS if item.api_name == 'share_float')
        service._sync_share_float_incremental(
            spec,
            checkpoint_store=Checkpoints(),
            run_date=date(2026, 6, 7),
            future_days=4,
        )

        self.assertEqual(requested_params, [
            {'ann_date': '20260606'},
            {'ann_date': '20260607'},
            {'float_date': '20260610'},
            {'float_date': '20260611'},
        ])
        self.assertTrue(all('ts_code' not in params for params in requested_params))

    def test_share_float_refetches_by_stock_only_when_date_hits_api_limit(self) -> None:
        requested_params = []
        spec = next(item for item in FULL_MARKET_SUPPLEMENTAL_SPECS if item.api_name == 'share_float')

        class CappedClient:
            def query(self, api_name, fields, params=None):
                params = dict(params or {})
                requested_params.append(params)
                if 'ts_code' not in params:
                    row = ['000001.SZ', '20260607', '20260620', 100.0, 1.0, 'holder', 'type']
                    return QueryResult(fields=fields, items=[row] * 6000)
                return QueryResult(
                    fields=fields,
                    items=[['000001.SZ', '20260607', '20260620', 100.0, 1.0, 'holder', 'type']],
                )

        service = DataIngestionService(CappedClient(), self.database, max_workers=1)
        records = service._fetch_share_float_date_records(spec, 'ann_date', '20260607')

        self.assertEqual(len(records), 1)
        self.assertEqual(requested_params[0]['ann_date'], '20260607')
        self.assertNotIn('ts_code', requested_params[0])
        self.assertEqual(requested_params[1]['ts_code'], '000001.SZ')


if __name__ == '__main__':
    unittest.main()
