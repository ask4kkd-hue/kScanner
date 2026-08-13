@echo off
REM ===================================================================
REM  WEEKLY FULL REBUILD - do not skip this.
REM
REM  Corporate actions retroactively change history and yfinance
REM  silently restates past bars. Incremental updates never catch
REM  either. This is how wrong history quietly accumulates in most
REM  home-built scanners.
REM ===================================================================
cd /d "%~dp0"
call .venv\Scripts\activate

REM Antivirus HTTPS scanning (AVG etc.) breaks yfinance's curl_cffi backend.
REM See README Part 6 troubleshooting for how this file is generated.
if exist "..\raw\combined_ca_bundle.pem" (
    set CURL_CA_BUNDLE=%~dp0..\raw\combined_ca_bundle.pem
    set SSL_CERT_FILE=%~dp0..\raw\combined_ca_bundle.pem
)

python universe.py
python ingest.py
python validate.py --days 5
python features.py --full

echo.
echo Full rebuild complete.
