from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import uvicorn


PID_FILE = Path(os.getenv("FM_DATA_SERVER_PID_FILE", "data/fm-data-server.pid"))
LOG_FILE = Path(os.getenv("FM_DATA_SERVER_LOG_FILE", "data/fm-data-server.log"))


def _stop_previous() -> None:
    """Stop the previous server recorded by this project's pid file."""
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except PermissionError:
        return

    for _ in range(20):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)


def _run_foreground(host: str, port: int) -> None:
    uvicorn.run("financial_market.data_server.api:app", host=host, port=port)


def main() -> None:
    host = os.getenv("FM_DATA_SERVER_HOST", "127.0.0.1")
    port = int(os.getenv("FM_DATA_SERVER_PORT", "8766"))
    if os.getenv("FM_DATA_SERVER_FOREGROUND") == "1":
        _run_foreground(host, port)
        return

    _stop_previous()
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    log = LOG_FILE.open("ab")
    child = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "financial_market.data_server.api:app",
            "--host",
            host,
            "--port",
            str(port),
        ],
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    log.close()
    PID_FILE.write_text(str(child.pid), encoding="utf-8")


if __name__ == "__main__":
    main()
