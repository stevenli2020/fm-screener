# WSL Ubuntu test workflow

All development verification for FinancialMarket is run in WSL Ubuntu. Work from the
mounted project directory, normally `/mnt/d/Projects/FinancialMarket`.

## One-time setup

```bash
sudo apt update
sudo apt install -y python3-venv
cd /mnt/d/Projects/FinancialMarket
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev,server]'
```

## Standard test loop

```bash
cd /mnt/d/Projects/FinancialMarket
set -a && source .env && set +a
.venv/bin/python -m pytest
.venv/bin/python -m ruff check src tests
.venv/bin/python -m ruff format --check src tests
.venv/bin/python -m pip check
```

## Live API acceptance check

Start the project-owned server from WSL. The command returns immediately, runs the
server in the background, and keeps only one managed instance. A subsequent start
stops the previous managed instance first. Runtime output is written to
`data/fm-data-server.log` and the PID is recorded in `data/fm-data-server.pid`.

In terminal one:

```bash
cd /mnt/d/Projects/FinancialMarket
set -a && source .env && set +a
.venv/bin/fm-data-server
```

In terminal two:

```bash
cd /mnt/d/Projects/FinancialMarket
set -a && source .env && set +a
.venv/bin/fm health
.venv/bin/fm ohlcv D05.SI --start-date 2025-01-01 --end-date 2025-01-31
```

For foreground diagnostics, use `FM_DATA_SERVER_FOREGROUND=1 .venv/bin/fm-data-server`.
