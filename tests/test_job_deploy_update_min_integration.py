from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from jobs import job_deploy_update


class JobDeployUpdateMinIntegrationTest(unittest.TestCase):
    def test_history_mode_runs_bootstrap_then_history_command(self) -> None:
        commands: list[list[str]] = []

        def fake_run(command: list[str]) -> None:
            commands.append(command)

        with patch("jobs.job_deploy_update._run", side_effect=fake_run), \
             patch(
                 "sys.argv",
                 [
                     "job_deploy_update.py",
                     "--history",
                     "--start-date",
                     "20260305",
                     "--end-date",
                     "20260306",
                 ],
             ):
            job_deploy_update.main()

        self.assertEqual(len(commands), 2)
        self.assertTrue(commands[0][-1].endswith(str(Path("jobs") / "job_bootstrap.py")))
        self.assertTrue(commands[1][-3].endswith(str(Path("jobs") / "job_history.py")))
        self.assertEqual(commands[1][-2:], ["20260305", "20260306"])

    def test_daily_mode_runs_bootstrap_then_daily_pipeline(self) -> None:
        commands: list[list[str]] = []

        def fake_run(command: list[str]) -> None:
            commands.append(command)

        with patch("jobs.job_deploy_update._run", side_effect=fake_run), \
             patch("sys.argv", ["job_deploy_update.py", "20260306", "--mode", "light"]):
            job_deploy_update.main()

        self.assertEqual(len(commands), 2)
        self.assertTrue(commands[0][-1].endswith(str(Path("jobs") / "job_bootstrap.py")))
        self.assertTrue(commands[1][2].endswith(str(Path("jobs") / "job_daily_pipeline.py")))
        self.assertIn("20260306", commands[1])
        self.assertIn("light", commands[1])


if __name__ == "__main__":
    unittest.main()
