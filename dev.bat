@echo off
REM Double-click launcher for dev.ps1 — starts/restarts both the backend
REM (FastAPI, :8000) and frontend (Vite, :5173) dev servers.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0dev.ps1"
