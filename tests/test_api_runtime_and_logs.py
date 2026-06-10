from __future__ import annotations

import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

os.environ.setdefault("API_AUTH_ENABLED", "false")

from fastapi.testclient import TestClient

from backend.core.deps import get_database
from backend.main import create_app


@contextmanager
def api_client():
    app = create_app()
    app.dependency_overrides[get_database] = lambda: object()
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


class RuntimeAndJobLogApiTest(unittest.TestCase):
    def test_get_job_logs_summary_clamps_query_params(self) -> None:
        mocked_report = {
            "log_dir": "/tmp/logs",
            "generated_at": "2026-03-11T00:00:00+00:00",
            "window_days": 90,
            "job_name": "job_history",
            "latest_run": None,
            "recent_failures": [],
            "stage_summary": [],
            "status_counts": {"failed": 1},
            "latest_run_tables": [],
        }

        with patch("backend.app.api.build_job_log_report", return_value=mocked_report) as report_mock:
            with api_client() as client:
                response = client.get(
                    "/api/v1/job/logs/summary",
                    params={"days": 999, "limit": 0, "job_name": "job_history"},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["window_days"], 90)
        report_mock.assert_called_once_with(days=90, limit=1, job_name="job_history")

    def test_get_runtime_config_returns_jobs_payload(self) -> None:
        jobs_payload = {
            "max_workers": 20,
            "qps_limit": 3.5,
            "api_qps_limits": {"daily": 2.0},
        }

        with patch("backend.app.api.get_runtime_jobs_config", return_value=jobs_payload) as runtime_mock:
            with api_client() as client:
                response = client.get("/api/v1/runtime-config")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["jobs"], jobs_payload)
        runtime_mock.assert_called_once()

    def test_put_runtime_config_returns_updated_jobs_payload(self) -> None:
        updated_jobs = {
            "max_workers": 50,
            "qps_limit": 4.0,
            "verbose_request_logs": True,
        }

        with patch("backend.app.api.set_runtime_jobs_config", return_value=updated_jobs) as runtime_mock:
            with api_client() as client:
                response = client.put(
                    "/api/v1/runtime-config",
                    json={"jobs": {"max_workers": 50, "qps_limit": 4.0, "verbose_request_logs": True}},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["jobs"], updated_jobs)
        runtime_mock.assert_called_once()

    def test_put_runtime_config_maps_value_error_to_bad_request(self) -> None:
        with patch("backend.app.api.set_runtime_jobs_config", side_effect=ValueError("jobs.max_workers invalid")):
            with api_client() as client:
                response = client.put("/api/v1/runtime-config", json={"jobs": {"max_workers": 999}})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "jobs.max_workers invalid")

    def test_get_job_runs_clamps_limit_and_status(self) -> None:
        mocked_payload = {
            "log_dir": "/tmp/logs",
            "generated_at": "2026-03-11T00:00:00+00:00",
            "window_days": 90,
            "job_name": "job_history",
            "status": "failed",
            "items": [],
            "total": 0,
        }

        with patch("backend.app.api.list_job_runs", return_value=mocked_payload) as runs_mock:
            with api_client() as client:
                response = client.get(
                    "/api/v1/job/runs",
                    params={"days": 999, "limit": 999, "job_name": "job_history", "status": "FAILED"},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["status"], "failed")
        runs_mock.assert_called_once_with(days=90, limit=100, job_name="job_history", status="failed")

    def test_get_job_runs_rejects_invalid_status(self) -> None:
        with api_client() as client:
            response = client.get("/api/v1/job/runs", params={"status": "broken"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "status must be one of: running, success, failed, unknown")

    def test_get_job_failure_returns_payload(self) -> None:
        mocked_payload = {
            "log_dir": "/tmp/logs",
            "generated_at": "2026-03-11T00:00:00+00:00",
            "run": {
                "run_id": 101,
                "job_name": "job_history",
                "run_mode": "history",
                "target_range": "20260301:20260305",
                "max_workers": 20,
                "timeout_seconds": 21600,
                "started_ts": 1,
                "started_at": "2026-03-11T00:00:00+00:00",
                "finished_ts": 2,
                "finished_at": "2026-03-11T00:10:00+00:00",
                "status": "failed",
                "timed_out": False,
                "duration_seconds": 600,
                "message": "network timeout",
            },
            "failed_stages": [
                {
                    "stage_name": "sync_daily",
                    "status": "failed",
                    "duration_ms": 1234,
                    "message": "network timeout",
                    "logged_at": "2026-03-11T00:05:00+00:00",
                    "extra": {"trade_date": "20260305"},
                }
            ],
            "failed_tables": [],
            "recent_failures": [],
        }

        with patch("backend.app.api.get_job_failure_detail", return_value=mocked_payload) as failure_mock:
            with api_client() as client:
                response = client.get("/api/v1/job/failures/101")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["run"]["run_id"], 101)
        failure_mock.assert_called_once_with(run_id=101)

    def test_get_job_failure_maps_missing_run_to_404(self) -> None:
        with patch("backend.app.api.get_job_failure_detail", side_effect=ValueError("run_id 999 not found")):
            with api_client() as client:
                response = client.get("/api/v1/job/failures/999")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "run_id 999 not found")

    def test_get_job_table_trends_clamps_query_params(self) -> None:
        mocked_payload = {
            "log_dir": "/tmp/logs",
            "generated_at": "2026-03-11T00:00:00+00:00",
            "window_days": 90,
            "job_name": "job_history",
            "items": [],
            "total": 0,
        }

        with patch("backend.app.api.summarize_table_trends", return_value=mocked_payload) as trends_mock:
            with api_client() as client:
                response = client.get(
                    "/api/v1/job/tables/trends",
                    params={"days": 999, "limit": 999, "job_name": "job_history"},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["window_days"], 90)
        trends_mock.assert_called_once_with(days=90, limit=100, job_name="job_history")

    def test_get_job_failure_trends_clamps_days(self) -> None:
        mocked_payload = {
            "log_dir": "/tmp/logs",
            "generated_at": "2026-03-11T00:00:00+00:00",
            "window_days": 90,
            "job_name": "job_history",
            "current_failure_streak": 2,
            "max_failure_streak": 4,
            "latest_failure": None,
            "daily": [],
            "jobs": [],
        }

        with patch("backend.app.api.summarize_failure_trends", return_value=mocked_payload) as trends_mock:
            with api_client() as client:
                response = client.get(
                    "/api/v1/job/failures/trends",
                    params={"days": 999, "job_name": "job_history"},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["current_failure_streak"], 2)
        trends_mock.assert_called_once_with(days=90, job_name="job_history")


if __name__ == "__main__":
    unittest.main()
