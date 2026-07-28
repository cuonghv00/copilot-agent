# 🤖 Copilot Agent

> Automation pipeline biến M365 Copilot thành một AI coding agent thực thụ — gửi task, nhận code, tự động apply và verify, không cần thao tác thủ công.

---

## Mục lục

- [Tổng quan](#tổng-quan)
- [Kiến trúc hệ thống](#kiến-trúc-hệ-thống)
- [Yêu cầu](#yêu-cầu)
- [Cài đặt](#cài-đặt)
- [Windows Setup (WSL)](#windows-setup-wsl)
- [Windows Native (không WSL)](#windows-native-không-wsl)
- [Cấu hình](#cấu-hình)
- [Cài đặt Chrome Extension](#cài-đặt-chrome-extension)
- [Sử dụng](#sử-dụng)
- [Lệnh CLI](#lệnh-cli)
- [Skills System](#skills-system)
- [Cấu trúc project](#cấu-trúc-project)

---

## Tổng quan

**Copilot Agent** là một pipeline tự động hóa kết nối Python CLI với Chrome Extension để điều khiển M365 Copilot Web. Thay vì copy-paste thủ công, bạn gõ task trên terminal — agent sẽ:

1. **Zip repo** và sync lên OneDrive
2. **Gửi prompt** tới M365 Copilot qua WebSocket → Extension
3. **Extension** tự động thao tác trình duyệt: new chat, paste prompt, click send
4. **Phát hiện file download** (ZIP chứa code) và tải về tự động
5. **Apply code** từ ZIP vào repo local
6. **Chạy verify command** (unittest, pytest, …) và **tự retry** nếu fail

```
[Python CLI] ──WebSocket──► [Chrome Extension] ──► [M365 Copilot Web]
     │                              │                      │
     │◄── SESSION_ID, STATUS ───────┤                      │
     │◄── FILE_DOWNLOADED ──────────┤◄── Auto Download ────┤
     │                              │
     ├── apply_downloaded_zip()
     └── run_verify()  →  auto-retry nếu fail
```

---

## Kiến trúc hệ thống

```
 [1. Local Machine]              [2. OneDrive Sync]         [3. Copilot Web]
┌──────────────────┐           ┌───────────────────┐       ┌──────────────────┐
│  Local Repo      │           │ Local Sync Folder │       │ Chrome/Edge Tab  │
└────────┬─────────┘           └─────────┬─────────┘       └────────┬─────────┘
         │ 1. Zip repo                   │                          │
         ├──────────────────────────────►│                          │
         │                               │ 2. Cloud Auto-Sync       │
         │                               ├─────────────────────────►│
         │ 3. Send Task & OneDrive Link  │                          │
         ├───────────────────────────────┼─────────────────────────►│ 4. New Chat
         │    (via WebSocket)            │                          │    Paste & Send
         │                               │                          │ 5. Generate ZIP
         │ 7. Detect downloaded file     │                          │ 6. Auto Download
         │◄──────────────────────────────┼──────────────────────────┤
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
| Chrome / Edge | bất kỳ (với extension) |
| M365 Copilot | tài khoản hợp lệ |
| OneDrive | (tùy chọn, để chia sẻ repo với Copilot) |

---

## Cài đặt

```bash
# Clone repo
git clone <repo-url>
cd copilot-agent

# Cài dependencies với uv
uv sync

# Hoặc với pip
pip install websockets rich prompt-toolkit
```

---

## Windows Setup (WSL)

> **Khuyến nghị cho môi trường doanh nghiệp:** Agent chạy trong WSL, Chrome/Edge chạy trên Windows. Không cần cài Python hay công cụ nào vào Windows.

### Bước 1 — Cài WSL (nếu chưa có)

Mở PowerShell với quyền Admin:
```powershell
wsl --install
# Khởi động lại máy, sau đó mở Ubuntu từ Start Menu
```

### Bước 2 — Cài `uv` portable trong WSL

`uv` là package manager không cần quyền root, không cài vào system Python:

```bash
# Trong terminal WSL (Ubuntu)
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env   # hoặc mở lại terminal

# Kiểm tra
uv --version
```

> **Tại sao `uv`?** Tự quản lý Python interpreter, tạo `.venv` isolated, không đụng đến system packages. Hoàn toàn portable — xóa thư mục là sạch.

### Bước 3 — Clone & khởi tạo project

```bash
# Trong WSL
git clone <repo-url>
cd copilot-agent

# uv tự tải Python đúng version + cài dependencies
uv sync
```

### Bước 4 — Xác định đường dẫn OneDrive

OneDrive trên Windows được mount vào WSL tại `/mnt/c/Users/<tên>/OneDrive*/`. Tìm thư mục sync:

```bash
# Tìm thư mục OneDrive
ls "/mnt/c/Users/$(cmd.exe /c 'echo %USERNAME%' 2>/dev/null | tr -d '\r')/"

# Ví dụ kết quả điển hình:
# /mnt/c/Users/cuonghv22/OneDrive - FPT Software/
```

Tạo thư mục sync trong OneDrive:
```bash
mkdir -p "/mnt/c/Users/cuonghv22/OneDrive - FPT Software/copilot-sync"
```

### Bước 5 — Cấu hình `config.json` cho Windows/WSL

```json
{
  "repo_path": "/home/cuonghv22/projects/my-project",
  "sync_path": "/mnt/c/Users/cuonghv22/OneDrive - FPT Software/copilot-sync",
  "download_path": "/mnt/c/Users/cuonghv22/Downloads/CopilotAgent",
  "onedrive_link": "https://<tenant>-my.sharepoint.com/:u:/r/personal/<user>/Documents/copilot-sync/{zip_filename}",
  "sync_delay": 15,
  "onedrive_link_delay_ms": 3000,
  "reconnect_timeout_s": 60
}
```

> **`sync_delay`:** OneDrive trên Windows cần thêm thời gian upload so với Linux native. Khuyến nghị 10–20 giây.

### Bước 6 — Khởi động

```bash
# Trong WSL terminal
uv run python main.py
```

Sau đó mở Chrome/Edge trên Windows, load extension và vào M365 Copilot.

### Bước 7 — Lấy SharePoint link OneDrive

Để lấy link dùng cho `onedrive_link` trong config:

1. Mở OneDrive trên web (`https://<tenant>-my.sharepoint.com`)
2. Vào thư mục `copilot-sync/`
3. Chuột phải vào file `.zip` → **Share** → **Copy link**
4. Lấy phần URL base, thay tên file bằng `{zip_filename}`

```
# Ví dụ link thực:
https://fptsoftware362-my.sharepoint.com/:u:/r/personal/cuonghv22_fpt_com/Documents/copilot-sync/my-project.zip

# Điền vào config (thay "my-project.zip" bằng {zip_filename}):
"onedrive_link": "https://fptsoftware362-my.sharepoint.com/:u:/r/personal/cuonghv22_fpt_com/Documents/copilot-sync/{zip_filename}"
```

### Troubleshooting Windows/WSL

| Vấn đề | Nguyên nhân | Giải pháp |
|---|---|---|
| Extension không kết nối được | Firewall Windows chặn port WSL | Chạy `wsl hostname -I` lấy IP WSL, điền vào extension options thay `localhost` |
| OneDrive chưa sync kịp | Upload chậm | Tăng `sync_delay` lên 20–30s |
| Copilot không nhận file | Paste quá nhanh | Tăng `onedrive_link_delay_ms` lên 4000–5000 |
| Extension mất kết nối giữa chừng | Mạng chập chờn | `reconnect_timeout_s: 90` — agent tự chờ reconnect |
| Đường dẫn không hợp lệ trong WSL | Dùng path Windows `C:\\...` | Dùng `/mnt/c/...` thay thế |

### WSL Firewall (nếu extension không kết nối được)

```powershell
# Chạy trong PowerShell (Admin) trên Windows
# Lấy IP của WSL
$wslIp = (wsl hostname -I).Trim()
Write-Host "WSL IP: $wslIp"

# Thêm port proxy cho phép port 8765 từ Windows vào WSL
netsh interface portproxy add v4tov4 listenport=8765 listenaddress=0.0.0.0 connectport=8765 connectaddress=$wslIp
```

Sau đó trong extension Options, thay `ws://localhost:8765` bằng `ws://<WSL-IP>:8765`.

---

## Windows Native (không WSL)

> Chạy agent **trực tiếp trên Windows** — không cần WSL, không cài Python vào hệ thống. Chỉ cần giải nén và double-click `windows\run.bat`.

### Phương án A — Portable (khuyến nghị)

**Lần đầu chạy:**

1. Tải source code (clone hoặc giải nén ZIP) vào một thư mục bất kỳ, ví dụ: `D:\copilot-agent\`
2. Copy file `windows\config.windows.json` thành `config.json` (thư mục gốc) và chỉnh sửa các đường dẫn
3. Double-click **`windows\run.bat`**

`run.bat` sẽ tự động:
- Tải `uv.exe` portable (~10MB) vào thư mục `.uv\` nếu chưa có
- Cài Python đúng phiên bản + dependencies vào `.venv\`
- Khởi động agent

**Các lần sau:** Double-click `windows\run.bat` là xong.

> **Portable hoàn toàn:** Xóa thư mục là sạch. Không đụng gì vào Windows Registry hay System PATH.

### Setup một lần (không dùng run.bat)

Nếu muốn chạy từ PowerShell thủ công:

```powershell
# Trong PowerShell (không cần Admin)
powershell -ExecutionPolicy Bypass -File windows\setup.ps1

# Chạy agent
.uv\uv.exe run python main.py
```

### Cấu hình `config.json` cho Windows native

Sử dụng `windows\config.windows.json` làm mẫu — khác biệt chính so với Linux:

| Trường | Linux/WSL | Windows Native |
|---|---|---|
| `repo_path` | `/home/user/project` | `C:/Users/user/project` |
| `sync_path` | `/mnt/c/Users/...` | `C:/Users/.../OneDrive.../copilot-sync` |
| `download_path` | `~/Downloads/CopilotAgent` | `C:/Users/user/Downloads/CopilotAgent` |
| `verify_command` | `python3 -m unittest discover` | `python -m unittest discover` |

> **Lưu ý:** Dùng `/` hoặc `\\` trong path JSON đều được. Không dùng `\` đơn vì sẽ bị escape.

### Phương án B — Đóng gói `.exe` (phân phối cho tập thể)

Nếu muốn phân phối cho team mà không cần ai cài đặt gì cả:

```bash
# Chạy trong WSL hoặc trên máy dev
uv add --dev pyinstaller

# Build file .exe duy nhất
uv run pyinstaller \
  --onefile \
  --name "copilot-agent" \
  --add-data "skills:skills" \
  --add-data "extension:extension" \
  main.py
```

Hoặc trên Windows PowerShell:

```powershell
.uv\uv.exe add --dev pyinstaller

.uv\uv.exe run pyinstaller `
  --onefile `
  --name "copilot-agent" `
  --add-data "skills;skills" `
  --add-data "extension;extension" `
  main.py
```

> Sau khi build, file `dist\copilot-agent.exe` (~50MB) có thể chạy độc lập. Người dùng chỉ cần có file `.exe` + `config.json`.

> [!NOTE]
> **Giới hạn của `.exe`:** Một số antivirus doanh nghiệp sẽ cảnh báo file `.exe` không có chữ ký số. Trong trường hợp này, phương án A (portable) an toàn hơn.

### Troubleshooting Windows Native

| Vấn đề | Giải pháp |
|---|---|
| `run.bat` đóng ngay | Click chuột phải **`windows\run.bat`** → **Run as Administrator** (chỉ lần đầu nếu firewall chặn) |
| Lỗi `SSL` khi tải uv | Mạng doanh nghiệp chặn GitHub. Hỏi IT whitelist `github.com` hoặc tải `uv.exe` thủ công → đặt vào `.uv\` (thư mục gốc) |

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
  "websocket_port": 8765,
  "default_model": "auto",
  "verify_command": "python3 -m unittest discover",
  "max_retry_on_failure": 1,
  "zip_exclude_dirs": [".git", "__pycache__", "node_modules", ".venv"],
  "active_skill": "default",
  "skills_dir": "./skills",
  "session_state_file": "./.copilot-agent-state.json",
  "sync_command": "",
  "sync_delay": 10
}
```

| Key | Mô tả |
|---|---|
| `repo_path` | Đường dẫn repo cần làm việc |
| `sync_path` | Thư mục sync với OneDrive (file ZIP sẽ được đặt ở đây) |
| `download_path` | Thư mục nhận file ZIP từ Copilot |
| `onedrive_link` | Link OneDrive public tới ZIP. Dùng `{zip_filename}` hoặc `{repo_name}` làm placeholder |
| `websocket_port` | Port WebSocket để CLI ↔ Extension giao tiếp (mặc định: `8765`) |
| `default_model` | Model Copilot mặc định (`auto`, `think`, `quick`, `gpt`, …) |
| `verify_command` | Lệnh verify sau khi apply code (ví dụ: `pytest`, `python3 -m unittest discover`) |
| `max_retry_on_failure` | Số lần tự động retry khi verify thất bại |
| `zip_exclude_dirs` | Các thư mục bị loại khỏi ZIP |
| `sync_command` | Lệnh tùy chọn chạy sau khi zip (ví dụ: rsync, copy sang OneDrive) |
| `sync_delay` | Thời gian chờ (giây) sau sync để OneDrive kịp upload |

---

## Cài đặt Chrome Extension

1. Mở Chrome/Edge → vào `chrome://extensions/`
2. Bật **Developer mode** (góc trên phải)
3. Click **"Load unpacked"** → chọn thư mục `extension/`
4. Extension **"Copilot Agent"** sẽ xuất hiện trong danh sách
5. Mở tab M365 Copilot (`https://m365.cloud.microsoft/chat`)
6. Extension tự động kết nối WebSocket khi CLI chạy

> **Tùy chọn:** Vào trang Options của extension để cấu hình WebSocket port nếu thay đổi khác mặc định.

---

## Sử dụng

### 1. Khởi động CLI

```bash
# Với uv
uv run python main.py

# Hoặc trực tiếp
python main.py
```

### 2. Quy trình cơ bản

```
1. CLI khởi động WebSocket server
2. Mở Chrome với tab M365 Copilot (extension tự kết nối)
3. CLI hỏi đường dẫn repo để zip (Enter để bỏ qua)
4. Gõ task vào prompt và nhấn Enter
5. Agent gửi task → Extension thao tác Copilot → Tải ZIP về
6. CLI tự động apply code + chạy verify
```

### 3. Ví dụ workflow

```
❯ Fix bug trong hàm validate_email ở auth.py để chấp nhận domain .vn /out

→ Agent zip repo → gửi Copilot → nhận ZIP → apply → pytest ✓
```

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

### Inline flags

- Thêm `/out` trực tiếp vào prompt để bật output rules một lần:

  ```
  ❯ Refactor module database.py /out
  ```

---

## Skills System

Skills là các template prompt được tái sử dụng. Mỗi skill là một thư mục trong `skills/` chứa file `skills.md`.

**Cấu trúc:**
```
skills/
├── default/
│   └── skills.md
├── python-backend/
│   └── skills.md
└── clean-code/
    └── skills.md
```

**Sử dụng trong prompt:**
```
❯ Refactor module auth.py theo chuẩn @clean-code
```

Agent sẽ tự động đọc `skills/clean-code/skills.md` và đính kèm nội dung vào prompt gửi Copilot.

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
│   ├── runner.py             # TaskRunner: WebSocket server & task dispatch
│   ├── prompt.py             # Xây dựng prompt đầy đủ, skills loader
│   ├── repo.py               # zip_repo, apply_downloaded_zip, run_verify
│   ├── config.py             # load_config, AgentState (session persistence)
│   └── ui.py                 # Rich console, panels, toolbar
│
├── extension/                # Chrome Extension (Manifest V3)
│   ├── manifest.json
│   ├── background.js         # Service worker, WebSocket client
│   ├── content.js            # Tự động hóa thao tác Copilot Web UI
│   ├── options.html          # Trang cài đặt extension
│   └── options.js
│
├── skills/                   # Skill templates
│   ├── default/
│   ├── python-backend/
│   └── clean-code/
│
├── tests/                    # Unit tests
├── docs/                     # Tài liệu & ý tưởng kiến trúc
└── demo_project/             # Project mẫu để thử nghiệm
```

---

## Bảo mật

- **Path traversal protection**: `apply_downloaded_zip()` kiểm tra mọi entry trong ZIP trước khi giải nén, từ chối bất kỳ path nào trỏ ra ngoài `repo_path`.
- **Shell injection prevention**: `run_verify()` dùng `shlex.split` + `shell=False` để tránh injection.
- **Task serialization**: `asyncio.Lock` đảm bảo chỉ một task chạy tại một thời điểm.
- **WebSocket port**: Chỉ bind trên `localhost` — không expose ra mạng ngoài.

---

## License

MIT
