#!/usr/bin/env bash
# Linux/Mac equivalent of run_daily.bat
set -e
cd "$(dirname "$0")"
source .venv/bin/activate
python universe.py
python ingest.py
python validate.py --days 1
python features.py
echo "Done. Launch with: streamlit run app.py"
