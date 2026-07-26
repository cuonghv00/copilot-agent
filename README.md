# 🤖 Copilot Agent

> Automation pipeline biến M365 Copilot thành một AI coding agent thực thụ — gửi task, nhận code, tự động apply và verify, không cần thao tác thủ công.

---

## Mục lục

- [Tổng quan](#tổng-quan)
- [Kiến trúc hệ thống](#kiến-trúc-hệ-thống)
- [Yêu cầu](#yêu-cầu)
- [Cài đặt](#cài-đặt)
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
