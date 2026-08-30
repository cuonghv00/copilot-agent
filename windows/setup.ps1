# setup.ps1 — Cài đặt lần đầu cho Copilot Agent trên Windows (không cần Admin)
#
# Cách dùng:
#   powershell -ExecutionPolicy Bypass -File windows\setup.ps1
#   powershell -ExecutionPolicy Bypass -File windows\setup.ps1 -NoProxy
#   powershell -ExecutionPolicy Bypass -File windows\setup.ps1 -Proxy "http://proxy.company.com:8080"
#
param(
    [switch]$NoProxy,                # Bỏ qua proxy hệ thống hoàn toàn
    [string]$Proxy = ""              # Dùng proxy cụ thể (ghi đè system proxy)
)

$ErrorActionPreference = "Stop"
$WinDir     = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $WinDir      # thư mục cha = project root
$UvDir      = Join-Path $ProjectDir ".uv"
$UvExe      = Join-Path $UvDir "uv.exe"

Write-Host ""
Write-Host "=== Copilot Agent — Windows Setup ===" -ForegroundColor Cyan
Write-Host "Project: $ProjectDir" -ForegroundColor DarkGray

# Hiển thị chế độ proxy đang dùng
if ($NoProxy) {
    Write-Host "Proxy:   [disabled]" -ForegroundColor Yellow
} elseif ($Proxy) {
    Write-Host "Proxy:   $Proxy" -ForegroundColor Yellow
} else {
    Write-Host "Proxy:   [system default]" -ForegroundColor DarkGray
}
Write-Host ""

# ── Hàm helper: Invoke-WebRequest với cài đặt proxy ────────────────────────
function Download-File {
    param([string]$Uri, [string]$OutFile)

    if ($NoProxy) {
        # Bypass system proxy: đặt empty proxy cho session này
        $webProxy = New-Object System.Net.WebProxy
        [System.Net.WebRequest]::DefaultWebProxy = $webProxy
        Invoke-WebRequest -Uri $Uri -OutFile $OutFile -UseBasicParsing
    } elseif ($Proxy) {
        Invoke-WebRequest -Uri $Uri -OutFile $OutFile -UseBasicParsing -Proxy $Proxy -ProxyUseDefaultCredentials
    } else {
        Invoke-WebRequest -Uri $Uri -OutFile $OutFile -UseBasicParsing
    }
}

# ── Hàm helper: set env vars proxy cho uv ──────────────────────────────────
function Set-UvProxyEnv {
    if ($NoProxy) {
        # Xóa proxy env vars để uv không dùng proxy nào
        $env:HTTP_PROXY  = ""
        $env:HTTPS_PROXY = ""
        $env:NO_PROXY    = "*"
        $env:http_proxy  = ""
        $env:https_proxy = ""
        $env:no_proxy    = "*"
    } elseif ($Proxy) {
        $env:HTTP_PROXY  = $Proxy
        $env:HTTPS_PROXY = $Proxy
        $env:http_proxy  = $Proxy
        $env:https_proxy = $Proxy
    }
    # else: không set gì → uv dùng proxy hệ thống mặc định
}

# ── 1. Tải uv nếu chưa có ──────────────────────────────────────────────────
if (-not (Test-Path $UvExe)) {
    Write-Host "[1/3] Downloading uv (portable Python package manager)..." -ForegroundColor Yellow

    New-Item -ItemType Directory -Force -Path $UvDir | Out-Null

    $uvZip = Join-Path $UvDir "uv.zip"
    $uvUrl = "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip"

    try {
        Download-File -Uri $uvUrl -OutFile $uvZip
    } catch {
        Write-Host "" 
        Write-Host "ERROR: Không tải được uv." -ForegroundColor Red
        Write-Host "  $_" -ForegroundColor DarkRed
        Write-Host ""
        Write-Host "Gợi ý:" -ForegroundColor Yellow
        Write-Host "  - Thử lại với: setup.ps1 -NoProxy" -ForegroundColor Yellow
        Write-Host "  - Hoặc chỉ định proxy: setup.ps1 -Proxy 'http://proxy:8080'" -ForegroundColor Yellow
        Write-Host "  - Hoặc tải uv.exe thủ công từ:" -ForegroundColor Yellow
        Write-Host "    $uvUrl" -ForegroundColor Cyan
        Write-Host "    rồi đặt vào: $UvExe" -ForegroundColor Cyan
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
Write-Host "[2/4] Installing Python & dependencies (may take a minute)..." -ForegroundColor Yellow
Set-UvProxyEnv
& $UvExe sync --project $ProjectDir
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR: uv sync thất bại." -ForegroundColor Red
    Write-Host "Gợi ý: thử lại với -NoProxy hoặc -Proxy 'http://proxy:port'" -ForegroundColor Yellow
    exit 1
}
Write-Host "    ✓ Dependencies installed." -ForegroundColor Green

# ── 3. Cài Playwright browser (Chromium) ─────────────────────────────────────────────
Write-Host "[3/4] Installing Playwright Chromium (skip if using system Chrome/Edge)..." -ForegroundColor Yellow

# Chỉ cài Playwright Chromium nếu config không chỉ tới executable có sẵn
$ConfigJson = Join-Path $ProjectDir "config.json"
$SkipPlaywrightBrowser = $false
if (Test-Path $ConfigJson) {
    try {
        $cfg = Get-Content $ConfigJson -Raw | ConvertFrom-Json
        if ($cfg.browser_executable_path -ne $null -and $cfg.browser_executable_path -ne "") {
            $SkipPlaywrightBrowser = $true
            Write-Host "    ✓ browser_executable_path set in config.json — skipping Playwright Chromium download." -ForegroundColor Green
        }
    } catch {}
}

if (-not $SkipPlaywrightBrowser) {
    try {
        & $UvExe run --project $ProjectDir playwright install chromium
        if ($LASTEXITCODE -ne 0) { throw "playwright install failed" }
        Write-Host "    ✓ Playwright Chromium installed." -ForegroundColor Green
    } catch {
        Write-Host "    ⚠ Playwright Chromium install thất bại (mạng chặn?)." -ForegroundColor Yellow
        Write-Host "      → Điền browser_executable_path trong config.json để dùng Chrome/Edge có sẵn." -ForegroundColor Yellow
        Write-Host "      Ví dụ: \"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe\"" -ForegroundColor DarkGray
    }
}

# ── 3. Tạo config.json nếu chưa có ─────────────────────────────────────────
Write-Host "[4/4] Checking config.json..." -ForegroundColor Yellow
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
