@echo off
REM ===================================================================
REM  Daily update. Safe to run once a day, or once a month.
REM  The calendar anti-join fills whatever is missing either way -
REM  there is no separate "backfill mode".
REM ===================================================================
cd /d "%~dp0"
call .venv\Scripts\activate

REM Antivirus HTTPS scanning (AVG etc.) breaks yfinance's curl_cffi backend.
REM See README Part 6 troubleshooting for how this file is generated.
if exist "..\raw\combined_ca_bundle.pem" (
    set CURL_CA_BUNDLE=%~dp0..\raw\combined_ca_bundle.pem
    set SSL_CERT_FILE=%~dp0..\raw\combined_ca_bundle.pem
)

echo [1/4] Refreshing universe and surveillance flags...
python universe.py
if errorlevel 1 goto :error

echo [2/4] Fetching prices and filling gaps...
python ingest.py
if errorlevel 1 goto :error

echo [3/4] Validating against the official bhavcopy...
python validate.py --days 1
if errorlevel 1 goto :error

echo [4/4] Rebuilding features...
python features.py
if errorlevel 1 goto :error

echo.
echo Done. Launch the app with:  cd web ^&^& python main.py
goto :eof

:error
echo.
echo FAILED at the step above. Check logs\ before trusting any scan.
exit /b 1
