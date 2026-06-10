from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.app import job_runner


class ManualJobProgressTest(unittest.TestCase):
    def test_job_definitions_expose_full_and_date_update_entries(self) -> None:
        names = [item["name"] for item in job_runner.list_job_definitions()]

        self.assertEqual(names, ["daily", "update_date", "weekly", "monthly", "yearly"])

    def test_daily_full_update_steps_cover_all_daily_tables(self) -> None:
        steps = job_runner.JOB_DEFINITIONS["daily"]["steps"]

        self.assertEqual(
            steps,
            [
                ("job_daily_common.py", []),
                ("job_daily_featured.py", []),
                ("job_daily_strategy.py", ["--latest-only"]),
            ],
        )

    def test_yearly_full_update_includes_financial_fields_before_strategy_rebuild(self) -> None:
        steps = job_runner.JOB_DEFINITIONS["yearly"]["steps"]

        self.assertEqual(steps, [("job_quarterly.py", []), ("job_yearly.py", [])])

    def test_manual_task_list_keeps_only_six_latest_records(self) -> None:
        original_tasks = job_runner._TASKS.copy()
        try:
            job_runner._TASKS.clear()
            for index in range(8):
                task_id = str(index)
                job_runner._TASKS[task_id] = job_runner.ManualJobTask(
                    task_id=task_id,
                    job_name="daily",
                    label=f"全量日更 {index}",
                    status="success",
                    started_at=f"2026-05-24 10:00:0{index}",
                )

            tasks = job_runner.list_manual_tasks()

            self.assertEqual([task["task_id"] for task in tasks], ["7", "6", "5", "4", "3", "2"])
            self.assertEqual(set(job_runner._TASKS), {"2", "3", "4", "5", "6", "7"})
        finally:
            job_runner._TASKS.clear()
            job_runner._TASKS.update(original_tasks)

    def test_stage_label_covers_supplemental_tables(self) -> None:
        self.assertEqual(job_runner._stage_label("sync_t_concept_detail"), "更新概念明细")
        self.assertEqual(job_runner._stage_label("sync_t_fin_indicator"), "更新财务指标")

    def test_parse_log_progress_prefers_latest_table_progress(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "history.log"
            log_path.write_text(
                "\n".join(
                    [
                        "[stage] start history_sync_market_by_date extra={'trade_date': '20240102'}",
                        "[progress] t_daily_bar batch 1/1 params 1/1 (100.0%) inserted=5329",
                        "[heartbeat] run=run_history_sync status=completed elapsed_s=20.1 started=7 success=7 failed=0 retries=0 fetched=27449 dropped=0 upserted=32799",
                    ]
                ),
                encoding="utf-8",
            )

            progress = job_runner._parse_log_progress(log_path)

        self.assertEqual(progress["percent"], 100)
        self.assertEqual(progress["current"], "t_daily_bar")
        self.assertEqual(progress["detail"], "批次 1/1，已入库 5329 行")
        self.assertEqual(progress["stage"], "history_sync_market_by_date")


if __name__ == "__main__":
    unittest.main()
