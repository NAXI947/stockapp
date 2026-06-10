from __future__ import annotations

import json
from typing import Any
from urllib import request


class JobAlertNotifier:
    def __init__(self, enabled: bool, webhook_url: str):
        self.enabled = enabled
        self.webhook_url = webhook_url

    def notify_job_issue(
        self,
        job_name: str,
        run_mode: str,
        target_range: str,
        status: str,
        message: str,
        duration_seconds: int | None,
        timed_out: bool,
    ) -> None:
        if not self.enabled or not self.webhook_url:
            return
        payload = {
            'job_name': job_name,
            'run_mode': run_mode,
            'target_range': target_range,
            'status': status,
            'message': message,
            'duration_seconds': duration_seconds,
            'timed_out': timed_out,
        }
        data = json.dumps(payload, ensure_ascii=True).encode('utf-8')
        req = request.Request(
            self.webhook_url,
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        with request.urlopen(req, timeout=5) as response:
            response.read()


def build_job_alert_notifier(config: Any) -> JobAlertNotifier:
    return JobAlertNotifier(config.alert.enabled, config.alert.webhook_url)
