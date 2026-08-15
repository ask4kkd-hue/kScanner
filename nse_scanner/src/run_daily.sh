#!/usr/bin/env bash
# Linux/Mac equivalent of run_daily.bat
set -e
cd "$(dirname "$0")"
source .venv/bin/activate
python universe.py
python ingest.py
python validate.py --days 1
python features.py
echo "Done. Launch with: cd src/api && python main.py (backend, :8000), and in another shell: cd ../../../nse_scanner_ui && npm run dev (frontend, :5173)"
