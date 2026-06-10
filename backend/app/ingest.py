from __future__ import annotations

import logging
import math
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from threading import Lock
from typing import Any, Callable, Dict, Iterable, List, TypeVar

from .db import Database


@dataclass(frozen=True)
class TableSpec:
    api_name: str
    table_name: str
    columns: List[str]
    key_columns: List[str]
    source_map: Dict[str, str] = field(default_factory=dict)

    @property
    def query_fields(self) -> List[str]:
        seen: List[str] = []
        for column in self.columns:
            source_field = self.source_map.get(column, column)
            if source_field not in seen:
                seen.append(source_field)
        return seen


REFERENCE_SPECS = [
    TableSpec('stock_basic', 't_stock_basic', ['ts_code', 'symbol', 'name', 'industry', 'list_date'], ['ts_code']),
    TableSpec('trade_cal', 't_trade_cal', ['cal_date', 'is_open'], ['cal_date']),
]

MARKET_BY_DATE_SPECS = [
    TableSpec('daily', 't_daily_bar', ['ts_code', 'trade_date', 'open', 'high', 'low', 'close', 'vol', 'amount', 'pct_chg'], ['ts_code', 'trade_date']),
    TableSpec('adj_factor', 't_adj_factor', ['ts_code', 'trade_date', 'adj_factor'], ['ts_code', 'trade_date']),
    TableSpec('daily_basic', 't_daily_basic', ['ts_code', 'trade_date', 'turnover_rate', 'volume_ratio', 'circ_mv'], ['ts_code', 'trade_date']),
]

STATIC_SUPPLEMENTAL_SPECS = [
    TableSpec('dc_member', 't_concept_detail', ['id', 'concept_name', 'ts_code', 'name'], ['id', 'ts_code']),
]

COMMON_DATE_SUPPLEMENTAL_SPECS = [
    TableSpec(
        'top_list',
        't_top_list',
        ['ts_code', 'trade_date', 'name', 'net', 'buy', 'sell', 'reason'],
        ['ts_code', 'trade_date', 'reason'],
        source_map={'net': 'net_amount', 'buy': 'l_buy', 'sell': 'l_sell'},
    ),
]

FULL_MARKET_SUPPLEMENTAL_SPECS = [
    TableSpec(
        'share_float',
        't_share_float',
        ['ts_code', 'ann_date', 'float_date', 'float_share', 'float_ratio', 'holder_name', 'share_type'],
        ['ts_code', 'float_date', 'holder_name', 'share_type'],
    ),
    TableSpec(
        'fina_indicator',
        't_fin_indicator',
        ['ts_code', 'ann_date', 'end_date', 'debt_to_assets', 'roe'],
        ['ts_code', 'ann_date', 'end_date'],
    ),
]

FEATURED_DATE_SUPPLEMENTAL_SPECS = [
    TableSpec(
        'cyq_perf',
        't_cyq_perf',
        ['ts_code', 'trade_date', 'winner_rate', 'cost_50', 'cost_85', 'concentration'],
        ['ts_code', 'trade_date'],
        source_map={'cost_50': 'cost_50pct', 'cost_85': 'cost_85pct', 'concentration': 'cost_50pct'},
    ),
]

DATE_DRIVEN_SUPPLEMENTAL_API_NAMES = {'top_list', 'cyq_perf'}

ALL_DROP_TABLES = [
    't_strategy_daily', 't_fin_indicator', 't_share_float', 't_top_list', 't_cyq_perf',
    't_concept_detail', 't_daily_basic', 't_adj_factor', 't_daily_bar', 't_trade_cal', 't_stock_basic',
]

PARAM_BATCH_SIZE = 500
SHARE_FLOAT_ANN_LOOKBACK_DAYS = 30
SHARE_FLOAT_TRADE_LOOKBACK_DAYS = 7
SHARE_FLOAT_FUTURE_DAYS = 60
DEFAULT_RETRY_MAX_ATTEMPTS = 3
DEFAULT_RETRY_BASE_DELAY = 0.5
DEFAULT_RETRY_MAX_DELAY = 8.0
DEFAULT_QPS_LIMIT = 3.0
DEFAULT_QPS_BURST = 6
PROGRESS_BATCH_LOG_EVERY = 10
PROGRESS_TRADE_DATE_LOG_EVERY = 10
DEFAULT_API_CONCURRENCY_LIMITS = {
    'stock_basic': 2,
    'trade_cal': 2,
    'daily': 12,
    'adj_factor': 12,
    'daily_basic': 10,
    'dc_index': 2,
    'dc_member': 8,
    'cyq_perf': 4,
    'top_list': 4,
    'share_float': 6,
    'fina_indicator': 6,
    'index_classify': 2,
    'index_member_all': 2,
}
DEFAULT_API_QPS_LIMITS = {
    'stock_basic': 4.0,
    'trade_cal': 4.0,
    'daily': 4.0,
    'adj_factor': 4.0,
    'daily_basic': 4.0,
    'dc_index': 2.0,
    'dc_member': 4.0,
    'top_list': 4.0,
    'share_float': 4.0,
    'fina_indicator': 4.0,
    'cyq_perf': 2.0,
    'index_classify': 2.0,
    'index_member_all': 2.0,
}
HARD_API_CONCURRENCY_CAPS = {
    'cyq_perf': 1,
    'top_list': 1,
}
RATE_LIMIT_ERROR_MARKERS = (
    '每分钟最多访问该接口',
    '最多访问该接口',
    'rate limit',
    'too many requests',
)
RATE_LIMIT_MAX_RETRIES = 20
RATE_LIMIT_COOLDOWN_SECONDS = 65.0
STRATEGY_TS_CODE_BATCH_SIZE = 200
REQUIRED_NOT_NULL_COLUMNS_BY_TABLE = {
    't_fin_indicator': ['ts_code', 'ann_date', 'end_date'],
}
SW_INDEX_CLASSIFY_FIELDS = ['index_code', 'industry_name', 'level', 'industry_code', 'parent_code']
SW_INDEX_MEMBER_FIELDS = ['l1_code', 'l1_name', 'l2_code', 'l2_name', 'l3_code', 'l3_name', 'ts_code', 'name', 'in_date', 'out_date', 'is_new']
DC_INDEX_FIELDS = ['ts_code', 'trade_date', 'name', 'idx_type']
DC_MEMBER_FIELDS = ['trade_date', 'ts_code', 'con_code', 'name']
StageCallback = Callable[[str, float, str, Dict[str, Any], str], None]
_T = TypeVar('_T')


class TokenBucketRateLimiter:
    def __init__(self, qps_limit: float, burst: int):
        self.qps_limit = max(qps_limit, 0.1)
        self.capacity = max(burst, 1)
        self.tokens = float(self.capacity)
        self.last_refill = time.monotonic()
        self._lock = Lock()

    def acquire(self) -> None:
        while True:
            wait_seconds = 0.0
            with self._lock:
                now = time.monotonic()
                elapsed = max(now - self.last_refill, 0.0)
                refill = elapsed * self.qps_limit
                if refill > 0:
                    self.tokens = min(float(self.capacity), self.tokens + refill)
                    self.last_refill = now
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
                shortage = 1.0 - self.tokens
                wait_seconds = shortage / self.qps_limit
            time.sleep(max(wait_seconds, 0.001))


class DataIngestionService:
    def __init__(
        self,
        client: Any,
        database: Database,
        max_workers: int = 10,
        client_factory=None,
        qps_limit: float = DEFAULT_QPS_LIMIT,
        qps_burst: int = DEFAULT_QPS_BURST,
        retry_max_attempts: int = DEFAULT_RETRY_MAX_ATTEMPTS,
        retry_base_delay: float = DEFAULT_RETRY_BASE_DELAY,
        retry_max_delay: float = DEFAULT_RETRY_MAX_DELAY,
        api_qps_limits: Dict[str, float] | None = None,
        api_concurrency_limits: Dict[str, int] | None = None,
        table_concurrency_limits: Dict[str, int] | None = None,
        heartbeat_interval_seconds: int = 30,
        verbose_request_logs: bool = False,
    ):
        self.client = client
        self.database = database
        self.max_workers = max_workers
        self.client_factory = client_factory
        self.retry_max_attempts = max(retry_max_attempts, 1)
        self.retry_base_delay = max(retry_base_delay, 0.01)
        self.retry_max_delay = max(retry_max_delay, self.retry_base_delay)
        self.rate_limiter = TokenBucketRateLimiter(qps_limit=qps_limit, burst=qps_burst)
        self.api_qps_limits = dict(DEFAULT_API_QPS_LIMITS)
        if api_qps_limits:
            for api_name, limit in api_qps_limits.items():
                parsed_limit = max(float(limit), 0.1)
                self.api_qps_limits[str(api_name)] = parsed_limit
        self.api_rate_limiters: Dict[str, TokenBucketRateLimiter] = {}
        for api_name, limit in self.api_qps_limits.items():
            burst = max(int(math.ceil(limit * 2)), 1)
            self.api_rate_limiters[api_name] = TokenBucketRateLimiter(qps_limit=limit, burst=burst)
        self.api_concurrency_limits = dict(DEFAULT_API_CONCURRENCY_LIMITS)
        if api_concurrency_limits:
            for api_name, limit in api_concurrency_limits.items():
                parsed_limit = max(int(limit), 1)
                self.api_concurrency_limits[str(api_name)] = parsed_limit
        self.table_concurrency_limits: Dict[str, int] = {}
        if table_concurrency_limits:
            for table_name, limit in table_concurrency_limits.items():
                parsed_limit = max(int(limit), 1)
                self.table_concurrency_limits[str(table_name)] = parsed_limit
        self.heartbeat_interval_seconds = max(int(heartbeat_interval_seconds), 5)
        self.verbose_request_logs = verbose_request_logs
        self._stats_lock = Lock()
        self._stats = {
            'requests_started': 0,
            'requests_success': 0,
            'requests_failed': 0,
            'retries': 0,
            'records_fetched': 0,
            'records_dropped': 0,
            'rows_upserted': 0,
        }
        self._work_total: int = 0
        self._work_completed: int = 0
        self._work_unit: str = 'unit'
        self._run_started_ts = time.monotonic()
        self._last_activity_ts = time.monotonic()
        self._heartbeat_stop_event: threading.Event | None = None
        self._heartbeat_thread: threading.Thread | None = None
        self._heartbeat_depth = 0
        self._heartbeat_depth_lock = Lock()
        self._unavailable_api_errors: Dict[str, Exception] = {}
        self._unavailable_api_lock = Lock()

    @staticmethod
    def _log(message: str) -> None:
        print(message, flush=True)

    def _touch_activity(self) -> None:
        with self._stats_lock:
            self._last_activity_ts = time.monotonic()

    def _inc_stat(self, key: str, value: int = 1) -> None:
        with self._stats_lock:
            self._stats[key] = int(self._stats.get(key, 0)) + int(value)
            self._last_activity_ts = time.monotonic()

    def _snapshot_stats(self) -> dict[str, float]:
        with self._stats_lock:
            snapshot = dict(self._stats)
            snapshot['last_activity_age'] = max(time.monotonic() - self._last_activity_ts, 0.0)
            snapshot['work_total'] = self._work_total
            snapshot['work_completed'] = self._work_completed
            snapshot['run_elapsed_s'] = max(time.monotonic() - self._run_started_ts, 0.0)
            snapshot['work_unit'] = self._work_unit
        return snapshot

    def _reset_stats(self) -> None:
        with self._stats_lock:
            for key in self._stats.keys():
                self._stats[key] = 0
            self._work_total = 0
            self._work_completed = 0
            self._work_unit = 'unit'
            self._run_started_ts = time.monotonic()
            self._last_activity_ts = time.monotonic()

    def _set_workload(self, total: int, unit: str = 'unit') -> None:
        with self._stats_lock:
            self._work_total = max(int(total), 0)
            self._work_completed = 0
            self._work_unit = (unit or 'unit').strip() or 'unit'
            self._last_activity_ts = time.monotonic()

    def _set_work_progress(self, completed: int) -> None:
        with self._stats_lock:
            if self._work_total > 0:
                self._work_completed = max(0, min(int(completed), self._work_total))
            else:
                self._work_completed = max(int(completed), 0)
            self._last_activity_ts = time.monotonic()

    def _start_heartbeat(self, run_label: str) -> bool:
        with self._heartbeat_depth_lock:
            self._heartbeat_depth += 1
            if self._heartbeat_depth > 1:
                return False
            self._reset_stats()
            self._heartbeat_stop_event = threading.Event()

        def _heartbeat_loop():
            while self._heartbeat_stop_event and not self._heartbeat_stop_event.wait(self.heartbeat_interval_seconds):
                stats = self._snapshot_stats()
                status = 'normal_running'
                if stats['last_activity_age'] > self.heartbeat_interval_seconds * 2:
                    status = 'possible_stall'
                timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
                work_total = int(stats.get('work_total', 0) or 0)
                work_completed = int(stats.get('work_completed', 0) or 0)
                run_elapsed_s = float(stats.get('run_elapsed_s', 0.0) or 0.0)
                rate_per_min = 0.0
                percent = 0.0
                eta_str = 'n/a'
                if run_elapsed_s > 0 and work_completed > 0:
                    rate_per_min = work_completed / run_elapsed_s * 60.0
                if work_total > 0:
                    percent = min(work_completed / work_total * 100.0, 100.0)
                    if rate_per_min > 0 and work_completed <= work_total:
                        remain_units = work_total - work_completed
                        eta_minutes = remain_units / rate_per_min
                        eta_time = datetime.utcnow() + timedelta(minutes=eta_minutes)
                        eta_str = eta_time.strftime('%Y-%m-%dT%H:%M:%SZ')
                self._log(
                    f"[heartbeat] ts={timestamp} run={run_label} status={status} "
                    f"started={int(stats['requests_started'])} success={int(stats['requests_success'])} "
                    f"failed={int(stats['requests_failed'])} retries={int(stats['retries'])} "
                    f"fetched={int(stats['records_fetched'])} dropped={int(stats['records_dropped'])} "
                    f"upserted={int(stats['rows_upserted'])} idle_s={stats['last_activity_age']:.1f} "
                    f"work={work_completed}/{work_total} unit={stats.get('work_unit', 'unit')} "
                    f"progress={percent:.1f}% rate={rate_per_min:.2f}/min eta={eta_str}"
                )

        self._heartbeat_thread = threading.Thread(target=_heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()
        return True

    def _stop_heartbeat(self, started_here: bool) -> None:
        with self._heartbeat_depth_lock:
            if self._heartbeat_depth > 0:
                self._heartbeat_depth -= 1
            should_stop = started_here and self._heartbeat_depth == 0
        if not should_stop:
            return
        if self._heartbeat_stop_event:
            self._heartbeat_stop_event.set()
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=1.0)
        self._heartbeat_stop_event = None
        self._heartbeat_thread = None

    def _run_with_heartbeat(self, run_label: str, func: Callable[[], _T]) -> _T:
        started_here = self._start_heartbeat(run_label)
        started = time.monotonic()
        try:
            result = func()
            if started_here:
                stats = self._snapshot_stats()
                self._log(
                    f"[heartbeat] run={run_label} status=completed elapsed_s={(time.monotonic() - started):.1f} "
                    f"started={int(stats['requests_started'])} success={int(stats['requests_success'])} "
                    f"failed={int(stats['requests_failed'])} retries={int(stats['retries'])} "
                    f"fetched={int(stats['records_fetched'])} dropped={int(stats['records_dropped'])} "
                    f"upserted={int(stats['rows_upserted'])}"
                )
            return result
        except BaseException as exc:
            if started_here:
                stats = self._snapshot_stats()
                self._log(
                    f"[heartbeat] run={run_label} status=abnormal_exit elapsed_s={(time.monotonic() - started):.1f} "
                    f"error={exc} started={int(stats['requests_started'])} success={int(stats['requests_success'])} "
                    f"failed={int(stats['requests_failed'])} retries={int(stats['retries'])} "
                    f"fetched={int(stats['records_fetched'])} dropped={int(stats['records_dropped'])} "
                    f"upserted={int(stats['rows_upserted'])}"
                )
            raise
        finally:
            self._stop_heartbeat(started_here)

    def run_full_sync(
        self,
        trade_date: str | None = None,
        stage_callback: StageCallback | None = None,
    ) -> Dict[str, Dict[str, Any]]:
        def _run():
            summary = self.run_common_sync(trade_date=trade_date, stage_callback=stage_callback)
            featured_summary = self.run_featured_sync(trade_date=trade_date, stage_callback=stage_callback)
            self._merge_table_summaries(summary, featured_summary)
            summary['t_strategy_daily'] = self._measure_stage(
                'build_strategy_daily',
                self._build_strategy_daily,
                stage_callback,
            )
            return summary
        return self._run_with_heartbeat('run_full_sync', _run)

    def run_common_sync(
        self,
        trade_date: str | None = None,
        include_static_supplemental: bool = True,
        stage_callback: StageCallback | None = None,
    ) -> Dict[str, Dict[str, Any]]:
        def _run():
            summary: Dict[str, Dict[str, Any]] = {}
            trade_dates = self._measure_stage(
                'sync_reference_tables',
                lambda: self._sync_reference_tables(summary, trade_date=trade_date),
                stage_callback,
            )
            if trade_dates:
                trade_dates = self._measure_stage(
                    'resolve_latest_market_dates',
                    lambda: self._resolve_latest_market_dates(trade_dates),
                    stage_callback,
                    extra={'candidate_dates': len(trade_dates)},
                )
            self._measure_stage(
                'sync_market_tables',
                lambda: self._sync_market_tables(summary, trade_dates),
                stage_callback,
                extra={'trade_dates': len(trade_dates)},
            )
            self._measure_stage(
                'sync_common_date_supplemental_tables',
                lambda: self._sync_date_supplemental_tables(summary, trade_dates, COMMON_DATE_SUPPLEMENTAL_SPECS),
                stage_callback,
                extra={'trade_dates': len(trade_dates)},
            )
            if include_static_supplemental:
                self._measure_stage(
                    'sync_static_supplemental_tables',
                    lambda: self._sync_static_supplemental_tables(summary, STATIC_SUPPLEMENTAL_SPECS),
                    stage_callback,
                )
            return summary
        return self._run_with_heartbeat('run_common_sync', _run)

    def run_featured_sync(
        self,
        trade_date: str | None = None,
        stage_callback: StageCallback | None = None,
    ) -> Dict[str, Dict[str, Any]]:
        def _run():
            summary: Dict[str, Dict[str, Any]] = {}
            trade_dates = self._measure_stage(
                'resolve_featured_trade_dates',
                lambda: self._resolve_featured_trade_dates(trade_date),
                stage_callback,
            )
            try:
                self._measure_stage(
                    'sync_featured_date_supplemental_tables',
                    lambda: self._sync_date_supplemental_tables(summary, trade_dates, FEATURED_DATE_SUPPLEMENTAL_SPECS),
                    stage_callback,
                    extra={'trade_dates': len(trade_dates)},
                )
            except Exception as exc:
                if not self._is_upstream_internal_unavailable(exc):
                    raise
                self._log(
                    f"[warn] skip cyq_perf because upstream internal service is unavailable; "
                    f"existing data is preserved error={exc}"
                )
                spec = self._find_spec('cyq_perf', FEATURED_DATE_SUPPLEMENTAL_SPECS)
                summary[spec.table_name] = {
                    **self._validate_records(spec.columns, [], 0),
                    'warning': str(exc),
                }
            return summary
        return self._run_with_heartbeat('run_featured_sync', _run)

    def run_strategy_sync(
        self,
        trade_date: str | None = None,
        stage_callback: StageCallback | None = None,
    ) -> Dict[str, Dict[str, Any]]:
        def _run():
            return {
                't_strategy_daily': self._measure_stage(
                    'build_strategy_daily',
                    lambda: self._build_strategy_daily(trade_date=trade_date),
                    stage_callback,
                )
            }
        return self._run_with_heartbeat('run_strategy_sync', _run)

    def run_history_sync(
        self,
        start_date: str,
        end_date: str,
        progress_callback: Callable[[str], None] | None = None,
        stage_callback: StageCallback | None = None,
    ) -> Dict[str, Dict[str, Any]]:
        def _run():
            summary: Dict[str, Dict[str, Any]] = {}
            trade_dates = self._measure_stage(
                'sync_reference_tables',
                lambda: self._sync_reference_tables(summary, start_date=start_date, end_date=end_date),
                stage_callback,
            )
            total_trade_dates = len(trade_dates)
            self._set_workload(total_trade_dates, unit='trade_date')
            for index, trade_date in enumerate(trade_dates, start=1):
                batch_summary: Dict[str, Dict[str, Any]] = {}
                self._measure_stage(
                    'history_sync_market_by_date',
                    lambda td=trade_date: self._sync_market_tables(batch_summary, [td]),
                    stage_callback,
                    extra={'trade_date': trade_date},
                )
                self._measure_stage(
                    'history_sync_date_supplemental',
                    lambda td=trade_date: self._sync_date_supplemental_tables(batch_summary, [td], COMMON_DATE_SUPPLEMENTAL_SPECS + FEATURED_DATE_SUPPLEMENTAL_SPECS),
                    stage_callback,
                    extra={'trade_date': trade_date},
                )
                self._merge_table_summaries(summary, batch_summary)
                self._set_work_progress(index)
                if progress_callback:
                    progress_callback(trade_date)
                should_log_progress = (
                    index == 1
                    or index == total_trade_dates
                    or index % PROGRESS_TRADE_DATE_LOG_EVERY == 0
                )
                if should_log_progress:
                    percent = (index / total_trade_dates * 100.0) if total_trade_dates else 100.0
                    self._log(
                        f"[progress] history trade_date {index}/{total_trade_dates} "
                        f"({percent:.1f}%) current={trade_date}"
                    )
            summary['t_strategy_daily'] = self._measure_stage(
                'build_strategy_daily',
                self._build_strategy_daily,
                stage_callback,
            )
            market_total_rows = (
                int(summary.get('t_daily_bar', {}).get('rows', 0) or 0)
                + int(summary.get('t_adj_factor', {}).get('rows', 0) or 0)
                + int(summary.get('t_daily_basic', {}).get('rows', 0) or 0)
            )
            strategy_rows = int(summary.get('t_strategy_daily', {}).get('rows', 0) or 0)
            if market_total_rows == 0:
                raise RuntimeError(
                    'history_sync produced zero market rows: '
                    't_daily_bar/t_adj_factor/t_daily_basic are all empty'
                )
            if strategy_rows == 0:
                raise RuntimeError('history_sync produced zero strategy rows in t_strategy_daily')
            return summary
        return self._run_with_heartbeat('run_history_sync', _run)

    def run_sw_industry_sync(
        self,
        stage_callback: StageCallback | None = None,
    ) -> Dict[str, Dict[str, Any]]:
        def _run():
            return {
                't_stock_basic': self._measure_stage(
                    'sync_sw_industry_mapping',
                    self._sync_sw_industry_mapping,
                    stage_callback,
                )
            }
        return self._run_with_heartbeat('run_sw_industry_sync', _run)

    def run_weekly_sync(
        self,
        stage_callback: StageCallback | None = None,
    ) -> Dict[str, Dict[str, Any]]:
        def _run():
            return {
                't_stock_basic': self._measure_stage(
                    'sync_sw_industry_mapping',
                    self._sync_sw_industry_mapping,
                    stage_callback,
                )
            }
        return self._run_with_heartbeat('run_weekly_sync', _run)

    def run_monthly_sync(
        self,
        stage_callback: StageCallback | None = None,
        checkpoint_store=None,
    ) -> Dict[str, Dict[str, Any]]:
        def _run():
            summary: Dict[str, Dict[str, Any]] = {}
            for api_name in ('dc_member', 'share_float'):
                spec = self._find_spec(api_name, STATIC_SUPPLEMENTAL_SPECS + FULL_MARKET_SUPPLEMENTAL_SPECS)
                try:
                    if api_name == 'share_float':
                        sync_func = lambda spec=spec: self._sync_share_float_incremental(
                            spec,
                            checkpoint_store=checkpoint_store,
                        )
                    else:
                        sync_func = lambda spec=spec: self._sync_spec_in_batches(
                            spec,
                            self._build_query_param_list(spec.api_name, None),
                        )
                    summary[spec.table_name] = self._measure_stage(
                        f'sync_{spec.table_name}',
                        sync_func,
                        stage_callback,
                    )
                except Exception as exc:
                    if not self._is_upstream_internal_unavailable(exc):
                        raise
                    self._log(
                        f"[warn] skip {api_name} because upstream internal service is unavailable; "
                        f"existing data is preserved error={exc}"
                    )
                    summary[spec.table_name] = {
                        **self._validate_records(spec.columns, [], 0),
                        'warning': str(exc),
                    }
            summary['t_strategy_daily'] = self._measure_stage(
                'rebuild_strategy_share_float_impact',
                self._rebuild_strategy_for_share_float_impact_dates,
                stage_callback,
            )
            return summary
        return self._run_with_heartbeat('run_monthly_sync', _run)

    def run_quarterly_sync(
        self,
        stage_callback: StageCallback | None = None,
    ) -> Dict[str, Dict[str, Any]]:
        def _run():
            summary: Dict[str, Dict[str, Any]] = {}
            spec = self._find_spec('fina_indicator', FULL_MARKET_SUPPLEMENTAL_SPECS)
            try:
                summary[spec.table_name] = self._measure_stage(
                    f'sync_{spec.table_name}',
                    lambda: self._sync_spec_in_batches(spec, self._build_query_param_list(spec.api_name, None)),
                    stage_callback,
                )
            except Exception as exc:
                if not self._is_upstream_internal_unavailable(exc):
                    raise
                self._log(
                    f"[warn] skip fina_indicator because upstream internal service is unavailable; "
                    f"existing data is preserved error={exc}"
                )
                summary[spec.table_name] = {
                    **self._validate_records(spec.columns, [], 0),
                    'warning': str(exc),
                }
            return summary
        return self._run_with_heartbeat('run_quarterly_sync', _run)

    def run_yearly_sync(
        self,
        stage_callback: StageCallback | None = None,
    ) -> Dict[str, Dict[str, Any]]:
        def _run():
            return {
                't_strategy_daily': self._measure_stage(
                    'rebuild_strategy_daily_full',
                    self._build_strategy_daily,
                    stage_callback,
                )
            }
        return self._run_with_heartbeat('run_yearly_sync', _run)

    @staticmethod
    def _emit_stage(
        stage_callback: StageCallback | None,
        stage_name: str,
        duration_seconds: float,
        status: str = 'success',
        extra: Dict[str, Any] | None = None,
        message: str = '',
    ) -> None:
        if stage_callback is None:
            return
        stage_callback(stage_name, duration_seconds, status, extra or {}, message)

    @staticmethod
    def _find_spec(api_name: str, specs: List[TableSpec]) -> TableSpec:
        for spec in specs:
            if spec.api_name == api_name:
                return spec
        raise ValueError(f'table spec not found for api: {api_name}')

    def _measure_stage(
        self,
        stage_name: str,
        func: Callable[[], _T],
        stage_callback: StageCallback | None,
        extra: Dict[str, Any] | None = None,
    ) -> _T:
        started = time.monotonic()
        self._log(f"[stage] start {stage_name} extra={extra or {}}")
        try:
            result = func()
            duration = time.monotonic() - started
            self._log(f"[stage] success {stage_name} duration={duration:.3f}s")
            self._emit_stage(stage_callback, stage_name, time.monotonic() - started, 'success', extra or {})
            return result
        except Exception as exc:
            duration = time.monotonic() - started
            self._log(f"[stage] failed {stage_name} duration={duration:.3f}s error={exc}")
            self._emit_stage(
                stage_callback,
                stage_name,
                time.monotonic() - started,
                'failed',
                extra or {},
                str(exc),
            )
            raise

    def _sync_reference_tables(
        self,
        summary: Dict[str, Dict[str, Any]],
        trade_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> List[str]:
        stock_spec = next(spec for spec in REFERENCE_SPECS if spec.api_name == 'stock_basic')
        stock_records = self._fetch_records(stock_spec, {})
        summary[stock_spec.table_name] = self._upsert_records(stock_spec, stock_records)

        cal_spec = next(spec for spec in REFERENCE_SPECS if spec.api_name == 'trade_cal')
        cal_params = self._trade_cal_params(trade_date=trade_date, start_date=start_date, end_date=end_date)
        cal_records = self._fetch_records(cal_spec, cal_params)
        summary[cal_spec.table_name] = self._upsert_records(cal_spec, cal_records)
        trade_dates = sorted(record['cal_date'] for record in cal_records if record.get('is_open') == 1)
        return trade_dates

    @staticmethod
    def _pick_industry_name(record: Dict[str, Any]) -> str | None:
        value = record.get('industry_name')
        if value:
            return str(value)
        value = record.get('index_name')
        if value:
            return str(value)
        value = record.get('name')
        if value:
            return str(value)
        return None

    def _sync_sw_industry_mapping(self) -> Dict[str, Any]:
        l1_records = self._query_any_fields('index_classify', {'level': 'L1'}, fields=SW_INDEX_CLASSIFY_FIELDS)
        l2_records = self._query_any_fields('index_classify', {'level': 'L2'}, fields=SW_INDEX_CLASSIFY_FIELDS)
        if not l1_records and not l2_records:
            return self._validate_records(
                ['ts_code', 'symbol', 'name', 'industry', 'sw_level1_name', 'sw_level2_name', 'list_date'],
                [],
                0,
            )

        l1_name_by_code: Dict[str, str] = {}
        for rec in l1_records:
            name = self._pick_industry_name(rec)
            if not name:
                continue
            index_code = rec.get('index_code')
            industry_code = rec.get('industry_code')
            if index_code:
                l1_name_by_code[str(index_code)] = name
            if industry_code:
                l1_name_by_code[str(industry_code)] = name

        l2_meta: Dict[str, tuple[str | None, str | None]] = {}
        for rec in l2_records:
            code = rec.get('index_code')
            if not code:
                continue
            l2_name = self._pick_industry_name(rec)
            parent_code = rec.get('parent_code')
            l2_meta[str(code)] = (l2_name, str(parent_code) if parent_code else None)

        stock_rows = self.database.fetch_all(
            'SELECT ts_code, symbol, name, industry, sw_level1_name, sw_level2_name, list_date FROM t_stock_basic'
        )
        stock_by_code = {row['ts_code']: dict(row) for row in stock_rows if row['ts_code']}

        best_mapping: Dict[str, tuple[int, str | None, str | None]] = {}
        membership_candidates: Dict[str, List[tuple[str | None, str | None, str, bool]]] = {}
        index_member_available = True
        for l2_code, (l2_name, parent_code) in l2_meta.items():
            if not index_member_available:
                break
            try:
                members = self._query_any_fields('index_member_all', {'l2_code': l2_code}, fields=SW_INDEX_MEMBER_FIELDS)
            except Exception as exc:
                logging.getLogger(__name__).warning(
                    "index_member_all API unavailable, skipping SW industry mapping: %s", exc
                )
                index_member_available = False
                break
            l1_name = l1_name_by_code.get(parent_code or '')
            for rec in members:
                ts_code = rec.get('ts_code')
                if not ts_code or ts_code not in stock_by_code:
                    continue
                out_date = rec.get('out_date')
                in_date = str(rec.get('in_date') or '')
                active = 1 if not out_date else 0
                membership_candidates.setdefault(str(ts_code), []).append((l1_name, l2_name, in_date, bool(active)))
                rank = active * 10_000_000 + int(in_date or '0')
                current = best_mapping.get(ts_code)
                if current is None or rank > current[0]:
                    best_mapping[str(ts_code)] = (rank, l1_name, l2_name)

        if not best_mapping:
            return self._validate_records(
                ['ts_code', 'symbol', 'name', 'industry', 'sw_level1_name', 'sw_level2_name', 'list_date'],
                [],
                0,
            )

        multi_membership_stocks = sum(1 for items in membership_candidates.values() if len(items) > 1)
        ambiguous_active_memberships = {
            ts_code: items
            for ts_code, items in membership_candidates.items()
            if sum(1 for _, _, _, is_active in items if is_active) > 1
        }
        if ambiguous_active_memberships:
            sample = [
                {
                    'ts_code': ts_code,
                    'memberships': [
                        {
                            'sw_level1_name': l1_name,
                            'sw_level2_name': l2_name,
                            'in_date': in_date,
                        }
                        for l1_name, l2_name, in_date, is_active in items if is_active
                    ],
                }
                for ts_code, items in list(sorted(ambiguous_active_memberships.items()))[:5]
            ]
            self._log(
                f"[warn] sync_sw_industry_mapping found {len(ambiguous_active_memberships)} stocks with "
                f"multiple active SW memberships; keeping the latest in_date mapping sample={sample}"
            )

        columns = ['ts_code', 'symbol', 'name', 'industry', 'sw_level1_name', 'sw_level2_name', 'list_date']
        records: List[Dict[str, Any]] = []
        for ts_code, (_, l1_name, l2_name) in best_mapping.items():
            base = stock_by_code[ts_code]
            records.append(
                {
                    'ts_code': base.get('ts_code'),
                    'symbol': base.get('symbol'),
                    'name': base.get('name'),
                    'industry': base.get('industry'),
                    'sw_level1_name': l1_name,
                    'sw_level2_name': l2_name,
                    'list_date': base.get('list_date'),
                }
            )
        rows = [tuple(record.get(column) for column in columns) for record in records]
        inserted = self.database.upsert_many('t_stock_basic', columns, rows, ['ts_code'])
        self._inc_stat('rows_upserted', inserted)
        summary = self._validate_records(columns, records, inserted)
        summary['multi_membership_stocks'] = multi_membership_stocks
        summary['ambiguous_active_memberships'] = len(ambiguous_active_memberships)
        return summary

    def _query_any_fields(
        self,
        api_name: str,
        params: Dict[str, Any],
        fields: List[str] | None = None,
    ) -> List[Dict[str, Any]]:
        unavailable_error = self._get_unavailable_api_error(api_name)
        if unavailable_error is not None:
            raise unavailable_error
        last_error: Exception | None = None
        for attempt in range(1, self.retry_max_attempts + 1):
            try:
                self._inc_stat('requests_started', 1)
                self.rate_limiter.acquire()
                result = self.client.query(api_name, fields or [], params=params)
                records = [self._sanitize_record(record) for record in result.to_dicts()]
                self._inc_stat('requests_success', 1)
                self._inc_stat('records_fetched', len(records))
                return records
            except Exception as exc:
                last_error = exc
                self._inc_stat('requests_failed', 1)
                if self._is_upstream_internal_unavailable(exc):
                    self._remember_unavailable_api_error(api_name, exc)
                    break
                if attempt >= self.retry_max_attempts:
                    break
                backoff = min(self.retry_base_delay * (2 ** (attempt - 1)), self.retry_max_delay)
                jitter = random.uniform(0.0, self.retry_base_delay)
                self._inc_stat('retries', 1)
                time.sleep(backoff + jitter)
        raise last_error

    def _sync_market_tables(self, summary: Dict[str, Dict[str, Any]], trade_dates: Iterable[str]) -> None:
        dates = list(trade_dates)
        for spec in MARKET_BY_DATE_SPECS:
            params_list = [{'trade_date': trade_date} for trade_date in dates]
            summary[spec.table_name] = self._sync_spec_in_batches(spec, params_list)

    def _resolve_latest_market_dates(self, trade_dates: List[str]) -> List[str]:
        daily_spec = next(spec for spec in MARKET_BY_DATE_SPECS if spec.api_name == 'daily')
        for candidate in reversed(trade_dates):
            if self._fetch_records(daily_spec, {'trade_date': candidate}):
                return [candidate]
        return []

    def _sync_static_supplemental_tables(
        self,
        summary: Dict[str, Dict[str, Any]],
        specs: List[TableSpec] | None = None,
    ) -> None:
        for spec in specs or STATIC_SUPPLEMENTAL_SPECS:
            param_list = self._build_query_param_list(spec.api_name, None)
            summary[spec.table_name] = self._sync_spec_in_batches(spec, param_list)

    def _sync_date_supplemental_tables(
        self,
        summary: Dict[str, Dict[str, Any]],
        trade_dates: Iterable[str],
        specs: List[TableSpec],
    ) -> None:
        dates = list(trade_dates)
        for spec in specs:
            if spec.api_name not in DATE_DRIVEN_SUPPLEMENTAL_API_NAMES:
                raise ValueError(
                    f"date supplemental sync only supports trade-date APIs; "
                    f"got api={spec.api_name}"
                )
            param_list = self._build_query_param_list(spec.api_name, dates)
            summary[spec.table_name] = self._sync_spec_in_batches(spec, param_list)

    def _resolve_featured_trade_dates(self, trade_date: str | None) -> List[str]:
        if trade_date:
            return [trade_date]
        rows = self.database.fetch_all('SELECT MAX(trade_date) AS trade_date FROM t_daily_bar')
        if rows and rows[0]['trade_date']:
            return [rows[0]['trade_date']]
        rows = self.database.fetch_all('SELECT MAX(cal_date) AS cal_date FROM t_trade_cal WHERE is_open = 1')
        if rows and rows[0]['cal_date']:
            return [rows[0]['cal_date']]
        return []

    def _resolve_concept_trade_date(self) -> str | None:
        rows = self.database.fetch_all('SELECT MAX(trade_date) AS trade_date FROM t_daily_bar')
        if rows and rows[0]['trade_date']:
            return rows[0]['trade_date']
        rows = self.database.fetch_all('SELECT MAX(cal_date) AS cal_date FROM t_trade_cal WHERE is_open = 1')
        if rows and rows[0]['cal_date']:
            return rows[0]['cal_date']
        return None

    def _build_query_param_list(self, api_name: str, trade_dates: List[str] | None) -> List[Dict[str, Any]]:
        if api_name == 'dc_member':
            concept_date = self._resolve_concept_trade_date()
            params = {'idx_type': '概念板块'}
            if concept_date:
                params['trade_date'] = concept_date
            concept_rows = self._query_any_fields('dc_index', params, fields=DC_INDEX_FIELDS)
            return [
                {
                    '_concept_name': row['name'],
                    'trade_date': row.get('trade_date') or concept_date,
                    'ts_code': row['ts_code'],
                }
                for row in concept_rows
                if row.get('ts_code') and row.get('name')
            ]
        if api_name in ('cyq_perf', 'top_list'):
            return [{'trade_date': trade_date} for trade_date in (trade_dates or [])]
        if api_name in ('share_float', 'fina_indicator'):
            rows = self.database.fetch_all('SELECT ts_code FROM t_stock_basic ORDER BY ts_code')
            return [{'ts_code': row['ts_code']} for row in rows]
        return [{}]

    def _sync_spec_in_batches(self, spec: TableSpec, params_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not params_list:
            return self._validate_records(spec.columns, [], 0)

        total_inserted = 0
        aggregate_missing: set[str] = set()
        aggregate_nulls: Dict[str, int] = {}
        aggregate_metrics: Dict[str, Any] = {}
        total_params = len(params_list)
        processed_params = 0
        total_batches = (total_params + PARAM_BATCH_SIZE - 1) // PARAM_BATCH_SIZE

        for batch_index, param_batch in enumerate(self._chunked(params_list, PARAM_BATCH_SIZE), start=1):
            batch_summary = self._fetch_and_upsert_records_batch(spec, param_batch)
            total_inserted += int(batch_summary['rows'])
            aggregate_missing.update(batch_summary['missing_fields'])
            for column, count in batch_summary['null_fields'].items():
                aggregate_nulls[column] = aggregate_nulls.get(column, 0) + int(count)
            aggregate_metrics = self._merge_metrics(aggregate_metrics, batch_summary.get('metrics') or {})
            processed_params += len(param_batch)
            should_log_progress = (
                batch_index == 1
                or batch_index == total_batches
                or batch_index % PROGRESS_BATCH_LOG_EVERY == 0
            )
            if should_log_progress:
                percent = (processed_params / total_params * 100.0) if total_params else 100.0
                self._log(
                    f"[progress] {spec.table_name} batch {batch_index}/{total_batches} "
                    f"params {processed_params}/{total_params} ({percent:.1f}%) inserted={total_inserted}"
                )

        summary = {
            'rows': total_inserted,
            'expected_fields': spec.columns,
            'missing_fields': sorted(aggregate_missing),
            'null_fields': aggregate_nulls,
        }
        final_metrics = self._finalize_sync_metrics(spec, params_list, aggregate_metrics)
        if final_metrics:
            summary['metrics'] = final_metrics
        return summary

    def _sync_share_float_incremental(
        self,
        spec: TableSpec,
        checkpoint_store=None,
        run_date: date | None = None,
        future_days: int = SHARE_FLOAT_FUTURE_DAYS,
    ) -> Dict[str, Any]:
        current_date = run_date or date.today()
        ann_start = current_date - timedelta(days=SHARE_FLOAT_ANN_LOOKBACK_DAYS)
        latest_trade_date = self._latest_trade_date()
        float_anchor = latest_trade_date or current_date
        float_start = float_anchor - timedelta(days=SHARE_FLOAT_TRADE_LOOKBACK_DAYS)
        float_end = current_date + timedelta(days=max(int(future_days), 0))

        total_inserted = 0
        aggregate_missing: set[str] = set()
        aggregate_nulls: Dict[str, int] = {}
        aggregate_metrics: Dict[str, Any] = {}
        axes = (
            ('ann_date', ann_start, current_date),
            ('float_date', float_start, float_end),
        )
        for field_name, requested_start, end_date in axes:
            axis_summary = self._sync_share_float_date_axis(
                spec,
                field_name,
                requested_start,
                end_date,
                checkpoint_store,
            )
            total_inserted += int(axis_summary['rows'])
            aggregate_missing.update(axis_summary['missing_fields'])
            for column, count in axis_summary['null_fields'].items():
                aggregate_nulls[column] = aggregate_nulls.get(column, 0) + int(count)
            self._merge_metrics_in_place(aggregate_metrics, axis_summary.get('metrics') or {})

        result = {
            'rows': total_inserted,
            'expected_fields': spec.columns,
            'missing_fields': sorted(aggregate_missing),
            'null_fields': aggregate_nulls,
        }
        if aggregate_metrics:
            result['metrics'] = aggregate_metrics
        return result

    def _sync_share_float_date_axis(
        self,
        spec: TableSpec,
        field_name: str,
        requested_start: date,
        end_date: date,
        checkpoint_store=None,
    ) -> Dict[str, Any]:
        target_range = f'share_float:{field_name}'
        start_text = requested_start.strftime('%Y%m%d')
        if checkpoint_store is not None:
            start_text = checkpoint_store.start_incremental_run(
                'job_monthly',
                target_range,
                start_text,
                requested_end=end_date.strftime('%Y%m%d'),
            )
        start_date = datetime.strptime(start_text, '%Y%m%d').date()
        dates = list(self._date_range(start_date, end_date))
        self._set_workload(len(dates), f'{field_name}_date')

        total_inserted = 0
        aggregate_missing: set[str] = set()
        aggregate_nulls: Dict[str, int] = {}
        aggregate_metrics: Dict[str, Any] = {}
        try:
            for index, query_date in enumerate(dates, start=1):
                date_text = query_date.strftime('%Y%m%d')
                records = self._fetch_share_float_date_records(spec, field_name, date_text)
                batch_summary = self._upsert_records(spec, records)
                total_inserted += int(batch_summary['rows'])
                aggregate_missing.update(batch_summary['missing_fields'])
                for column, count in batch_summary['null_fields'].items():
                    aggregate_nulls[column] = aggregate_nulls.get(column, 0) + int(count)
                self._merge_metrics_in_place(aggregate_metrics, batch_summary.get('metrics') or {})
                if checkpoint_store is not None:
                    checkpoint_store.mark_progress('job_monthly', target_range, date_text)
                self._set_work_progress(index)
                self._log(
                    f"[progress] {spec.table_name} {field_name} {index}/{len(dates)} "
                    f"date={date_text} inserted={total_inserted}"
                )
        except Exception:
            if checkpoint_store is not None:
                checkpoint_store.mark_failed('job_monthly', target_range)
            raise
        if checkpoint_store is not None:
            checkpoint_store.mark_success('job_monthly', target_range)

        result = {
            'rows': total_inserted,
            'expected_fields': spec.columns,
            'missing_fields': sorted(aggregate_missing),
            'null_fields': aggregate_nulls,
        }
        if aggregate_metrics:
            result['metrics'] = aggregate_metrics
        return result

    def _fetch_share_float_date_records(
        self,
        spec: TableSpec,
        field_name: str,
        date_text: str,
    ) -> List[Dict[str, Any]]:
        base_params = {field_name: date_text}
        records = self._fetch_records(spec, base_params)
        if len(records) != 6000:
            return records

        self._log(
            f"[warn] {spec.api_name} {field_name}={date_text} reached 6000-row limit; "
            "refetching by ts_code"
        )
        stock_rows = self.database.fetch_all('SELECT ts_code FROM t_stock_basic ORDER BY ts_code')
        params_list = [
            {field_name: date_text, 'ts_code': row['ts_code']}
            for row in stock_rows
            if row.get('ts_code')
        ]
        return self._fetch_records_batch(spec, params_list)

    def _latest_trade_date(self) -> date | None:
        rows = self.database.fetch_all('SELECT MAX(trade_date) AS trade_date FROM t_daily_bar')
        value = rows[0].get('trade_date') if rows else None
        if not value:
            return None
        try:
            return datetime.strptime(str(value), '%Y%m%d').date()
        except Exception:
            return None

    @staticmethod
    def _date_range(start_date: date, end_date: date) -> Iterable[date]:
        current = start_date
        while current <= end_date:
            yield current
            current += timedelta(days=1)

    @staticmethod
    def _trade_cal_params(
        trade_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Dict[str, Any]:
        if trade_date:
            return {'start_date': trade_date, 'end_date': trade_date}
        if start_date and end_date:
            return {'start_date': start_date, 'end_date': end_date}
        end = date.today()
        start = end - timedelta(days=30)
        return {'start_date': start.strftime('%Y%m%d'), 'end_date': end.strftime('%Y%m%d')}

    def _fetch_records(self, spec: TableSpec, params: Dict[str, Any], use_thread_client: bool = False) -> List[Dict[str, Any]]:
        unavailable_error = self._get_unavailable_api_error(spec.api_name)
        if unavailable_error is not None:
            raise unavailable_error
        last_error: Exception | None = None
        normal_failures = 0
        rate_limit_failures = 0
        source_concept_name = params.get('_concept_name')
        query_api_name = spec.api_name
        query_fields = spec.query_fields
        query_params = dict(params)
        if spec.api_name == 'dc_member':
            query_fields = DC_MEMBER_FIELDS
            query_params = {
                'ts_code': params.get('ts_code'),
                'trade_date': params.get('trade_date'),
            }
        while True:
            try:
                self._inc_stat('requests_started', 1)
                if self.verbose_request_logs:
                    self._log(
                        f"[request] start api={query_api_name} "
                        f"normal_failures={normal_failures}/{self.retry_max_attempts} "
                        f"rate_limit_failures={rate_limit_failures}/{RATE_LIMIT_MAX_RETRIES} params={query_params}"
                    )
                self.rate_limiter.acquire()
                api_rate_limiter = self.api_rate_limiters.get(query_api_name)
                if api_rate_limiter is not None:
                    api_rate_limiter.acquire()
                client = self.client_factory() if use_thread_client and self.client_factory else self.client
                request_started = time.monotonic()
                result = client.query(query_api_name, query_fields, params=query_params)
                if spec.api_name == 'dc_member':
                    records = [
                        self._sanitize_record(
                            {
                                'id': record.get('ts_code'),
                                'concept_name': source_concept_name,
                                'ts_code': record.get('con_code'),
                                'name': record.get('name'),
                            }
                        )
                        for record in result.to_dicts()
                    ]
                else:
                    records = [self._sanitize_record(self._map_record(spec, record)) for record in result.to_dicts()]
                self._inc_stat('requests_success', 1)
                self._inc_stat('records_fetched', len(records))
                if self.verbose_request_logs:
                    self._log(
                        f"[request] success api={query_api_name} rows={len(records)} "
                        f"duration={(time.monotonic() - request_started):.3f}s"
                    )
                return records
            except Exception as exc:
                last_error = exc
                self._inc_stat('requests_failed', 1)
                if self.verbose_request_logs:
                    self._log(f"[request] failed api={query_api_name} error={exc}")
                if self._is_upstream_internal_unavailable(exc):
                    self._remember_unavailable_api_error(query_api_name, exc)
                    break
                if self._is_rate_limit_error(exc):
                    rate_limit_failures += 1
                    if rate_limit_failures > RATE_LIMIT_MAX_RETRIES:
                        break
                    cooldown = max(RATE_LIMIT_COOLDOWN_SECONDS, self.retry_max_delay)
                    jitter = random.uniform(0.0, 5.0)
                    self._inc_stat('retries', 1)
                    self._log(
                        f"[rate-limit] api={query_api_name} hit={rate_limit_failures}/{RATE_LIMIT_MAX_RETRIES} "
                        f"sleep={(cooldown + jitter):.1f}s params={query_params}"
                    )
                    time.sleep(cooldown + jitter)
                    continue

                normal_failures += 1
                if normal_failures >= self.retry_max_attempts:
                    break
                backoff = min(self.retry_base_delay * (2 ** (normal_failures - 1)), self.retry_max_delay)
                jitter = random.uniform(0.0, self.retry_base_delay)
                self._inc_stat('retries', 1)
                if self.verbose_request_logs:
                    self._log(f"[request] retry api={query_api_name} sleep={(backoff + jitter):.3f}s")
                time.sleep(backoff + jitter)
        raise last_error

    def _fetch_records_batch(self, spec: TableSpec, params_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not params_list:
            return []
        if self.max_workers <= 1 or len(params_list) == 1:
            records: List[Dict[str, Any]] = []
            for params in params_list:
                records.extend(self._fetch_records(spec, params))
            return records

        records: List[Dict[str, Any]] = []
        api_limit = self.api_concurrency_limits.get(spec.api_name, self.max_workers)
        table_limit = self.table_concurrency_limits.get(spec.table_name, self.max_workers)
        hard_cap = HARD_API_CONCURRENCY_CAPS.get(spec.api_name, self.max_workers)
        worker_count = min(self.max_workers, api_limit, table_limit, hard_cap, len(params_list))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(self._fetch_records, spec, params, True) for params in params_list]
            for future in as_completed(futures):
                records.extend(future.result())
        return records

    def _fetch_and_upsert_records_batch(self, spec: TableSpec, params_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        total_inserted = 0
        aggregate_missing: set[str] = set()
        aggregate_nulls: Dict[str, int] = {}
        aggregate_metrics: Dict[str, Any] = {}

        def apply_records(records: List[Dict[str, Any]]) -> None:
            nonlocal total_inserted
            if not records:
                return
            batch_summary = self._upsert_records(spec, records)
            total_inserted += int(batch_summary['rows'])
            aggregate_missing.update(batch_summary['missing_fields'])
            for column, count in batch_summary['null_fields'].items():
                aggregate_nulls[column] = aggregate_nulls.get(column, 0) + int(count)
            self._merge_metrics_in_place(aggregate_metrics, batch_summary.get('metrics') or {})

        if self.max_workers <= 1 or len(params_list) == 1:
            for params in params_list:
                apply_records(self._fetch_records(spec, params))
            result = {
                'rows': total_inserted,
                'expected_fields': spec.columns,
                'missing_fields': sorted(aggregate_missing),
                'null_fields': aggregate_nulls,
            }
            if aggregate_metrics:
                result['metrics'] = aggregate_metrics
            return result

        api_limit = self.api_concurrency_limits.get(spec.api_name, self.max_workers)
        table_limit = self.table_concurrency_limits.get(spec.table_name, self.max_workers)
        hard_cap = HARD_API_CONCURRENCY_CAPS.get(spec.api_name, self.max_workers)
        worker_count = min(self.max_workers, api_limit, table_limit, hard_cap, len(params_list))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(self._fetch_records, spec, params, True) for params in params_list]
            for future in as_completed(futures):
                apply_records(future.result())
        result = {
            'rows': total_inserted,
            'expected_fields': spec.columns,
            'missing_fields': sorted(aggregate_missing),
            'null_fields': aggregate_nulls,
        }
        if aggregate_metrics:
            result['metrics'] = aggregate_metrics
        return result

    @staticmethod
    def _is_rate_limit_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return any(marker.lower() in message for marker in RATE_LIMIT_ERROR_MARKERS)

    @staticmethod
    def _is_upstream_internal_unavailable(exc: Exception) -> bool:
        message = str(exc).lower()
        return (
            'upstream' in message
            and ('127.0.0.1' in message or 'localhost' in message)
            and ('connection refused' in message or 'connectex' in message)
        )

    def _get_unavailable_api_error(self, api_name: str) -> Exception | None:
        with self._unavailable_api_lock:
            return self._unavailable_api_errors.get(api_name)

    def _remember_unavailable_api_error(self, api_name: str, exc: Exception) -> None:
        with self._unavailable_api_lock:
            self._unavailable_api_errors.setdefault(api_name, exc)

    def _upsert_records(self, spec: TableSpec, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        if spec.table_name == 't_cyq_perf':
            for record in records:
                c50 = record.get('cost_50')
                c85 = record.get('cost_85')
                concentration = None
                try:
                    if c50 is not None and c85 is not None:
                        denom = float(c85) + float(c50)
                        if denom != 0.0:
                            concentration = (float(c85) - float(c50)) / denom
                except Exception:
                    concentration = None
                record['concentration'] = round(concentration, 6) if concentration is not None else None
        if spec.table_name == 't_fin_indicator':
            for record in records:
                dta = record.get('debt_to_assets')
                if dta is not None:
                    try:
                        dta_float = float(dta)
                        if dta_float > 999999.9999 or dta_float < -999999.9999:
                            record['debt_to_assets'] = None
                    except (ValueError, TypeError):
                        record['debt_to_assets'] = None
        filtered_records, dropped = self._filter_invalid_records(spec, records)
        if dropped:
            self._inc_stat('records_dropped', dropped)
        rows = [tuple(record.get(column) for column in spec.columns) for record in filtered_records]
        inserted = self.database.upsert_many(spec.table_name, spec.columns, rows, spec.key_columns)
        self._inc_stat('rows_upserted', inserted)
        summary = self._validate_records(spec.columns, filtered_records, inserted)
        record_metrics = self._build_record_metrics(spec, filtered_records, dropped)
        if record_metrics:
            summary['metrics'] = record_metrics
        return summary

    @staticmethod
    def _merge_metrics_in_place(current: Dict[str, Any], incoming: Dict[str, Any]) -> None:
        if not incoming:
            return
        for key, value in incoming.items():
            if isinstance(value, dict):
                bucket = current.setdefault(key, {})
                if not isinstance(bucket, dict):
                    current[key] = dict(value)
                    continue
                for child_key, child_value in value.items():
                    bucket[child_key] = int(bucket.get(child_key, 0) or 0) + int(child_value or 0)
            else:
                current[key] = int(current.get(key, 0) or 0) + int(value or 0)

    def _merge_metrics(self, current: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(current)
        self._merge_metrics_in_place(merged, incoming)
        return merged

    @staticmethod
    def _build_record_metrics(spec: TableSpec, filtered_records: List[Dict[str, Any]], dropped: int) -> Dict[str, Any]:
        if spec.table_name != 't_cyq_perf':
            return {}
        coverage_by_trade_date: Dict[str, int] = {}
        for record in filtered_records:
            trade_date = str(record.get('trade_date') or '').strip()
            ts_code = str(record.get('ts_code') or '').strip()
            if not trade_date or not ts_code:
                continue
            coverage_by_trade_date[trade_date] = coverage_by_trade_date.get(trade_date, 0) + 1
        metrics: Dict[str, Any] = {
            'covered_rows': len(filtered_records),
            'dropped_rows': int(dropped or 0),
        }
        if coverage_by_trade_date:
            metrics['covered_by_trade_date'] = coverage_by_trade_date
        return metrics

    def _finalize_sync_metrics(self, spec: TableSpec, params_list: List[Dict[str, Any]], aggregate_metrics: Dict[str, Any]) -> Dict[str, Any]:
        if spec.table_name != 't_cyq_perf':
            return aggregate_metrics
        requested_trade_dates = sorted(
            {
                str(params.get('trade_date') or '').strip()
                for params in params_list
                if str(params.get('trade_date') or '').strip()
            }
        )
        if not requested_trade_dates:
            return aggregate_metrics
        placeholders = self._sql_placeholders(len(requested_trade_dates))
        sql = f'''
        SELECT trade_date, COUNT(DISTINCT ts_code) AS target_count
        FROM t_daily_bar
        WHERE trade_date IN ({placeholders})
        GROUP BY trade_date
        '''
        rows = self.database.fetch_all(sql, tuple(requested_trade_dates))
        target_by_trade_date = {}
        for row in rows:
            trade_date = row['trade_date'] if 'trade_date' in row.keys() else None
            if not trade_date:
                continue
            target_by_trade_date[str(trade_date)] = int(row['target_count'] or 0)
        covered_by_trade_date = {
            str(key): int(value or 0)
            for key, value in (aggregate_metrics.get('covered_by_trade_date') or {}).items()
        }
        per_trade_date: Dict[str, Dict[str, Any]] = {}
        target_total = 0
        covered_total = 0
        for trade_date in requested_trade_dates:
            target_count = int(target_by_trade_date.get(trade_date, 0) or 0)
            covered_count = int(covered_by_trade_date.get(trade_date, 0) or 0)
            missing_count = max(target_count - covered_count, 0)
            coverage_ratio = round((covered_count / target_count), 4) if target_count else 0.0
            per_trade_date[trade_date] = {
                'target_count': target_count,
                'covered_count': covered_count,
                'missing_count': missing_count,
                'coverage_ratio': coverage_ratio,
            }
            target_total += target_count
            covered_total += covered_count
        missing_total = max(target_total - covered_total, 0)
        finalized = {
            key: value
            for key, value in aggregate_metrics.items()
            if key != 'covered_by_trade_date'
        }
        finalized.update(
            {
                'target_total': target_total,
                'covered_total': covered_total,
                'missing_total': missing_total,
                'coverage_ratio': round((covered_total / target_total), 4) if target_total else 0.0,
                'per_trade_date': per_trade_date,
            }
        )
        return finalized

    def _filter_invalid_records(self, spec: TableSpec, records: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], int]:
        required_columns = REQUIRED_NOT_NULL_COLUMNS_BY_TABLE.get(spec.table_name, [])
        if not required_columns:
            return records, 0
        filtered: List[Dict[str, Any]] = []
        dropped = 0
        for record in records:
            invalid = False
            for column in required_columns:
                value = record.get(column)
                if value is None or value == '':
                    invalid = True
                    break
            if invalid:
                dropped += 1
                continue
            filtered.append(record)
        if dropped:
            self._log(
                f"[warn] drop_invalid_records table={spec.table_name} "
                f"dropped={dropped} reason=required_not_null_missing"
            )
        return filtered, dropped

    @staticmethod
    def _chunked(items: List[Dict[str, Any]], size: int) -> Iterable[List[Dict[str, Any]]]:
        for index in range(0, len(items), size):
            yield items[index:index + size]

    @staticmethod
    def _chunked_values(items: List[str], size: int) -> Iterable[List[str]]:
        for index in range(0, len(items), size):
            yield items[index:index + size]

    @staticmethod
    def _merge_table_summaries(target: Dict[str, Dict[str, Any]], updates: Dict[str, Dict[str, Any]]) -> None:
        for table_name, new_stats in updates.items():
            current = target.get(table_name)
            if current is None:
                target[table_name] = {
                    'rows': new_stats['rows'],
                    'expected_fields': list(new_stats['expected_fields']),
                    'missing_fields': list(new_stats['missing_fields']),
                    'null_fields': dict(new_stats['null_fields']),
                }
                continue
            current['rows'] += new_stats['rows']
            current['missing_fields'] = sorted(set(current['missing_fields']) | set(new_stats['missing_fields']))
            for column, count in new_stats['null_fields'].items():
                current['null_fields'][column] = current['null_fields'].get(column, 0) + count

    @staticmethod
    def _map_record(spec: TableSpec, record: Dict[str, Any]) -> Dict[str, Any]:
        mapped: Dict[str, Any] = {}
        for column in spec.columns:
            source_field = spec.source_map.get(column, column)
            mapped[column] = record.get(source_field)
        return mapped

    def _build_strategy_daily(self, trade_date: str | None = None) -> Dict[str, Any]:
        from backend.app.strategy import get_all_strategies
        strategies = get_all_strategies()
        if not strategies:
            return {'rows': 0, 'expected_fields': [], 'missing_fields': [], 'null_fields': {}}

        # For MVP, we presume the first strategy handles primary DB fields 
        # (like the original Vacuum strategy fields).
        # We merge all expected fields.
        expected_fields_set = {'ts_code', 'trade_date', 'pct_chg', 'turnover_rate', 'volume_ratio', 'winner_rate'}
        for strategy in strategies.values():
            expected_fields_set.update(strategy.expected_fields)
        expected_fields = list(expected_fields_set)
        
        # Ensure final_score falls back if missing
        if 'final_score' not in expected_fields:
            expected_fields.append('final_score')

        total_inserted = 0
        aggregate_nulls: Dict[str, int] = {}
        ts_codes = self._load_strategy_ts_codes(trade_date)
        total_batches = (len(ts_codes) + STRATEGY_TS_CODE_BATCH_SIZE - 1) // STRATEGY_TS_CODE_BATCH_SIZE

        # v1.1: 加载股票基本信息（名称用于ST检查）
        stock_names = self._load_stock_names()
        
        for batch_index, ts_code_batch in enumerate(self._chunked_values(ts_codes, STRATEGY_TS_CODE_BATCH_SIZE), start=1):
            rows = self._load_strategy_source_rows(ts_code_batch, trade_date)
            float_rows = self._load_strategy_float_rows(ts_code_batch, trade_date)
            float_map = self._build_float_risk_map(float_rows)
            
            # v1.1: 加载本批次近3日龙虎榜数据
            top_list_map = self._load_top_list_3d(ts_code_batch, trade_date)

            grouped_rows: Dict[str, List[Dict[str, Any]]] = {}
            for row in rows:
                grouped_rows.setdefault(row['ts_code'], []).append(row)

            payload = []
            strategy_records: List[Dict[str, Any]] = []
            for ts_code, series in grouped_rows.items():
                # v1.1: 获取股票名称和龙虎榜数据
                stock_name = stock_names.get(ts_code, '')
                top_list_data = top_list_map.get(ts_code, [])
                
                for index, row in enumerate(series):
                    if trade_date and row['trade_date'] != trade_date:
                        continue
                    
                    float_risk_7d = self._has_float_risk(float_map.get(ts_code, []), row['trade_date'])
                    
                    # Accumulate scores and fields from all registered strategies
                    total_score = 0
                    combined_extra_fields: Dict[str, Any] = {}
                    
                    for strategy in strategies.values():
                        # v1.1: 传入股票名称和龙虎榜数据
                        res = strategy.calculate(series, index, float_risk_7d, top_list_data, stock_name)
                        if res:
                            total_score += res.score
                            combined_extra_fields.update(res.extra_fields)
                    
                    # Base fields from source
                    row_dict = dict(row)
                    record = {
                        'ts_code': row['ts_code'],
                        'trade_date': row['trade_date'],
                        'pct_chg': row_dict.get('pct_chg'),
                        'turnover_rate': row_dict.get('turnover_rate'),
                        'volume_ratio': row_dict.get('volume_ratio'),
                        'winner_rate': row_dict.get('winner_rate'),
                        'float_risk_7d': float_risk_7d,
                    }
                    record.update(combined_extra_fields)
                    
                    # Ensure final score is present
                    record['final_score'] = record.get('final_score', total_score)
                    
                    # Fill missing expected fields with None
                    for f in expected_fields:
                        if f not in record:
                            record[f] = None
                            
                    payload_row = tuple(record.get(f) for f in expected_fields)
                    payload.append(payload_row)
                    strategy_records.append(record)

            inserted = self.database.upsert_many(
                't_strategy_daily',
                expected_fields,
                payload,
                ['ts_code', 'trade_date'],
            )
            total_inserted += inserted
            self._inc_stat('rows_upserted', inserted)
            chunk_nulls = self._validate_records(expected_fields, strategy_records, inserted)['null_fields']
            for column, count in chunk_nulls.items():
                aggregate_nulls[column] = aggregate_nulls.get(column, 0) + int(count)
            should_log_progress = (
                batch_index == 1
                or batch_index == total_batches
                or batch_index % PROGRESS_BATCH_LOG_EVERY == 0
            )
            if should_log_progress:
                self._log(
                    f"[progress] t_strategy_daily batch {batch_index}/{total_batches} "
                    f"ts_codes={len(ts_code_batch)} inserted={total_inserted}"
                )

        return {
            'rows': total_inserted,
            'expected_fields': expected_fields,
            'missing_fields': [],
            'null_fields': aggregate_nulls,
        }

    def _rebuild_strategy_for_share_float_impact_dates(self) -> Dict[str, Any]:
        trade_dates = self._resolve_share_float_impact_trade_dates()
        if not trade_dates:
            return {'rows': 0, 'expected_fields': [], 'missing_fields': [], 'null_fields': {}}
        total_rows = 0
        expected_fields: List[str] = []
        missing_fields: set[str] = set()
        aggregate_nulls: Dict[str, int] = {}
        for index, trade_date in enumerate(trade_dates, start=1):
            summary = self._build_strategy_daily(trade_date=trade_date)
            total_rows += int(summary.get('rows', 0) or 0)
            expected_fields = list(summary.get('expected_fields') or expected_fields)
            missing_fields.update(summary.get('missing_fields') or [])
            for column, count in (summary.get('null_fields') or {}).items():
                aggregate_nulls[column] = aggregate_nulls.get(column, 0) + int(count or 0)
            self._log(
                f"[progress] t_strategy_daily impact_date {index}/{len(trade_dates)} "
                f"current={trade_date} inserted={total_rows}"
            )
        return {
            'rows': total_rows,
            'expected_fields': expected_fields,
            'missing_fields': sorted(missing_fields),
            'null_fields': aggregate_nulls,
        }

    def _resolve_share_float_impact_trade_dates(self) -> List[str]:
        max_rows = self.database.fetch_all('SELECT MAX(trade_date) AS trade_date FROM t_daily_bar')
        max_trade_date = str(max_rows[0]['trade_date']) if max_rows and max_rows[0].get('trade_date') else ''
        if max_trade_date:
            try:
                max_dt = datetime.strptime(max_trade_date, '%Y%m%d').date()
                lower_float_date = (max_dt - timedelta(days=7)).strftime('%Y%m%d')
                upper_float_date = (max_dt + timedelta(days=7)).strftime('%Y%m%d')
                float_rows = self.database.fetch_all(
                    '''
                    SELECT DISTINCT float_date
                    FROM t_share_float
                    WHERE float_date IS NOT NULL
                      AND float_ratio IS NOT NULL
                      AND float_ratio > 5
                      AND float_date > %s
                      AND float_date <= %s
                    ORDER BY float_date
                    ''',
                    (lower_float_date, upper_float_date),
                )
                candidate_dates = self._expand_float_impact_dates([str(row['float_date']) for row in float_rows])
                if not candidate_dates:
                    return []
                min_candidate = min(candidate_dates)
                trade_rows = self.database.fetch_all(
                    '''
                    SELECT DISTINCT trade_date
                    FROM t_daily_bar
                    WHERE trade_date >= %s
                      AND trade_date <= %s
                    ORDER BY trade_date
                    ''',
                    (min_candidate, max_trade_date),
                )
                available = {str(row['trade_date']) for row in trade_rows if row.get('trade_date')}
                return [trade_date for trade_date in candidate_dates if trade_date in available]
            except Exception:
                return []

        float_rows = self.database.fetch_all(
            '''
            SELECT DISTINCT float_date
            FROM t_share_float
            WHERE float_date IS NOT NULL
              AND float_ratio IS NOT NULL
              AND float_ratio > 5
            ORDER BY float_date
            '''
        )
        return self._expand_float_impact_dates([str(row['float_date']) for row in float_rows])

    @staticmethod
    def _expand_float_impact_dates(float_dates: List[str]) -> List[str]:
        dates: set[str] = set()
        for float_date in float_dates:
            try:
                fd = datetime.strptime(float_date, '%Y%m%d').date()
            except Exception:
                continue
            for offset in range(1, 8):
                dates.add((fd - timedelta(days=offset)).strftime('%Y%m%d'))
        return sorted(dates)

    def _load_strategy_ts_codes(self, trade_date: str | None) -> List[str]:
        if trade_date:
            sql = 'SELECT DISTINCT ts_code FROM t_daily_bar WHERE trade_date <= %s ORDER BY ts_code'
            params: tuple[object, ...] = (trade_date,)
            rows = self.database.fetch_all(sql, params)
        else:
            rows = self.database.fetch_all('SELECT DISTINCT ts_code FROM t_daily_bar ORDER BY ts_code')
        return [str(row['ts_code']) for row in rows if row['ts_code']]

    def _load_strategy_source_rows(self, ts_codes: List[str], trade_date: str | None) -> List[Dict[str, Any]]:
        if not ts_codes:
            return []
        placeholders = self._sql_placeholders(len(ts_codes))
        sql = f'''
        SELECT d.ts_code, d.trade_date, d.open, d.high, d.low, d.close, d.vol, d.amount, d.pct_chg,
               a.adj_factor, b.turnover_rate, b.volume_ratio, c.winner_rate
        FROM t_daily_bar d
        LEFT JOIN t_adj_factor a ON a.ts_code = d.ts_code AND a.trade_date = d.trade_date
        LEFT JOIN t_daily_basic b ON b.ts_code = d.ts_code AND b.trade_date = d.trade_date
        LEFT JOIN t_cyq_perf c ON c.ts_code = d.ts_code AND c.trade_date = d.trade_date
        WHERE d.ts_code IN ({placeholders})
        '''
        params: List[object] = list(ts_codes)
        if trade_date:
            try:
                target_dt = datetime.strptime(trade_date, '%Y%m%d').date()
                lookback_start = (target_dt - timedelta(days=400)).strftime('%Y%m%d')
            except Exception:
                lookback_start = trade_date
            sql += ' AND d.trade_date <= %s AND d.trade_date >= %s'
            params.extend([trade_date, lookback_start])
        sql += ' ORDER BY d.ts_code, d.trade_date'
        return self.database.fetch_all(sql, tuple(params))

    def _load_strategy_float_rows(self, ts_codes: List[str], trade_date: str | None) -> List[Dict[str, Any]]:
        if not ts_codes:
            return []
        placeholders = self._sql_placeholders(len(ts_codes))
        sql = f'''
        SELECT ts_code, float_date, float_ratio
        FROM t_share_float
        WHERE ts_code IN ({placeholders})
          AND float_date IS NOT NULL
          AND float_ratio IS NOT NULL
        '''
        params: List[object] = list(ts_codes)
        if trade_date:
            try:
                td = datetime.strptime(trade_date, '%Y%m%d').date()
                end_date = (td + timedelta(days=7)).strftime('%Y%m%d')
            except Exception:
                end_date = trade_date
            sql += ' AND float_date > %s AND float_date <= %s'
            params.extend([trade_date, end_date])
        return self.database.fetch_all(sql, tuple(params))

    def _sql_placeholders(self, count: int) -> str:
        return ', '.join(['%s'] * count)

    @staticmethod
    def _compute_adjusted_ma(series: List[Dict[str, Any]], index: int, window: int) -> float | None:
        if index + 1 < window:
            return None
        current_adj = series[index].get('adj_factor')
        if current_adj in (None, 0):
            return None
        adjusted_prices: List[float] = []
        for item in series[index - window + 1:index + 1]:
            close = item.get('close')
            adj_factor = item.get('adj_factor')
            if close is None or adj_factor in (None, 0):
                return None
            adjusted_prices.append(float(close) * float(adj_factor) / float(current_adj))
        return round(sum(adjusted_prices) / window, 4)

    @staticmethod
    def _build_float_risk_map(rows: List[Dict[str, Any]]) -> Dict[str, List[tuple[date, float]]]:
        result: Dict[str, List[tuple[date, float]]] = {}
        for row in rows:
            try:
                float_date = datetime.strptime(row['float_date'], '%Y%m%d').date()
            except Exception:
                continue
            result.setdefault(row['ts_code'], []).append((float_date, float(row['float_ratio'])))
        return result

    @staticmethod
    def _has_float_risk(events: List[tuple[date, float]], trade_date_str: str) -> int:
        try:
            trade_date = datetime.strptime(trade_date_str, '%Y%m%d').date()
        except Exception:
            return 0
        for float_date, float_ratio in events:
            day_gap = (float_date - trade_date).days
            if 1 <= day_gap <= 7 and float_ratio > 5:
                return 1
        return 0

    @staticmethod
    def _sanitize_value(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, float) and math.isnan(value):
            return None
        if hasattr(value, 'item'):
            try:
                value = value.item()
            except Exception:
                return value
            if isinstance(value, float) and math.isnan(value):
                return None
        return value

    @classmethod
    def _sanitize_record(cls, record: Dict[str, Any]) -> Dict[str, Any]:
        return {key: cls._sanitize_value(value) for key, value in record.items()}

    @staticmethod
    def _validate_records(columns: List[str], records: List[Dict[str, Any]], inserted: int) -> Dict[str, Any]:
        missing_fields = sorted({column for record in records for column in columns if column not in record})
        null_fields: Dict[str, int] = {}
        for column in columns:
            null_count = sum(1 for record in records if record.get(column) is None)
            if null_count:
                null_fields[column] = null_count
        return {
            'rows': inserted,
            'expected_fields': columns,
            'missing_fields': missing_fields,
            'null_fields': null_fields,
        }

    def _load_stock_names(self) -> Dict[str, str]:
        """
        v1.1: 加载所有股票代码和名称映射（用于ST检查）
        """
        sql = 'SELECT ts_code, name FROM t_stock_basic WHERE name IS NOT NULL'
        rows = self.database.fetch_all(sql)
        return {row['ts_code']: (row['name'] or '') for row in rows}

    def _load_top_list_3d(self, ts_codes: List[str], trade_date: str | None) -> Dict[str, List[Dict[str, Any]]]:
        """
        v1.1: 加载近3日龙虎榜数据（用于加分判断）
        返回: {ts_code: [{'trade_date': 'xxx', 'net': 1000000}, ...]}
        """
        if not ts_codes or not trade_date:
            return {}
        
        placeholders = ', '.join(['%s'] * len(ts_codes))
        
        try:
            target_dt = datetime.strptime(trade_date, '%Y%m%d').date()
            lookback_start = (target_dt - timedelta(days=3)).strftime('%Y%m%d')
        except Exception:
            return {}
        
        sql = f'''
        SELECT ts_code, trade_date, net
        FROM t_top_list
        WHERE ts_code IN ({placeholders})
          AND trade_date <= %s
          AND trade_date >= %s
        '''
        params = list(ts_codes) + [trade_date, lookback_start]
        
        rows = self.database.fetch_all(sql, tuple(params))
        
        result: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            ts_code = row['ts_code']
            if ts_code not in result:
                result[ts_code] = []
            result[ts_code].append({
                'trade_date': row['trade_date'],
                'net': float(row['net']) if row['net'] is not None else 0
            })
        
        return result


# ---------------------------------------------------------------------------
# Module-level summary printer  (imported and called by job scripts)
# ---------------------------------------------------------------------------

def print_sync_summary(summary: Dict[str, Dict[str, Any]], job_name: str = '') -> None:
    """Print a structured field-level update summary at the end of a sync job.

    For every table in *summary* we compute, for each expected field:
      - total_values  = rows written to DB
      - null_count    = how many of those rows have NULL for that field
      - ok_count      = total_values - null_count
      - ok_pct        = ok_count / total_values * 100

    A global totals line is printed at the end so operators can immediately
    spot silent failures such as volume_ratio being wiped after a full daily sync.
    """
    SEP = '-' * 72
    header = f"[summary] job={job_name}" if job_name else "[summary]"
    print(SEP)
    print(header)
    print(SEP)

    global_total_cells = 0
    global_ok_cells = 0
    warn_fields: List[str] = []          # fields with ok_pct < 80 %

    for table_name, stats in summary.items():
        rows = int(stats.get('rows') or 0)
        expected_fields: List[str] = list(stats.get('expected_fields') or [])
        null_fields: Dict[str, int] = dict(stats.get('null_fields') or {})
        missing_fields: List[str] = list(stats.get('missing_fields') or [])

        # Skip sentinel entries (no expected_fields means the table wasn't really tracked)
        if not expected_fields or rows == 0:
            print(f"  {table_name}: rows=0  (skipped or no data)")
            continue

        num_fields = len(expected_fields)
        total_cells = rows * num_fields
        null_cells = sum(int(null_fields.get(f, 0)) for f in expected_fields)
        ok_cells = total_cells - null_cells
        ok_pct = ok_cells / total_cells * 100.0 if total_cells else 100.0

        global_total_cells += total_cells
        global_ok_cells += ok_cells

        status_icon = '[OK]' if ok_pct >= 95.0 else ('[!!]' if ok_pct >= 70.0 else '[XX]')
        print(
            f"  {status_icon} {table_name}: "
            f"rows={rows}  fields={num_fields}  "
            f"ok={ok_cells}/{total_cells}  ({ok_pct:.1f}%)"
        )

        # Per-field detail for any field that has NULLs
        field_lines: List[str] = []
        for field in expected_fields:
            nc = int(null_fields.get(field, 0))
            if nc == 0:
                continue
            field_ok = rows - nc
            field_pct = field_ok / rows * 100.0
            icon = '[!!]' if field_pct >= 70.0 else '[XX]'
            field_lines.append(
                f"        {icon} {field}: ok={field_ok}/{rows} ({field_pct:.1f}%)"
            )
            if field_pct < 80.0:
                warn_fields.append(f"{table_name}.{field}({field_pct:.1f}%)")
        if field_lines:
            print('\n'.join(field_lines))

        if missing_fields:
            print(f"        [missing_fields] {missing_fields}")

        # Extra cyq_perf coverage metrics if present
        metrics = stats.get('metrics') or {}
        if metrics and 'coverage_ratio' in metrics:
            cov_pct = float(metrics['coverage_ratio']) * 100.0
            covered = int(metrics.get('covered_total') or 0)
            target = int(metrics.get('target_total') or 0)
            missing = int(metrics.get('missing_total') or 0)
            print(
                f"        [coverage] covered={covered}/{target}  "
                f"missing={missing}  ratio={cov_pct:.1f}%"
            )

    # --- Global totals ---
    print(SEP)
    global_ok_pct = global_ok_cells / global_total_cells * 100.0 if global_total_cells else 100.0
    global_icon = '[OK]' if global_ok_pct >= 95.0 else ('[!!]' if global_ok_pct >= 70.0 else '[XX]')
    print(
        f"  {global_icon} TOTAL: tables={len(summary)}  "
        f"cells={global_ok_cells}/{global_total_cells}  "
        f"ok_rate={global_ok_pct:.1f}%"
    )
    if warn_fields:
        print(f"  [warn] low-fill fields: {', '.join(warn_fields)}")
    print(SEP)
