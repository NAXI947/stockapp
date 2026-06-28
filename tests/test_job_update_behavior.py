from __future__ import annotations

from datetime import date

import pytest

from backend.app.ingest import (
    COMMON_DATE_SUPPLEMENTAL_SPECS,
    DataIngestionService,
    FULL_MARKET_SUPPLEMENTAL_SPECS,
    TableSpec,
)
from backend.app.job_checkpoint import JobCheckpointStore
from backend.app.job_runner import JOB_DEFINITIONS


class _FakeDatabase:
    def __init__(self, rows_by_sql=None):
        self.rows_by_sql = rows_by_sql or {}
        self.calls = []

    def fetch_all(self, sql, params=()):
        self.calls.append((sql, tuple(params)))
        for marker, rows in self.rows_by_sql.items():
            if marker in sql:
                return rows
        return []

    def upsert_many(self, table, columns, rows, key_columns):
        materialized = list(rows)
        self.calls.append((f"UPSERT {table}", tuple(materialized)))
        return len(materialized)


class _FakeCheckpointStore:
    def __init__(self, resume_starts=None):
        self.resume_starts = resume_starts or {}
        self.progress = []
        self.success = []
        self.failed = []

    def start_incremental_run(self, job_name, target_range, requested_start, requested_end=None):
        return self.resume_starts.get(target_range, requested_start)

    def mark_progress(self, job_name, target_range, trade_date):
        self.progress.append((target_range, trade_date))

    def mark_success(self, job_name, target_range):
        self.success.append(target_range)

    def mark_failed(self, job_name, target_range):
        self.failed.append(target_range)


def _share_float_spec():
    return next(spec for spec in FULL_MARKET_SUPPLEMENTAL_SPECS if spec.api_name == "share_float")


def test_manual_daily_uses_latest_strategy_rebuild():
    daily_steps = JOB_DEFINITIONS["daily"]["steps"]

    assert daily_steps[2] == ("job_daily_strategy.py", ["--latest-only"])


def test_data_update_no_longer_fetches_shareholder_counts():
    api_names = {spec.api_name for spec in COMMON_DATE_SUPPLEMENTAL_SPECS}

    assert "stk_holdernumber" not in api_names


def test_manual_update_date_job_passes_date_to_daily_steps():
    update_steps = JOB_DEFINITIONS["update_date"]["steps"]

    assert update_steps == [
        ("job_daily_common.py", ["{date}", "--light"]),
        ("job_daily_featured.py", ["{date}"]),
        ("job_daily_strategy.py", ["{date}"]),
    ]


def test_daily_basic_fills_missing_volume_ratio_from_daily_bar():
    database = _FakeDatabase(
        {
            "FROM t_daily_bar": [
                {"ts_code": "000001.SZ", "trade_date": "20260617", "vol": 100.0},
                {"ts_code": "000001.SZ", "trade_date": "20260618", "vol": 100.0},
                {"ts_code": "000001.SZ", "trade_date": "20260619", "vol": 100.0},
                {"ts_code": "000001.SZ", "trade_date": "20260622", "vol": 100.0},
                {"ts_code": "000001.SZ", "trade_date": "20260623", "vol": 100.0},
                {"ts_code": "000001.SZ", "trade_date": "20260624", "vol": 250.0},
            ]
        }
    )
    service = DataIngestionService(client=object(), database=database)
    spec = TableSpec(
        "daily_basic",
        "t_daily_basic",
        ["ts_code", "trade_date", "turnover_rate", "volume_ratio", "circ_mv"],
        ["ts_code", "trade_date"],
    )

    summary = service._upsert_records(
        spec,
        [
            {
                "ts_code": "000001.SZ",
                "trade_date": "20260624",
                "turnover_rate": 3.1,
                "volume_ratio": None,
                "circ_mv": 1000.0,
            }
        ],
    )

    upsert_call = next(call for call in database.calls if call[0] == "UPSERT t_daily_basic")
    assert upsert_call[1][0] == ("000001.SZ", "20260624", 3.1, 2.5, 1000.0)
    assert summary["null_fields"] == {}


def test_strategy_volume_ratio_falls_back_to_daily_bar_series():
    series = [
        {"trade_date": "20260617", "vol": 100.0},
        {"trade_date": "20260618", "vol": 100.0},
        {"trade_date": "20260619", "vol": 100.0},
        {"trade_date": "20260622", "vol": 100.0},
        {"trade_date": "20260623", "vol": 100.0},
        {"trade_date": "20260624", "vol": 250.0},
    ]

    assert DataIngestionService._compute_volume_ratio(series, 5) == 2.5


def test_block_trade_fills_missing_premium_from_daily_close():
    database = _FakeDatabase(
        {
            "FROM t_daily_bar": [
                {"ts_code": "000001.SZ", "trade_date": "20260624", "close": 10.0},
            ]
        }
    )
    service = DataIngestionService(client=object(), database=database)
    spec = TableSpec(
        "block_trade",
        "t_block_trade",
        ["ts_code", "trade_date", "price", "vol", "amount", "premium"],
        ["ts_code", "trade_date", "price", "vol"],
    )

    summary = service._upsert_records(
        spec,
        [
            {
                "ts_code": "000001.SZ",
                "trade_date": "20260624",
                "price": 10.5,
                "vol": 20.0,
                "amount": 210.0,
                "premium": None,
            }
        ],
    )

    upsert_call = next(call for call in database.calls if call[0] == "UPSERT t_block_trade")
    assert upsert_call[1][0] == ("000001.SZ", "20260624", 10.5, 20.0, 210.0, 5.0)
    assert summary["null_fields"] == {}


def test_monthly_sync_rebuilds_strategy_for_share_float_impact_dates(monkeypatch):
    service = DataIngestionService(client=object(), database=_FakeDatabase())
    calls = []

    def fake_find_spec(api_name, specs):
        return type("Spec", (), {"api_name": api_name, "table_name": f"t_{api_name}"})()

    monkeypatch.setattr(service, "_find_spec", fake_find_spec)
    monkeypatch.setattr(service, "_build_query_param_list", lambda api_name, trade_dates: [{"api_name": api_name}])
    monkeypatch.setattr(service, "_sync_spec_in_batches", lambda spec, params: {"rows": 1})
    monkeypatch.setattr(service, "_sync_share_float_incremental", lambda spec, **kwargs: {"rows": 1})
    monkeypatch.setattr(service, "_rebuild_strategy_for_share_float_impact_dates", lambda: calls.append("rebuild") or {"rows": 2})

    summary = service.run_monthly_sync()

    assert calls == ["rebuild"]
    assert summary["t_strategy_daily"]["rows"] == 2


@pytest.mark.parametrize("failed_api", ["dc_member", "share_float"])
def test_monthly_sync_preserves_existing_data_when_upstream_internal_service_is_down(monkeypatch, failed_api):
    service = DataIngestionService(client=object(), database=_FakeDatabase())
    error = Exception(
        '上游调用失败: upstream: http: Post "http://127.0.0.1:9933": '
        'dial tcp 127.0.0.1:9933: connect: connection refused'
    )
    synced_apis = []

    def fake_find_spec(api_name, specs):
        return type(
            "Spec",
            (),
            {
                "api_name": api_name,
                "table_name": {
                    "dc_member": "t_concept_detail",
                    "share_float": "t_share_float",
                }[api_name],
                "columns": ["ts_code"],
            },
        )()

    def fake_sync(spec, params=None, **kwargs):
        synced_apis.append(spec.api_name)
        if spec.api_name == failed_api:
            raise error
        return {"rows": 1}

    monkeypatch.setattr(service, "_find_spec", fake_find_spec)
    monkeypatch.setattr(service, "_build_query_param_list", lambda api_name, trade_dates: [{"api_name": api_name}])
    monkeypatch.setattr(service, "_sync_spec_in_batches", fake_sync)
    monkeypatch.setattr(service, "_sync_share_float_incremental", fake_sync)
    monkeypatch.setattr(
        service,
        "_rebuild_strategy_for_share_float_impact_dates",
        lambda: {"rows": 2},
    )

    summary = service.run_monthly_sync()

    failed_table = fake_find_spec(failed_api, []).table_name
    assert synced_apis == ["dc_member", "share_float"]
    assert summary[failed_table]["rows"] == 0
    assert summary[failed_table]["warning"] == str(error)
    assert summary["t_strategy_daily"]["rows"] == 2


def test_quarterly_sync_preserves_financial_data_when_upstream_internal_service_is_down(monkeypatch):
    service = DataIngestionService(client=object(), database=_FakeDatabase())
    error = Exception(
        '上游调用失败: upstream: http: Post "http://localhost:9933": '
        'dial tcp 127.0.0.1:9933: connect: connection refused'
    )
    spec = type(
        "Spec",
        (),
        {
            "api_name": "fina_indicator",
            "table_name": "t_fin_indicator",
            "columns": ["ts_code"],
        },
    )()

    monkeypatch.setattr(service, "_find_spec", lambda api_name, specs: spec)
    monkeypatch.setattr(service, "_build_query_param_list", lambda api_name, trade_dates: [{"ts_code": "000001.SZ"}])
    monkeypatch.setattr(
        service,
        "_sync_spec_in_batches",
        lambda spec, params: (_ for _ in ()).throw(error),
    )

    summary = service.run_quarterly_sync()

    assert summary["t_fin_indicator"]["rows"] == 0
    assert summary["t_fin_indicator"]["warning"] == str(error)


def test_share_float_impact_dates_are_seven_day_windows():
    database = _FakeDatabase(
        {
            "SELECT DISTINCT float_date": [
                {"float_date": "20260510"},
                {"float_date": "20260512"},
            ]
        }
    )
    service = DataIngestionService(client=object(), database=database)

    dates = service._resolve_share_float_impact_trade_dates()

    assert dates == [
        "20260503",
        "20260504",
        "20260505",
        "20260506",
        "20260507",
        "20260508",
        "20260509",
        "20260510",
        "20260511",
    ]


def test_incremental_share_float_queries_date_units_without_stock_scan(monkeypatch):
    database = _FakeDatabase(
        {
            "MAX(trade_date)": [{"trade_date": "20260604"}],
        }
    )
    checkpoints = _FakeCheckpointStore(
        {
            "share_float:ann_date": "20260606",
            "share_float:float_date": "20260610",
        }
    )
    service = DataIngestionService(client=object(), database=database, max_workers=1)
    requested_params = []

    def fake_fetch(spec, params, use_thread_client=False):
        requested_params.append(dict(params))
        return [
            {
                "ts_code": "000001.SZ",
                "ann_date": params.get("ann_date", "20260601"),
                "float_date": params.get("float_date", "20260620"),
                "float_share": 100.0,
                "float_ratio": 1.0,
                "holder_name": "holder",
                "share_type": "type",
            }
        ]

    monkeypatch.setattr(service, "_fetch_records", fake_fetch)

    summary = service._sync_share_float_incremental(
        _share_float_spec(),
        checkpoint_store=checkpoints,
        run_date=date(2026, 6, 7),
        future_days=4,
    )

    assert requested_params == [
        {"ann_date": "20260606"},
        {"ann_date": "20260607"},
        {"float_date": "20260610"},
        {"float_date": "20260611"},
    ]
    assert all("ts_code" not in params for params in requested_params)
    assert checkpoints.progress == [
        ("share_float:ann_date", "20260606"),
        ("share_float:ann_date", "20260607"),
        ("share_float:float_date", "20260610"),
        ("share_float:float_date", "20260611"),
    ]
    assert checkpoints.success == ["share_float:ann_date", "share_float:float_date"]
    assert summary["rows"] == 4


def test_incremental_share_float_marks_failed_date_and_does_not_advance(monkeypatch):
    database = _FakeDatabase(
        {
            "MAX(trade_date)": [{"trade_date": "20260604"}],
        }
    )
    checkpoints = _FakeCheckpointStore({"share_float:ann_date": "20260606"})
    service = DataIngestionService(client=object(), database=database, max_workers=1)
    requested_params = []

    def fake_fetch(spec, params, use_thread_client=False):
        requested_params.append(dict(params))
        if params == {"ann_date": "20260607"}:
            raise TimeoutError("upstream timed out")
        return []

    monkeypatch.setattr(service, "_fetch_records", fake_fetch)

    with pytest.raises(TimeoutError, match="timed out"):
        service._sync_share_float_incremental(
            _share_float_spec(),
            checkpoint_store=checkpoints,
            run_date=date(2026, 6, 7),
            future_days=4,
        )

    assert requested_params == [
        {"ann_date": "20260606"},
        {"ann_date": "20260607"},
    ]
    assert checkpoints.progress == [("share_float:ann_date", "20260606")]
    assert checkpoints.failed == ["share_float:ann_date"]
    assert checkpoints.success == []


def test_capped_share_float_date_is_refetched_by_stock(monkeypatch):
    database = _FakeDatabase(
        {
            "SELECT ts_code FROM t_stock_basic": [
                {"ts_code": "600001.SH"},
                {"ts_code": "600002.SH"},
            ],
        }
    )
    service = DataIngestionService(client=object(), database=database, max_workers=1)
    requested_params = []
    capped_records = [
        {
            "ts_code": f"{index:06d}.SZ",
            "ann_date": "20260607",
            "float_date": "20260620",
            "float_share": 100.0,
            "float_ratio": 1.0,
            "holder_name": f"holder-{index}",
            "share_type": "type",
        }
        for index in range(6000)
    ]

    def fake_fetch(spec, params, use_thread_client=False):
        requested_params.append(dict(params))
        if "ts_code" not in params:
            return capped_records
        return [
            {
                "ts_code": params["ts_code"],
                "ann_date": params["ann_date"],
                "float_date": "20260620",
                "float_share": 100.0,
                "float_ratio": 1.0,
                "holder_name": params["ts_code"],
                "share_type": "type",
            }
        ]

    monkeypatch.setattr(service, "_fetch_records", fake_fetch)

    records = service._fetch_share_float_date_records(
        _share_float_spec(),
        "ann_date",
        "20260607",
    )

    assert requested_params == [
        {"ann_date": "20260607"},
        {"ann_date": "20260607", "ts_code": "600001.SH"},
        {"ann_date": "20260607", "ts_code": "600002.SH"},
    ]
    assert [record["ts_code"] for record in records[-2:]] == ["600001.SH", "600002.SH"]


def test_capped_share_float_date_refetches_only_missing_stocks(monkeypatch):
    database = _FakeDatabase(
        {
            "SELECT ts_code FROM t_stock_basic": [
                {"ts_code": "000001.SZ"},
                {"ts_code": "000002.SZ"},
                {"ts_code": "000003.SZ"},
            ],
        }
    )
    service = DataIngestionService(client=object(), database=database, max_workers=1)
    requested_params = []
    capped_records = [
        {
            "ts_code": "000001.SZ" if index % 2 == 0 else "000002.SZ",
            "ann_date": "20260607",
            "float_date": "20260620",
            "float_share": 100.0,
            "float_ratio": 1.0,
            "holder_name": f"holder-{index}",
            "share_type": "type",
        }
        for index in range(6000)
    ]

    def fake_fetch(spec, params, use_thread_client=False):
        requested_params.append(dict(params))
        if "ts_code" not in params:
            return capped_records
        return [
            {
                "ts_code": params["ts_code"],
                "ann_date": params["ann_date"],
                "float_date": "20260620",
                "float_share": 100.0,
                "float_ratio": 1.0,
                "holder_name": params["ts_code"],
                "share_type": "type",
            }
        ]

    monkeypatch.setattr(service, "_fetch_records", fake_fetch)

    records = service._fetch_share_float_date_records(
        _share_float_spec(),
        "ann_date",
        "20260607",
    )

    assert requested_params == [
        {"ann_date": "20260607"},
        {"ann_date": "20260607", "ts_code": "000003.SZ"},
    ]
    assert len(records) == 6001
    assert records[-1]["ts_code"] == "000003.SZ"


class _CheckpointDatabase:
    driver = "sqlite"

    def __init__(self, row):
        self.row = row
        self.executed = []

    def fetch_all(self, sql, params=()):
        return [self.row] if self.row else []

    def execute(self, sql, params=()):
        self.executed.append((sql, tuple(params)))


def test_incremental_checkpoint_replays_lookback_after_success():
    store = JobCheckpointStore(
        _CheckpointDatabase(
            {
                "last_completed_trade_date": "20260607",
                "status": "success",
            }
        )
    )

    assert store.get_incremental_start("job_monthly", "share_float:ann_date", "20260508") == "20260508"


def test_incremental_checkpoint_skips_completed_horizon_but_replays_when_horizon_advances():
    store = JobCheckpointStore(
        _CheckpointDatabase(
            {
                "last_completed_trade_date": "20260607",
                "status": "success",
            }
        )
    )

    assert (
        store.get_incremental_start(
            "job_monthly",
            "share_float:ann_date",
            "20260508",
            requested_end="20260607",
        )
        == "20260608"
    )
    assert (
        store.get_incremental_start(
            "job_monthly",
            "share_float:ann_date",
            "20260607",
            requested_end="20260707",
        )
        == "20260607"
    )


def test_incremental_checkpoint_resumes_after_last_completed_date_when_failed():
    database = _CheckpointDatabase(
        {
            "id": 7,
            "last_completed_trade_date": "20260605",
            "status": "failed",
        }
    )
    store = JobCheckpointStore(database)

    assert store.get_incremental_start("job_monthly", "share_float:ann_date", "20260508") == "20260606"
    assert store.start_incremental_run("job_monthly", "share_float:ann_date", "20260508") == "20260606"
    assert database.executed[-1][1] == ("running", 7)
