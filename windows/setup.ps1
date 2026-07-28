# setup.ps1 — Cài đặt lần đầu cho Copilot Agent trên Windows (không cần Admin)
# Chạy: powershell -ExecutionPolicy Bypass -File windows\setup.ps1

$ErrorActionPreference = "Stop"
$WinDir     = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $WinDir      # thư mục cha = project root
$UvDir      = Join-Path $ProjectDir ".uv"
$UvExe      = Join-Path $UvDir "uv.exe"

Write-Host ""
Write-Host "=== Copilot Agent — Windows Setup ===" -ForegroundColor Cyan
Write-Host "Project: $ProjectDir" -ForegroundColor DarkGray
Write-Host ""

# ── 1. Tải uv nếu chưa có ──────────────────────────────────────────────────
if (-not (Test-Path $UvExe)) {
    Write-Host "[1/3] Downloading uv (portable Python package manager)..." -ForegroundColor Yellow

    New-Item -ItemType Directory -Force -Path $UvDir | Out-Null

    $uvZip = Join-Path $UvDir "uv.zip"
    $uvUrl = "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip"

    try {
        Invoke-WebRequest -Uri $uvUrl -OutFile $uvZip -UseBasicParsing
    } catch {
        Write-Host "ERROR: Không tải được uv. Kiểm tra kết nối internet." -ForegroundColor Red
        exit 1
    }

    Expand-Archive -Path $uvZip -DestinationPath $UvDir -Force
    Remove-Item $uvZip -Force

    # uv giải nén vào subfolder, tìm và di chuyển uv.exe ra ngoài
    $found = Get-ChildItem -Path $UvDir -Recurse -Filter "uv.exe" | Select-Object -First 1
    if ($found -and $found.FullName -ne $UvExe) {
        Move-Item $found.FullName $UvExe -Force
    }

    Write-Host "    ✓ uv installed to $UvExe" -ForegroundColor Green
} else {
    Write-Host "[1/3] uv already present — skipping download." -ForegroundColor Green
}

# ── 2. Cài Python + dependencies qua uv ────────────────────────────────────
Write-Host "[2/3] Installing Python & dependencies (may take a minute)..." -ForegroundColor Yellow
& $UvExe sync --project $ProjectDir
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: uv sync thất bại." -ForegroundColor Red
    exit 1
}
Write-Host "    ✓ Dependencies installed." -ForegroundColor Green

# ── 3. Tạo config.json nếu chưa có ─────────────────────────────────────────
Write-Host "[3/3] Checking config.json..." -ForegroundColor Yellow
$ConfigPath    = Join-Path $ProjectDir "config.json"
$ConfigExample = Join-Path $WinDir "config.windows.json"

if (-not (Test-Path $ConfigPath)) {
    if (Test-Path $ConfigExample) {
        Copy-Item $ConfigExample $ConfigPath
        Write-Host "    ✓ config.json created from windows\config.windows.json" -ForegroundColor Green
        Write-Host "    → Hãy chỉnh sửa config.json trước khi chạy." -ForegroundColor Cyan
    } else {
        Write-Host "    ⚠ config.json chưa có. Tạo thủ công theo README." -ForegroundColor Yellow
    }
} else {
    Write-Host "    ✓ config.json already exists." -ForegroundColor Green
}

Write-Host ""
Write-Host "=== Setup hoàn tất! ===" -ForegroundColor Green
Write-Host "Chỉnh sửa config.json nếu cần, sau đó chạy: windows\run.bat" -ForegroundColor Cyan
Write-Host ""
