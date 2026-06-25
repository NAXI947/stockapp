from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from backend.app.paths import runtime_root

ROOT = runtime_root()
LOG_DIR = ROOT / 'logs'
_RUN_ID_LOCK = threading.Lock()
_LAST_RUN_ID = 0

thread_local_data = threading.local()


def next_run_id() -> int:
    global _LAST_RUN_ID
    with _RUN_ID_LOCK:
        candidate = int(time.time() * 1000)
        if candidate <= _LAST_RUN_ID:
            candidate = _LAST_RUN_ID + 1
        _LAST_RUN_ID = candidate
        if hasattr(thread_local_data, 'run_ids') and isinstance(thread_local_data.run_ids, list):
            thread_local_data.run_ids.append(candidate)
        return candidate


def write_json_log(filename: str, payload: dict[str, Any]) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / filename
    with path.open('a', encoding='utf-8') as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, separators=(',', ':')))
        fh.write('\n')
