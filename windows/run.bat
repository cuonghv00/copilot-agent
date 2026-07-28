@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1

:: Thư mục gốc project = thư mục cha của windows\
set "WIN_DIR=%~dp0"
set "PROJECT_DIR=%WIN_DIR%..\"
set "UV_EXE=%PROJECT_DIR%.uv\uv.exe"

:: ── Kiểm tra uv, tự động setup nếu chưa có ─────────────────────────────────
if not exist "%UV_EXE%" (
    echo [Copilot Agent] uv chua duoc cai dat. Chay setup...
    echo.
    powershell -ExecutionPolicy Bypass -File "%WIN_DIR%setup.ps1"
    if errorlevel 1 (
        echo [ERROR] Setup that bai. Xem log tren.
        pause
        exit /b 1
    )
    echo.
)

:: ── Kiểm tra config.json ────────────────────────────────────────────────────
if not exist "%PROJECT_DIR%config.json" (
    echo [WARN] config.json chua ton tai.
    echo        Sao chep windows\config.windows.json thanh config.json va chinh sua.
    pause
    exit /b 1
)

:: ── Chạy agent ──────────────────────────────────────────────────────────────
echo [Copilot Agent] Starting...
echo.
"%UV_EXE%" run --project "%PROJECT_DIR%" python "%PROJECT_DIR%main.py" %*

if errorlevel 1 (
    echo.
    echo [ERROR] Agent ket thuc voi loi. Xem log tren.
    pause
)
