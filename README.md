# 🤖 Copilot Agent

> Automation pipeline biến M365 Copilot thành một AI coding agent thực thụ — gửi task, nhận code, tự động apply và verify qua Playwright (CDP) trực tiếp trên Chrome/Edge.

---

## Mục lục

- [Tổng quan](#tổng-quan)
- [Kiến trúc hệ thống](#kiến-trúc-hệ-thống)
- [Yêu cầu](#yêu-cầu)
- [Cài đặt](#cài-đặt)
- [Windows Setup (WSL)](#windows-setup-wsl)
- [Windows Native (không WSL)](#windows-native-không-wsl)
- [Cấu hình](#cấu-hình)
- [Sử dụng](#sử-dụng)
- [Lệnh CLI](#lệnh-cli)
- [Skills System](#skills-system)
- [Cấu trúc project](#cấu-trúc-project)

---

## Tổng quan

**Copilot Agent** là một pipeline tự động hóa kết nối Python CLI với M365 Copilot Web thông qua **Playwright (CDP)**. Thay vì phụ thuộc vào Chrome Extension dễ bị ngắt kết nối trong mạng doanh nghiệp, agent điều khiển trực tiếp trình duyệt với profile lưu session cố định.

1. **Zip repo** và sync lên OneDrive
2. **Gửi prompt** tới M365 Copilot trực tiếp qua Playwright
3. **Playwright** tự động thao tác trình duyệt: new chat, select model, paste prompt, click send
4. **Phát hiện file download** (ZIP chứa code) và tải về tự động qua `expect_download()` API
5. **Apply code** từ ZIP vào repo local
6. **Chạy verify command** (unittest, pytest, …) và **tự retry** nếu fail

```
[Python CLI] ──Playwright CDP──► [Chrome/Edge Browser] ──► [M365 Copilot Web]
     │                                │                          │
     │◄── SESSION_ID, STATUS ─────────┤                          │
     │◄── FILE_DOWNLOADED (expect_download) ─────────────────────┤
     │
     ├── apply_downloaded_zip()
     └── run_verify()  →  auto-retry nếu fail
```

---

## Kiến trúc hệ thống

```
 [1. Local Machine]              [2. OneDrive Sync]         [3. Copilot Web]
┌──────────────────┐           ┌───────────────────┐       ┌──────────────────┐
│  Local Repo      │           │ Local Sync Folder │       │ Playwright Browser│
└────────┬─────────┘           └─────────┬─────────┘       └────────┬─────────┘
         │ 1. Zip repo                   │                          │
         ├──────────────────────────────►│                          │
         │                               │ 2. Cloud Auto-Sync       │
         │                               ├─────────────────────────►│
         │ 3. Send Task & OneDrive Link  │                          │
         ├───────────────────────────────┼─────────────────────────►│ 4. New Chat
         │    (via Playwright CDP)       │                          │    Paste & Send
         │                               │                          │ 5. Generate ZIP
         │ 7. Detect downloaded file     │                          │ 6. Auto Download
         │◄──────────────────────────────┼──────────────────────────┤ (expect_download)
         │ 8. Extract & Overwrite Repo   │
         │ 9. Run verify command         │
         └───────────────────────────────┘
```

---

## Yêu cầu

| Thành phần | Phiên bản |
|---|---|
| Python | ≥ 3.11 |
| uv (package manager) | latest |
| Chrome / Edge | Trình duyệt đã cài sẵn trên máy (hoặc Playwright Chromium) |
| M365 Copilot | tài khoản hợp lệ |
| OneDrive | (tùy chọn, để chia sẻ repo với Copilot) |

---

## Cài đặt

```bash
# Clone repo
git clone <repo-url>
cd copilot-agent

# Cài dependencies với uv (Playwright, Rich, Prompt Toolkit)
uv sync

# (Tùy chọn) Cài Chromium nếu không muốn dùng Chrome/Edge hệ thống:
uv run playwright install chromium
```

---

## Windows Setup (WSL)

> **Khuyến nghị cho môi trường doanh nghiệp:** Agent chạy trong WSL, tự động mở Chrome/Edge trên Windows hoặc Chromium.

### Bước 1 — Cài `uv` portable trong WSL

```bash
# Trong terminal WSL (Ubuntu)
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env   # hoặc mở lại terminal
```

### Bước 2 — Clone & khởi tạo project

```bash
# Trong WSL
git clone <repo-url>
cd copilot-agent

# uv tự tải Python đúng version + cài dependencies
uv sync
```

### Bước 3 — Cấu hình `config.json` cho Windows/WSL

```json
{
  "repo_path": "/home/cuonghv22/projects/my-project",
  "sync_path": "/mnt/c/Users/cuonghv22/OneDrive - FPT Software/copilot-sync",
  "download_path": "/mnt/c/Users/cuonghv22/Downloads/CopilotAgent",
  "onedrive_link": "https://<tenant>-my.sharepoint.com/:u:/r/personal/<user>/Documents/copilot-sync/{zip_filename}",
  "browser_profile_dir": "~/.copilot-agent-profile",
  "browser_headless": false,
  "browser_executable_path": "",
  "sync_delay": 15,
  "onedrive_link_delay_ms": 3000
}
```

### Bước 4 — Khởi động

```bash
# Trong WSL terminal
uv run python main.py
```

Lần đầu chạy: Browser sẽ tự mở, đăng nhập tài khoản M365 Copilot. Profile và session cookie sẽ được lưu tự động vào `browser_profile_dir` cho các lần sau.

---

## Windows Native (không WSL)

> Chạy agent **trực tiếp trên Windows** — không cần WSL, không cài Python vào hệ thống. Chỉ cần giải nén và double-click `windows\run.bat`.

### Phương án A — Portable (khuyến nghị)

**Lần đầu chạy:**

1. Tải source code vào thư mục bất kỳ, ví dụ: `D:\copilot-agent\`
2. Copy file `windows\config.windows.json` thành `config.json` (thư mục gốc)
3. Điền đường dẫn Chrome vào `browser_executable_path` nếu muốn dùng Chrome có sẵn:
   `"browser_executable_path": "C:/Program Files/Google/Chrome/Application/chrome.exe"`
4. Double-click **`windows\run.bat`** (hoặc chạy hỗ trợ proxy/no-proxy):
   ```cmd
   windows\run.bat --no-proxy
   ```

`run.bat` sẽ tự động:
- Tải `uv.exe` portable (~10MB) vào thư mục `.uv\`
- Cài Python + dependencies và Playwright vào `.venv\`
- Khởi động agent và mở browser

### Tùy chọn Proxy cho Windows Setup & Launch

Nếu mạng công ty chặn/yêu cầu proxy:

```cmd
:: Bypass proxy hoàn toàn
windows\run.bat --no-proxy

:: Chỉ định proxy cụ thể
windows\run.bat --proxy http://proxy.company.com:8080
```

---

## Cấu hình

Chỉnh sửa file `config.json` ở thư mục gốc:

```json
{
  "repo_path": "./demo_project/my_project",
  "sync_path": "./demo_project/my_project_sync",
  "download_path": "~/Downloads/CopilotAgent",
  "onedrive_link": "https://example.com/{zip_filename}",
  "copilot_base_url": "https://m365.cloud.microsoft/chat",
  "browser_profile_dir": "~/.copilot-agent-profile",
  "browser_headless": false,
  "browser_executable_path": "",
  "browser_timeout_ms": 30000,
  "default_model": "auto",
  "verify_command": "python3 -m unittest discover",
  "max_retry_on_failure": 1,
  "zip_exclude_dirs": [".git", "__pycache__", "node_modules", ".venv"],
  "active_skill": "default",
  "skills_dir": "./skills",
  "session_state_file": "./.copilot-agent-state.json",
  "sync_command": "",
  "sync_delay": 10,
  "onedrive_link_delay_ms": 3000
}
```

| Key | Mô tả |
|---|---|
| `repo_path` | Đường dẫn repo cần làm việc |
| `sync_path` | Thư mục sync với OneDrive (file ZIP sẽ được đặt ở đây) |
| `download_path` | Thư mục nhận file ZIP từ Copilot |
| `onedrive_link` | Link OneDrive public tới ZIP (`{zip_filename}` / `{repo_name}`) |
| `browser_profile_dir` | Thư mục lưu thông tin đăng nhập/session cookies của browser |
| `browser_headless` | Đặt `true` nếu muốn ẩn giao diện trình duyệt |
| `browser_executable_path` | Đường dẫn file `chrome.exe` hoặc `msedge.exe` (để trống nếu dùng Playwright Chromium) |
| `browser_timeout_ms` | Timeout thao tác DOM của Playwright (ms) |
| `default_model` | Model Copilot mặc định (`auto`, `think`, `quick`, `gpt`, `sonnet`, …) |
| `verify_command` | Lệnh verify sau khi apply code (`pytest`, `python3 -m unittest discover`) |
| `max_retry_on_failure` | Số lần tự động retry khi verify thất bại |
| `onedrive_link_delay_ms` | Thời gian chờ Copilot nhận diện attachment OneDrive link trước khi ấn Send |

---

## Sử dụng

### 1. Khởi động CLI

```bash
# Với uv
uv run python main.py

# Hoặc qua script trên Windows
windows\run.bat
```

### 2. Quy trình cơ bản

1. CLI khởi động Playwright Browser với persistent profile.
2. Nhập đường dẫn repo để zip (Enter để bỏ qua).
3. Gõ task vào prompt và nhấn Enter.
4. Agent tự thao tác trên Copilot (chọn model, dán prompt, click Send, chờ response).
5. Phát hiện và tự tải file ZIP qua Playwright download handler.
6. CLI tự động giải nén apply code + chạy lệnh verify.

---

## Lệnh CLI

| Lệnh | Mô tả |
|---|---|
| `/help` | Hiển thị danh sách lệnh |
| `/exit` | Thoát chương trình |
| `/new [model]` | Bắt đầu chat session mới (xóa lịch sử) |
| `/model [tên]` | Đổi model Copilot đang dùng |
| `/resume [session-id]` | Tiếp tục session Copilot cũ |
| `/zip` | Re-zip repo và cập nhật OneDrive link |
| `/diff` | Hiển thị `git diff` của repo hiện tại |
| `/verify` | Chạy verify command thủ công |
| `/skill list` | Liệt kê các skill có sẵn |
| `/out` | Toggle chế độ output rules (yêu cầu Copilot xuất ZIP) |

### Model hỗ trợ

| Model key | Mô tả |
|---|---|
| `auto` | Mặc định (để Copilot tự chọn) |
| `think` | Chế độ reasoning (Copilot Think Deeper) |
| `quick` | Phản hồi nhanh |
| `gpt` | GPT model |
| `sonnet` | Claude Sonnet |
| `opus` | Claude Opus |

---

## Skills System

Skills là các template prompt được tái sử dụng. Mỗi skill là một thư mục trong `skills/` chứa file `skills.md`.

**Sử dụng trong prompt:**
```
❯ Refactor module auth.py theo chuẩn @clean-code
```

---

## Cấu trúc project

```
copilot-agent/
├── main.py                   # Entrypoint
├── config.json               # Cấu hình chính
├── pyproject.toml            # Python dependencies
│
├── agent/                    # Python package chính
│   ├── cli.py                # Main loop, xử lý lệnh CLI
│   ├── browser.py            # Playwright Controller (thao tác DOM, session, downloads)
│   ├── runner.py             # TaskRunner: Orchestrate task dispatch & verify
│   ├── prompt.py             # Xây dựng prompt đầy đủ, skills loader
│   ├── repo.py               # zip_repo, apply_downloaded_zip, run_verify
│   ├── config.py             # load_config, AgentState (session persistence)
│   └── ui.py                 # Rich console, panels, toolbar
│
├── windows/                  # Helper scripts riêng cho Windows
│   ├── setup.ps1             # PowerShell setup script (tự tải uv, playwright, deps)
│   ├── run.bat               # Windows launcher script (hỗ trợ --no-proxy/--proxy)
│   └── config.windows.json   # Template cấu hình cho Windows Native
│
├── extension/                # Extension backup (không bắt buộc dùng)
├── skills/                   # Skill templates
├── tests/                    # Unit tests
└── demo_project/             # Project mẫu thử nghiệm
```

---

## Bảo mật

- **Path traversal protection**: `apply_downloaded_zip()` kiểm tra mọi entry trong ZIP trước khi giải nén.
- **Shell injection prevention**: `run_verify()` dùng `shlex.split` + `shell=False`.
- **Task serialization**: `asyncio.Lock` đảm bảo chỉ một task chạy tại một thời điểm.
- **Persistent Profile**: Thông tin đăng nhập lưu trên máy cá nhân tại `browser_profile_dir`, không gửi ra ngoài.

---

## License

MIT
