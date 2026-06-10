from __future__ import annotations

import pytest

from backend.app.ingest import DataIngestionService, FEATURED_DATE_SUPPLEMENTAL_SPECS


class _FakeDatabase:
    def fetch_all(self, sql, params=()):
        return []


def test_featured_sync_continues_when_cyq_upstream_internal_service_is_down(monkeypatch):
    service = DataIngestionService(client=object(), database=_FakeDatabase())
    error = Exception(
        '上游调用失败: upstream: http: Post "http://127.0.0.1:9933": '
        'dial tcp 127.0.0.1:9933: connect: connection refused'
    )

    monkeypatch.setattr(service, "_resolve_featured_trade_dates", lambda trade_date: [trade_date])
    monkeypatch.setattr(service, "_sync_date_supplemental_tables", lambda *args, **kwargs: (_ for _ in ()).throw(error))

    summary = service.run_featured_sync(trade_date="20260604")

    assert summary["t_cyq_perf"]["rows"] == 0
    assert summary["t_cyq_perf"]["warning"] == str(error)


def test_featured_sync_still_raises_unrelated_cyq_errors(monkeypatch):
    service = DataIngestionService(client=object(), database=_FakeDatabase())

    monkeypatch.setattr(service, "_resolve_featured_trade_dates", lambda trade_date: [trade_date])
    monkeypatch.setattr(
        service,
        "_sync_date_supplemental_tables",
        lambda *args, **kwargs: (_ for _ in ()).throw(Exception("您的token不对，请确认。")),
    )

    with pytest.raises(Exception, match="token"):
        service.run_featured_sync(trade_date="20260604")


@pytest.mark.parametrize("api_name", ["cyq_perf", "dc_member", "share_float", "fina_indicator"])
def test_internal_upstream_connection_refusal_is_not_retried(api_name):
    class _FailingClient:
        def __init__(self):
            self.calls = 0

        def query(self, api_name, fields, params=None):
            self.calls += 1
            raise Exception(
                '上游调用失败: upstream: http: Post "http://127.0.0.1:9933": '
                'dial tcp 127.0.0.1:9933: connect: connection refused'
            )

    client = _FailingClient()
    service = DataIngestionService(
        client=client,
        database=_FakeDatabase(),
        retry_max_attempts=5,
        retry_base_delay=0.01,
        retry_max_delay=0.01,
    )
    base_spec = FEATURED_DATE_SUPPLEMENTAL_SPECS[0]
    spec = type(
        "Spec",
        (),
        {
            "api_name": api_name,
            "table_name": f"t_{api_name}",
            "query_fields": base_spec.query_fields,
            "columns": base_spec.columns,
            "source_map": base_spec.source_map,
        },
    )()

    for _ in range(2):
        with pytest.raises(Exception, match="connection refused"):
            service._fetch_records(spec, {"trade_date": "20260604"})

    assert client.calls == 1


def test_internal_upstream_connection_refusal_is_not_retried_for_untyped_queries():
    class _FailingClient:
        def __init__(self):
            self.calls = 0

        def query(self, api_name, fields, params=None):
            self.calls += 1
            raise Exception(
                '上游调用失败: upstream: http: Post "http://127.0.0.1:9933": '
                'dial tcp 127.0.0.1:9933: connect: connection refused'
            )

    client = _FailingClient()
    service = DataIngestionService(
        client=client,
        database=_FakeDatabase(),
        retry_max_attempts=5,
        retry_base_delay=0.01,
        retry_max_delay=0.01,
    )

    for _ in range(2):
        with pytest.raises(Exception, match="connection refused"):
            service._query_any_fields("dc_index", {"idx_type": "概念板块"})

    assert client.calls == 1
