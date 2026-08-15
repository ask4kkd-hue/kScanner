# dev.ps1 - start (or restart) both the kSCANNER backend and frontend dev
# servers. If either is already running (anything listening on :8000 or
# :5173), it's killed first, then both are started fresh in their own
# visible PowerShell windows so you can see live logs for each.
#
# Run from anywhere:  powershell -ExecutionPolicy Bypass -File dev.ps1
# Or just double-click dev.bat.

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

function Stop-PortListener {
    param([int]$Port, [string]$Label)
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) {
        Write-Host "  $Label (port $Port) - nothing running"
        return
    }
    $procIds = $conns | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($procId in $procIds) {
        Write-Host "  $Label (port $Port) - stopping existing process $procId"
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "Stopping anything already running..."
Stop-PortListener -Port 8000 -Label "Backend"
Stop-PortListener -Port 5173 -Label "Frontend"
Start-Sleep -Seconds 1

Write-Host ""
Write-Host "Starting backend (FastAPI, port 8000)..."
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$root\nse_scanner\src'; & '.\.venv\Scripts\python.exe' api\main.py"
) -WindowStyle Normal

Write-Host "Starting frontend (Vite, port 5173)..."
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$root\nse_scanner_ui'; npm run dev"
) -WindowStyle Normal

Write-Host ""
Write-Host "Two new windows just opened (backend + frontend logs)."
Write-Host "Give them a few seconds, then:"
Write-Host "  Backend health:  http://127.0.0.1:8000/api/health"
Write-Host "  App:             http://localhost:5173"
