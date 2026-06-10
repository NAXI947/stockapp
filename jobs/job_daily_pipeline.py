from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run daily pipeline")
    parser.add_argument("trade_date", nargs="?", default=None, help="trade date in YYYYMMDD")
    parser.add_argument("--mode", choices=["light", "full"], default=None, help="pipeline mode")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    trade_date = args.trade_date
    pipeline_mode = (args.mode or os.environ.get('JOB_PIPELINE_MODE', 'light')).strip().lower()
    if pipeline_mode not in {'light', 'full'}:
        pipeline_mode = 'light'
    steps: list[tuple[str, list[str]]]
    if pipeline_mode == 'light':
        steps = [
            ('job_daily_common.py', (['--light'] + ([trade_date] if trade_date else []))),
            ('job_daily_featured.py', ([trade_date] if trade_date else [])),
            ('job_daily_strategy.py', (['--latest-only'] + ([trade_date] if trade_date else []))),
        ]
    else:
        steps = [
            ('job_daily_common.py', ([trade_date] if trade_date else [])),
            ('job_daily_featured.py', ([trade_date] if trade_date else [])),
            ('job_daily_strategy.py', ([])),
        ]
    total_steps = len(steps)
    print(f"[pipeline] mode={pipeline_mode} trade_date={trade_date or 'latest'}")
    for index, (script_name, args) in enumerate(steps, start=1):
        cmd = [sys.executable, str(ROOT / 'jobs' / script_name)] + args
        start_percent = ((index - 1) / total_steps) * 100.0
        print(f"[pipeline] {start_percent:.1f}% start: {' '.join(cmd)}")
        completed = subprocess.run(cmd, check=False)
        if completed.returncode != 0:
            raise SystemExit(f"[pipeline] failed: {script_name} exit={completed.returncode}")
        end_percent = (index / total_steps) * 100.0
        print(f"[pipeline] {end_percent:.1f}% success: {script_name}")


if __name__ == '__main__':
    main()
