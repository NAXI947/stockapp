from __future__ import annotations

import os
import re
import json
import socket
import sys
import threading
import time
from pathlib import Path
from urllib.request import urlopen

import uvicorn
import webview


class DesktopApi:
    def _store_path(self) -> Path:
        path = app_dir() / "data" / "desktop_store.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _read_store(self) -> dict[str, object]:
        path = self._store_path()
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def load_store(self, key: str) -> dict[str, object]:
        try:
            data = self._read_store()
            return {"ok": True, "value": data.get(str(key))}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "value": None}

    def save_store(self, key: str, value: object) -> dict[str, object]:
        try:
            path = self._store_path()
            data = self._read_store()
            data[str(key)] = value
            temp_path = path.with_suffix(".tmp")
            temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            temp_path.replace(path)
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def save_text_file(self, filename: str, content: str) -> dict[str, object]:
        safe_name = re.sub(r'[<>:"/\\|?*]+', "_", filename or "export.txt").strip() or "export.txt"
        try:
            window = webview.windows[0] if webview.windows else None
            if window is None:
                return {"saved": False, "error": "Window is not ready."}

            selected = window.create_file_dialog(webview.SAVE_DIALOG, save_filename=safe_name)
            if not selected:
                return {"saved": False}

            target = selected[0] if isinstance(selected, (list, tuple)) else selected
            Path(target).write_text(content, encoding="utf-8")
            return {"saved": True, "path": str(target)}
        except Exception as exc:
            return {"saved": False, "error": str(exc)}


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def find_port(start: int = 8765) -> int:
    for port in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("No available local port found.")


def wait_until_ready(url: str, timeout_seconds: int = 30) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.3)
    raise RuntimeError("Desktop service did not become ready in time.")


def main() -> None:
    root = app_dir()
    os.chdir(root)
    os.environ.setdefault("APP_ENV", "desktop")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    port = find_port()
    config = uvicorn.Config(
        "backend.main:app",
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="stocknew-api", daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    wait_until_ready(f"{base_url}/health")
    webview.create_window(
        "阻力最小爆发模型 V1.2",
        f"{base_url}/picks",
        width=1280,
        height=820,
        js_api=DesktopApi(),
    )
    webview.start()
    server.should_exit = True


if __name__ == "__main__":
    main()
