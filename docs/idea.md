Ý tưởng của bạn về việc **yêu cầu Copilot xuất ra file hoàn chỉnh để tải về** (thay vì parse text/code block thủ công) là một bước cải tiến rất đắc giá!

Điều này giúp loại bỏ hoàn toàn rủi ro bị lệch định dạng (indentation, missing imports, escape characters) khi parse raw text.

Dưới đây là **Thực thể kiến trúc & Luồng hoạt động đã được tinh chỉnh** theo 4 thông tin bạn đã cung cấp:

---

## Architecture Flow (Luồng thực thi tinh chỉnh)

```
 [1. Local Machine]                  [2. OneDrive Sync]            [3. Copilot Web]
┌──────────────────┐               ┌───────────────────┐          ┌──────────────────┐
│  Local Repo      │               │ Local Sync Folder │          │ Chrome/Edge Tab  │
└────────┬─────────┘               └─────────┬─────────┘          └────────┬─────────┘
         │ 1. Zip repo                       │                             │
         ├──────────────────────────────────►│                             │
         │                                   │ 2. Cloud Auto-Sync          │
         │                                   ├────────────────────────────►│ (OneDrive Cloud)
         │ 3. Send Task & OneDrive Link      │                             │
         ├───────────────────────────────────┼────────────────────────────►│ 4. Click New Chat
         │    (via WebSocket to Extension)   │                             │    Paste Link & Prompt
         │                                   │                             │ 5. Generate & Output
         │                                   │                             │    Downloadable File
         │ 7. Detect new file                │                             │ 6. Auto Click Download
         │◄──────────────────────────────────┼─────────────────────────────┤    to Download Folder
         │ 8. Extract & Overwrite Repo       │                             │
         │ 9. Run `pytest` / `python main.py`│                             │
         └───────────────────────────────────┴─────────────────────────────┴──────────────────┘

```

---

## Chi tiết 5 Bước thực thi hoàn chỉnh

### Bước 1: Khởi tạo & Nén file (Python Local CLI)

* Script Python tự động nén repo hiện tại thành `workspace.zip` và lưu thẳng vào thư mục OneDrive Sync local:
`C:\Users\<User>\OneDrive - Business\CopilotWorkspace\workspace.zip`
* **OneDrive Sync Client** tự động đẩy file lên cloud.
* Link OneDrive của file này là **cố định** (ví dụ: `https://<company>[-my.sharepoint.com/:u:/g/personal/.../workspace.zip](https://-my.sharepoint.com/:u:/g/personal/.../workspace.zip)`).

### Bước 2: Kích hoạt Task qua WebSocket (Python CLI ➔ Extension)

Python CLI kết nối tới Chrome Extension qua WebSocket và gửi thông tin:

```json
{
  "action": "START_NEW_TASK",
  "onedrive_link": "https://company-my.sharepoint.com/.../workspace.zip",
  "prompt": "Hãy mở file workspace.zip, tìm file auth.py và sửa lỗi validate email.",
  "verify_command": "pytest tests/test_auth.py"
}

```

### Bước 3: Thao tác UI & Tự động hóa New Chat (Browser Extension)

Khi Extension nhận được yêu cầu từ CLI:

1. **New Chat:** Extension tìm và click nút **"New Topic" / "New Chat"** trên giao diện Copilot Web để đảm bảo sạch Context cho task mới.
2. **Ghép System Prompt chuẩn chuẩn bị tải file:**
```text
[SYSTEM INSTRUCTION]
Bạn là AI Software Engineer. Hãy đọc file mã nguồn tại link OneDrive sau:
[LINK_ONEDRIVE]

YÊU CẦU TASK:
[PROMPT_TỪ_USER]

QUY ĐỊNH KẾT QUẢ:
Sau khi hoàn thành, hãy tạo/xuất ra một file nén (.zip) chứa toàn bộ các file đã được chỉnh sửa (hoặc file mã nguồn hoàn chỉnh). Cung cấp nút TẢI VỀ (Download) cho file này.

```


3. **Dán link & Gửi:** Extension tự động điền prompt vào ô chat và nhấn **Send**.

### Bước 4: Tải File đã sửa về Thư mục Cố định (Browser Extension)

1. Extension lắng nghe DOM (`MutationObserver`) cho đến khi Copilot hoàn tất câu trả lời.
2. Extension tìm phần tử chứa nút **Download** hoặc file đính kèm được Copilot tạo ra trong câu trả lời.
3. Extension kích hoạt sự kiện click để tải file về thư mục Downloads cố định trên máy local (ví dụ: `C:\Users\<User>\Downloads\CopilotAgent\output.zip`).

### Bước 5: Thay thế File & Chạy Lệnh Verify (Python Local CLI)

1. Python CLI dùng `watchdog` hoặc vòng lặp theo dõi thư mục `Downloads/CopilotAgent/`.
2. Ngay khi có file `output.zip` mới:
* CLI giải nén và **copy ghi đè** trực tiếp vào thư mục Repo làm việc.
* CLI gọi `subprocess.run(verify_command, shell=True)` bằng Python.


3. **Kết quả:**
* **Thành công (Exit code = 0):** In thông báo thành công + `git diff` để bạn review.
* **Thất bại (Exit code != 0):** Bắt toàn bộ `stderr/stdout`, khởi tạo **Task mới (New Chat)** kèm theo log lỗi để gửi lại Copilot sửa tiếp.



---

## Bộ mã nguồn mẫu PoC (Proof of Concept)

Dưới đây là bộ khung mã nguồn tối giản bằng **Python** và **JavaScript (Chrome Extension)** để bạn có thể chạy thử ngay:

### 1. File Python Orchestrator (`agent.py`)

```python
import asyncio
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path
import websockets

# Cấu hình đường dẫn
REPO_PATH = Path("./my_project")
ONEDRIVE_SYNC_PATH = Path(os.path.expanduser("~/OneDrive - Business/CopilotWorkspace"))
DOWNLOAD_PATH = Path(os.path.expanduser("~/Downloads/CopilotAgent"))
ONEDRIVE_LINK = "https://your-company-my.sharepoint.com/.../workspace.zip"  # Link cố định của bạn

def zip_repo():
    """Nén các file trong repo vào thư mục OneDrive Sync"""
    zip_file = ONEDRIVE_SYNC_PATH / "workspace.zip"
    ONEDRIVE_SYNC_PATH.mkdir(parents=True, exist_ok=True)
    
    with zipfile.ZipFile(zip_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(REPO_PATH):
            # Bỏ qua folder không cần thiết
            dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', 'node_modules', '.venv']]
            for file in files:
                file_path = Path(root) / file
                arcname = file_path.relative_to(REPO_PATH)
                zipf.write(file_path, arcname)
    print(f"[CLI] Đã nén repo và lưu tại OneDrive Sync: {zip_file}")

def apply_downloaded_files():
    """Giải nén file từ thư mục Download và ghi đè vào Repo"""
    output_zip = DOWNLOAD_PATH / "output.zip"
    if output_zip.exists():
        with zipfile.ZipFile(output_zip, 'r') as zipf:
            zipf.extractall(REPO_PATH)
        print(f"[CLI] Đã ghi đè file mới vào {REPO_PATH}")
        output_zip.unlink() # Xóa file zip sau khi apply xong
        return True
    return False

def run_verify(command):
    """Thực thi lệnh verify bằng Python subprocess"""
    print(f"[CLI] Đang thực thi lệnh kiểm thử: {command}")
    result = subprocess.run(command, shell=True, capture_output=True, text=True, cwd=REPO_PATH)
    return result.returncode == 0, result.stdout + result.stderr

async def handle_client(websocket):
    print("[CLI] Chrome Extension đã kết nối WebSocket!")
    
    task_prompt = "Hãy sửa hàm validate_email trong file auth.py để chấp nhận domain .vn"
    verify_cmd = "python -m unittest discover"

    # Bước 1: Zip & Sync
    zip_repo()
    
    # Bước 2: Gửi Yêu cầu sang Extension
    payload = {
        "action": "START_TASK",
        "onedrive_link": ONEDRIVE_LINK,
        "prompt": task_prompt,
    }
    await websocket.send(json.dumps(payload))
    print("[CLI] Đã gửi task sang Extension. Đang chờ Copilot xử lý...")

    # Bước 3: Lắng nghe phản hồi từ Extension khi file đã được download xong
    async for message in websocket:
        data = json.loads(message)
        if data.get("status") == "FILE_DOWNLOADED":
            print("[CLI] Extension báo file đã tải xong. Tiến hành apply & verify...")
            
            # Bước 4: Apply file & Verify
            if apply_downloaded_files():
                success, logs = run_verify(verify_cmd)
                if success:
                    print("[CLI] SUCCESS: Task hoàn thành xuất sắc!")
                else:
                    print(f"[CLI] FAILED: Verify thất bại. Log:\n{logs}")
                    # Tại đây bạn có thể tự động gửi lại task mới kèm theo `logs`
            break

async def main():
    DOWNLOAD_PATH.mkdir(parents=True, exist_ok=True)
    async with websockets.serve(handle_client, "localhost", 8765):
        print("[CLI] WebSocket Server đang chạy tại ws://localhost:8765")
        await asyncio.Future() # Chạy mãi mãi

if __name__ == "__main__":
    asyncio.run(main())

```

---

### 2. File Chrome Extension (`content.js`)

*(File này sẽ tự động hóa thao tác trên tab M365 Copilot Chat)*

```javascript
// Kết nối tới Python CLI
const socket = new WebSocket('ws://localhost:8765');

socket.onopen = () => {
    console.log('[Copilot Agent Extension] Đã kết nối tới Local Python CLI');
};

socket.onmessage = async (event) => {
    const data = JSON.parse(event.data);
    if (data.action === 'START_TASK') {
        console.log('[Extension] Bắt đầu thực thi Task...');
        await executeCopilotTask(data.onedrive_link, data.prompt);
    }
};

async function executeCopilotTask(onedriveLink, userPrompt) {
    // 1. Click nút "New Chat" / "New Topic"
    const newChatBtn = document.querySelector('button[aria-label="New topic"]') || document.querySelector('.new-topic-button');
    if (newChatBtn) {
        newChatBtn.click();
        await new Promise(r => setTimeout(r, 2000)); // Chờ 2s để reset chat
    }

    // 2. Chuẩn bị Prompt
    const fullPrompt = `[SYSTEM: Đọc file zip từ OneDrive tại link: ${onedriveLink}. Sau khi sửa code xong, hãy tạo file nén output.zip chứa các file đã sửa và cung cấp nút Download.]\n\nYÊU CẦU: ${userPrompt}`;

    // 3. Điền vào khung Chat và Nhấn Send
    const chatInput = document.querySelector('textarea') || document.querySelector('[contenteditable="true"]');
    if (chatInput) {
        chatInput.value = fullPrompt;
        chatInput.dispatchEvent(new Event('input', { bubbles: true }));

        const sendBtn = document.querySelector('button[aria-label="Submit"]') || document.querySelector('button[title="Send"]');
        if (sendBtn) sendBtn.click();
    }

    // 4. Theo dõi câu trả lời và tự động click Download khi hoàn tất
    observeResponseAndDownload();
}

function observeResponseAndDownload() {
    const observer = new MutationObserver((mutations, obs) => {
        // Tìm nút Download trong khối câu trả lời của Copilot
        const downloadBtn = document.querySelector('a[download]') || document.querySelector('button[title*="Download"]');
        const isStopBtnVisible = document.querySelector('button[aria-label*="Stop"]'); // Nút Stop gõ text

        if (downloadBtn && !isStopBtnVisible) {
            console.log('[Extension] Phát hiện file output! Đang kích hoạt download...');
            downloadBtn.click(); // Click tải file về folder Downloads
            
            obs.disconnect(); // Dừng quan sát

            // Báo lại cho Python CLI sau 3s (chờ browser hoàn tất ghi file)
            setTimeout(() => {
                socket.send(JSON.stringify({ status: 'FILE_DOWNLOADED' }));
            }, 3000);
        }
    });

    observer.observe(document.body, { childList: true, subtree: true });
}

```
