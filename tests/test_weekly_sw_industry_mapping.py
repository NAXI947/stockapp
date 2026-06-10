from __future__ import annotations

import tempfile
import unittest

from backend.app.db import Database
from backend.app.ingest import DataIngestionService
from backend.app.tushare_client import QueryResult


class PartialFieldsWeeklyClient:
    def query(self, api_name, fields, params=None):
        params = params or {}
        if api_name == 'index_classify':
            items = [
                ['801780.SI', '银行', 'L1', None],
                ['851911.SI', '银行Ⅱ', 'L2', '801780.SI'],
            ]
            if params.get('level'):
                items = [row for row in items if row[2] == params['level']]
            if fields:
                return QueryResult(
                    fields=['index_code', 'industry_name', 'level', 'parent_code'],
                    items=items,
                )
            return QueryResult(
                fields=['index_code', 'industry_name', 'level'],
                items=[row[:3] for row in items],
            )
        if api_name == 'index_member':
            items = [['851911.SI', '000001.SZ', '20200101', None]]
            if params.get('index_code'):
                items = [row for row in items if row[0] == params['index_code']]
            return QueryResult(
                fields=['index_code', 'con_code', 'in_date', 'out_date'],
                items=items,
            )
        raise AssertionError(f'unexpected api: {api_name}')


class WeeklySwIndustryMappingTest(unittest.TestCase):
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

    def tearDown(self) -> None:
        self.database.close()
        self.temp_db.close()

    def test_weekly_sync_requests_explicit_classify_fields(self) -> None:
        service = DataIngestionService(PartialFieldsWeeklyClient(), self.database)

        summary = service.run_weekly_sync()
        row = dict(
            self.database.fetch_all(
                'SELECT ts_code, sw_level1_name, sw_level2_name FROM t_stock_basic WHERE ts_code = ?',
                ('000001.SZ',),
            )[0]
        )

        self.assertEqual(summary['t_stock_basic']['null_fields'], {})
        self.assertEqual(row['sw_level1_name'], '银行')
        self.assertEqual(row['sw_level2_name'], '银行Ⅱ')

    def test_weekly_sync_detects_multiple_active_memberships(self) -> None:
        class MultiMembershipClient:
            def query(self, api_name, fields, params=None):
                params = params or {}
                if api_name == 'index_classify':
                    items = [
                        ['801780.SI', '银行', 'L1', None],
                        ['801790.SI', '非银金融', 'L1', None],
                        ['851911.SI', '银行Ⅱ', 'L2', '801780.SI'],
                        ['851921.SI', '保险Ⅱ', 'L2', '801790.SI'],
                    ]
                    if params.get('level'):
                        items = [row for row in items if row[2] == params['level']]
                    return QueryResult(
                        fields=['index_code', 'industry_name', 'level', 'parent_code'],
                        items=items,
                    )
                if api_name == 'index_member':
                    items = {
                        '851911.SI': [['851911.SI', '000001.SZ', '20200101', None]],
                        '851921.SI': [['851921.SI', '000001.SZ', '20230101', None]],
                    }
                    return QueryResult(
                        fields=['index_code', 'con_code', 'in_date', 'out_date'],
                        items=items.get(params.get('index_code'), []),
                    )
                raise AssertionError(f'unexpected api: {api_name}')

        service = DataIngestionService(MultiMembershipClient(), self.database)

        summary = service.run_weekly_sync()['t_stock_basic']
        row = dict(
            self.database.fetch_all(
                'SELECT ts_code, sw_level1_name, sw_level2_name FROM t_stock_basic WHERE ts_code = ?',
                ('000001.SZ',),
            )[0]
        )

        self.assertEqual(summary['multi_membership_stocks'], 1)
        self.assertEqual(summary['ambiguous_active_memberships'], 1)
        self.assertEqual(row['sw_level1_name'], '非银金融')
        self.assertEqual(row['sw_level2_name'], '保险Ⅱ')


if __name__ == '__main__':
    unittest.main()
