from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Automation entrypoint for bootstrap + daily/history updates"
    )
    parser.add_argument(
        "trade_date",
        nargs="?",
        default=None,
        help="trade date in YYYYMMDD for daily pipeline",
    )
    parser.add_argument(
        "--mode",
        choices=["light", "full"],
        default=None,
        help="daily pipeline mode",
    )
    parser.add_argument(
        "--history",
        action="store_true",
        help="run history sync instead of daily pipeline",
    )
    parser.add_argument(
        "--start-date",
        default=None,
        help="history start date in YYYYMMDD",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="history end date in YYYYMMDD",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="history mode only: rerun full range and ignore checkpoint",
    )
    parser.add_argument(
        "--bootstrap-only",
        action="store_true",
        help="only run bootstrap and exit",
    )
    parser.add_argument(
        "--monthly",
        action="store_true",
        help="run monthly sync (Eastmoney concept members + share_float)",
    )
    parser.add_argument(
        "--quarterly",
        action="store_true",
        help="run quarterly sync (fin_indicator)",
    )
    parser.add_argument(
        "--yearly",
        action="store_true",
        help="run yearly sync (strategy full rebuild)",
    )
    return parser.parse_args()


def _run(command: list[str]) -> None:
    print(f"[auto] run: {' '.join(command)}", flush=True)
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main() -> None:
    args = parse_args()
    cadence_flags = [args.monthly, args.quarterly, args.yearly]
    if sum(1 for enabled in cadence_flags if enabled) > 1:
        raise SystemExit("--monthly/--quarterly/--yearly are mutually exclusive")
    if args.history and any(cadence_flags):
        raise SystemExit("--history cannot be combined with --monthly/--quarterly/--yearly")

    _run([sys.executable, "-u", str(ROOT / "jobs" / "job_bootstrap.py")])
    if args.bootstrap_only:
        return
    if args.history:
        if not args.start_date or not args.end_date:
            raise SystemExit("--history requires --start-date and --end-date")
        command = [
            sys.executable,
            "-u",
            str(ROOT / "jobs" / "job_history.py"),
            args.start_date,
            args.end_date,
        ]
        if args.force:
            command.append("--force")
        _run(command)
        return
    if args.monthly:
        _run([sys.executable, "-u", str(ROOT / "jobs" / "job_monthly.py")])
        return
    if args.quarterly:
        _run([sys.executable, "-u", str(ROOT / "jobs" / "job_quarterly.py")])
        return
    if args.yearly:
        _run([sys.executable, "-u", str(ROOT / "jobs" / "job_yearly.py")])
        return

    command = [sys.executable, "-u", str(ROOT / "jobs" / "job_daily_pipeline.py")]
    if args.trade_date:
        command.append(args.trade_date)
    if args.mode:
        command.extend(["--mode", args.mode])
    _run(command)


if __name__ == "__main__":
    main()
