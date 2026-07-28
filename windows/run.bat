@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1

:: ──────────────────────────────────────────────────────────────────────────
:: Copilot Agent — Windows Launcher
::
:: Cách dùng:
::   run.bat                          chạy bình thường (dùng proxy hệ thống)
::   run.bat --no-proxy               tắt proxy khi setup + chạy
::   run.bat --proxy http://p:8080    dùng proxy cụ thể khi setup
:: ──────────────────────────────────────────────────────────────────────────

:: Thư mục gốc project = thư mục cha của windows\
set "WIN_DIR=%~dp0"
set "PROJECT_DIR=%WIN_DIR%..\"
set "UV_EXE=%PROJECT_DIR%.uv\uv.exe"

:: ── Parse proxy args ─────────────────────────────────────────────────────
set "SETUP_PROXY_ARGS="
set "UV_PROXY_ARGS="
set "AGENT_ARGS="

:parse_loop
if "%~1"=="" goto parse_done
if /i "%~1"=="--no-proxy" (
    set "SETUP_PROXY_ARGS=-NoProxy"
    set "UV_NO_PROXY=*"
    set "UV_HTTP_PROXY="
    set "HTTP_PROXY="
    set "HTTPS_PROXY="
    shift
    goto parse_loop
)
if /i "%~1"=="--proxy" (
    if "%~2"=="" (
        echo [ERROR] --proxy requires a URL argument.
        echo Usage: run.bat --proxy http://proxy.company.com:8080
        pause
        exit /b 1
    )
    set "SETUP_PROXY_ARGS=-Proxy %~2"
    set "HTTP_PROXY=%~2"
    set "HTTPS_PROXY=%~2"
    shift
    shift
    goto parse_loop
)
:: Các arg còn lại truyền thẳng vào agent
set "AGENT_ARGS=!AGENT_ARGS! %~1"
shift
goto parse_loop
:parse_done

:: ── Kiểm tra uv, tự động setup nếu chưa có ─────────────────────────────────
if not exist "%UV_EXE%" (
    echo [Copilot Agent] uv chua duoc cai dat. Chay setup...
    echo.
    powershell -ExecutionPolicy Bypass -File "%WIN_DIR%setup.ps1" %SETUP_PROXY_ARGS%
    if errorlevel 1 (
        echo.
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
"%UV_EXE%" run --project "%PROJECT_DIR%" python "%PROJECT_DIR%main.py" %AGENT_ARGS%

if errorlevel 1 (
    echo.
    echo [ERROR] Agent ket thuc voi loi. Xem log tren.
    pause
)
