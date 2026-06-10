from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

try:
    import tushare as ts
    _TUSHARE_IMPORT_ERROR = None
except ImportError as exc:  # pragma: no cover - runtime dependency
    ts = None
    _TUSHARE_IMPORT_ERROR = exc


@dataclass
class QueryResult:
    fields: List[str]
    items: List[List[Any]]

    def to_dicts(self) -> List[Dict[str, Any]]:
        return [dict(zip(self.fields, item)) for item in self.items]


class TushareClient:
    def __init__(self, token: str, base_url: str, timeout_seconds: int = 30):
        if ts is None:
            detail = f': {_TUSHARE_IMPORT_ERROR}' if _TUSHARE_IMPORT_ERROR else ''
            raise RuntimeError(f'tushare is required for real API mode. Install dependencies first{detail}.')
        self.token = token
        self.base_url = base_url
        self.timeout_seconds = max(int(timeout_seconds), 5)
        self.pro = ts.pro_api(token)
        self.pro._DataApi__token = token
        self.pro._DataApi__http_url = base_url
        try:
            self.pro._DataApi__timeout = self.timeout_seconds
        except Exception:
            pass

    def query(self, api_name: str, fields: List[str], params: Dict[str, Any] | None = None) -> QueryResult:
        params = dict(params or {})
        method = getattr(self.pro, api_name)
        if fields:
            params['fields'] = ','.join(fields)
        df = method(**params)
        if df is None or df.empty:
            return QueryResult(fields=fields, items=[])
        selected_fields = list(df.columns)
        return QueryResult(fields=selected_fields, items=df.where(df.notna(), None).values.tolist())


class MockTushareClient:
    def __init__(self):
        self._data = {
            'stock_basic': QueryResult(
                fields=['ts_code', 'symbol', 'name', 'industry', 'list_date'],
                items=[
                    ['000001.SZ', '000001', '平安银行', '银行', '19910403'],
                    ['000002.SZ', '000002', '万科A', '全国地产', '19910129'],
                ],
            ),
            'index_classify': QueryResult(
                fields=['index_code', 'industry_name', 'level', 'industry_code', 'parent_code'],
                items=[
                    ['801780.SI', '银行', 'L1', '110000', None],
                    ['801781.SI', '房地产', 'L1', '120000', None],
                    ['851911.SI', '银行Ⅱ', 'L2', '110100', '801780.SI'],
                    ['851921.SI', '房地产开发Ⅱ', 'L2', '120100', '801781.SI'],
                ],
            ),
            'index_member_all': QueryResult(
                fields=['l1_code', 'l1_name', 'l2_code', 'l2_name', 'l3_code', 'l3_name', 'ts_code', 'name', 'in_date', 'out_date', 'is_new'],
                items=[
                    ['801780.SI', '银行', '851911.SI', '银行Ⅱ', None, None, '000001.SZ', '平安银行', '20200101', None, 'Y'],
                    ['801781.SI', '房地产', '851921.SI', '房地产开发Ⅱ', None, None, '000002.SZ', '万科A', '20200101', None, 'Y'],
                ],
            ),
            'trade_cal': QueryResult(
                fields=['cal_date', 'is_open'],
                items=[['20260303', 1], ['20260304', 1], ['20260305', 1]],
            ),
            'daily': QueryResult(
                fields=['ts_code', 'trade_date', 'open', 'high', 'low', 'close', 'vol', 'amount', 'pct_chg'],
                items=[
                    ['000001.SZ', '20260304', 12.31, 12.88, 12.20, 12.78, 1854321.0, 236512.4, 4.52],
                    ['000002.SZ', '20260304', 9.80, 10.18, 9.71, 10.02, 1432100.0, 142314.2, 3.08],
                ],
            ),
            'adj_factor': QueryResult(
                fields=['ts_code', 'trade_date', 'adj_factor'],
                items=[['000001.SZ', '20260304', 1.0234], ['000002.SZ', '20260304', 0.9988]],
            ),
            'daily_basic': QueryResult(
                fields=['ts_code', 'trade_date', 'turnover_rate', 'volume_ratio', 'circ_mv'],
                items=[['000001.SZ', '20260304', 6.8, 1.5, 2150.2], ['000002.SZ', '20260304', 5.1, 1.2, 1880.6]],
            ),
            'dc_index': QueryResult(
                fields=['ts_code', 'trade_date', 'name', 'idx_type'],
                items=[
                    ['BK1001.DC', '20260304', 'AI金融', '概念板块'],
                    ['BK1002.DC', '20260304', '低空经济', '概念板块'],
                    ['BK1003.DC', '20260304', '地产链', '概念板块'],
                ],
            ),
            'dc_member': QueryResult(
                fields=['trade_date', 'ts_code', 'con_code', 'name'],
                items=[
                    ['20260304', 'BK1001.DC', '000001.SZ', '平安银行'],
                    ['20260304', 'BK1002.DC', '000001.SZ', '平安银行'],
                    ['20260304', 'BK1003.DC', '000002.SZ', '万科A'],
                ],
            ),
            'cyq_perf': QueryResult(
                fields=['ts_code', 'trade_date', 'winner_rate', 'cost_50pct', 'cost_85pct'],
                items=[['000001.SZ', '20260304', 85.2, 12.10, 12.62], ['000002.SZ', '20260304', 76.5, 9.88, 10.05]],
            ),
            'top_list': QueryResult(
                fields=['ts_code', 'trade_date', 'name', 'net_amount', 'l_buy', 'l_sell', 'reason'],
                items=[
                    ['000001.SZ', '20260304', '平安银行', 15230.8, 32010.2, 16779.4, '日涨幅偏离值达7%'],
                    ['000001.SZ', '20260304', '平安银行', 12100.2, 25000.0, 12900.0, '连续三个交易日内涨幅偏离值累计20%'],
                    ['000002.SZ', '20260304', '万科A', 9800.5, 21100.0, 11300.5, '连续三个交易日内涨幅偏离值累计20%'],
                ],
            ),
            'share_float': QueryResult(
                fields=['ts_code', 'ann_date', 'float_date', 'float_share', 'float_ratio', 'holder_name', 'share_type'],
                items=[
                    ['000001.SZ', '20260301', '20260310', 1000000.0, 2.1, '机构A', '定增股份'],
                    ['000001.SZ', '20260301', '20260310', 500000.0, 1.0, '机构B', '定增股份'],
                    ['000002.SZ', '20260302', '20260320', 800000.0, 6.5, '机构C', '首发原股东限售股份'],
                ],
            ),
            'fina_indicator': QueryResult(
                fields=['ts_code', 'ann_date', 'end_date', 'debt_to_assets', 'roe'],
                items=[
                    ['000001.SZ', '20260131', '20251231', 91.2, 8.6],
                    ['000001.SZ', '20260215', '20251231', 90.8, 8.9],
                    ['000002.SZ', '20260131', '20251231', 78.5, 5.2],
                ],
            ),
        }

    def query(self, api_name: str, fields: List[str], params: Dict[str, Any] | None = None) -> QueryResult:
        params = params or {}
        result = self._data[api_name]
        current = QueryResult(fields=list(result.fields), items=[list(row) for row in result.items])

        if api_name == 'trade_cal':
            current = self._filter_trade_cal(current, params)
        if api_name in {'daily', 'adj_factor', 'daily_basic', 'cyq_perf', 'top_list'} and params.get('trade_date'):
            current = self._override_trade_date(current, params['trade_date'])
        if api_name == 'dc_index':
            current = self._filter_dc_index(current, params)
        if api_name == 'dc_member':
            if params.get('ts_code'):
                current = self._filter_by_ts_code(current, params['ts_code'])
            if params.get('trade_date'):
                current = self._filter_by_trade_date(current, params['trade_date'])
        if api_name in {'share_float', 'fina_indicator'}:
            if params.get('ts_code'):
                current = self._filter_by_ts_code(current, params['ts_code'])
            if params.get('ann_date'):
                current = self._filter_by_ann_date(current, params['ann_date'])
        if api_name == 'index_classify':
            current = self._filter_index_classify(current, params)
        if api_name == 'index_member_all' and params.get('l2_code'):
            current = self._filter_by_l2_code(current, params['l2_code'])

        if not fields:
            return current
        field_index = [current.fields.index(field) for field in fields]
        return QueryResult(
            fields=fields,
            items=[[row[i] for i in field_index] for row in current.items],
        )

    @staticmethod
    def _filter_trade_cal(result: QueryResult, params: Dict[str, Any]) -> QueryResult:
        start_date = params.get('start_date')
        end_date = params.get('end_date')
        filtered = []
        for row in result.items:
            cal_date = row[0]
            if start_date and cal_date < start_date:
                continue
            if end_date and cal_date > end_date:
                continue
            filtered.append(row)
        return QueryResult(fields=result.fields, items=filtered)

    @staticmethod
    def _override_trade_date(result: QueryResult, trade_date: str) -> QueryResult:
        if 'trade_date' not in result.fields:
            return result
        idx = result.fields.index('trade_date')
        items = []
        for row in result.items:
            new_row = list(row)
            new_row[idx] = trade_date
            items.append(new_row)
        return QueryResult(fields=result.fields, items=items)

    @staticmethod
    def _filter_by_ts_code(result: QueryResult, ts_code: str) -> QueryResult:
        if 'ts_code' not in result.fields:
            return result
        idx = result.fields.index('ts_code')
        return QueryResult(fields=result.fields, items=[row for row in result.items if row[idx] == ts_code])

    @staticmethod
    def _filter_by_trade_date(result: QueryResult, trade_date: str) -> QueryResult:
        if 'trade_date' not in result.fields:
            return result
        idx = result.fields.index('trade_date')
        return QueryResult(fields=result.fields, items=[row for row in result.items if row[idx] == trade_date])

    @staticmethod
    def _filter_by_ann_date(result: QueryResult, ann_date: str) -> QueryResult:
        if 'ann_date' not in result.fields:
            return result
        idx = result.fields.index('ann_date')
        return QueryResult(fields=result.fields, items=[row for row in result.items if row[idx] == ann_date])

    @staticmethod
    def _filter_by_index_code(result: QueryResult, index_code: str) -> QueryResult:
        if 'index_code' not in result.fields:
            return result
        idx = result.fields.index('index_code')
        return QueryResult(fields=result.fields, items=[row for row in result.items if row[idx] == index_code])

    @staticmethod
    def _filter_by_l2_code(result: QueryResult, l2_code: str) -> QueryResult:
        if 'l2_code' not in result.fields:
            return result
        idx = result.fields.index('l2_code')
        return QueryResult(fields=result.fields, items=[row for row in result.items if row[idx] == l2_code])

    @staticmethod
    def _filter_by_id(result: QueryResult, record_id: str) -> QueryResult:
        if 'id' not in result.fields:
            return result
        idx = result.fields.index('id')
        return QueryResult(fields=result.fields, items=[row for row in result.items if row[idx] == record_id])

    @staticmethod
    def _filter_dc_index(result: QueryResult, params: Dict[str, Any]) -> QueryResult:
        current = result
        trade_date = params.get('trade_date')
        idx_type = params.get('idx_type')
        if trade_date:
            current = MockTushareClient._filter_by_trade_date(current, trade_date)
        if idx_type and 'idx_type' in current.fields:
            idx = current.fields.index('idx_type')
            current = QueryResult(fields=current.fields, items=[row for row in current.items if row[idx] == idx_type])
        return current

    @staticmethod
    def _filter_index_classify(result: QueryResult, params: Dict[str, Any]) -> QueryResult:
        level = params.get('level')
        if not level or 'level' not in result.fields:
            return result
        idx = result.fields.index('level')
        return QueryResult(fields=result.fields, items=[row for row in result.items if row[idx] == level])
