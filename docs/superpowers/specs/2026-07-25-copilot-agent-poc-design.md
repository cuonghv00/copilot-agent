# Design Specification: M365 Copilot Web Agent PoC

## 1. Overview

Build an automated AI Coding Agent loop using Microsoft 365 Copilot Web. A local Python CLI (`agent.py`) orchestrates tasks while an unpacked Manifest v3 Chrome Extension (`extension/`) automates browser interactions.

**Core idea:** Instead of parsing raw text/code snippets from chat responses, Copilot Web is instructed to output complete modified project files inside a `.zip` archive with a download link. This eliminates indentation, import, and escape character errors from text parsing.

---

## 2. System Architecture & Component Responsibilities

```text
[Local Workspace Repo] ◄──── (Unzip & Overwrite) ──── [Python CLI: agent.py]
                                                             │
                                                   (WebSocket ws://localhost:8765)
                                                             ▼
[M365 Copilot Web Tab] ◄──── (DOM Automation) ────── [Chrome Extension]
  (Chrome Browser)                                        ├─ content.js (DOM Observer & Actions)
                                                          └─ background.js (WebSocket Client & chrome.downloads)
```

### 2.1 Python CLI (`agent.py`)

- **WebSocket Server:** Runs on `ws://localhost:8765`.
- **Zip & Sync:** Packages workspace files into `workspace.zip`, saves to configurable sync directory (OneDrive local sync folder or any designated path).
- **Task Dispatcher:** Sends JSON payload (task instructions, model preference, OneDrive link) to Chrome Extension via WebSocket.
- **Extractor & Verifier:** Receives `FILE_DOWNLOADED` notification from Extension via WebSocket, then extracts `output.zip` from `Downloads/CopilotAgent/` directory, overwrites project files, and runs verification command (`pytest` / `python -m unittest`).

### 2.2 Chrome Extension (`extension/`)

- **`manifest.json`:** Manifest v3 with permissions: `downloads`, `storage`, `activeTab`, `tabs`. Host permissions for `https://m365.cloud.microsoft/*` and `https://copilot.microsoft.com/*`.
- **`background.js` (Service Worker):**
  - Maintains WebSocket connection to `ws://localhost:8765`.
  - Navigates to Copilot chat URL via `chrome.tabs.update()` to create new chat sessions.
  - Uses `chrome.downloads.download()` to save output `.zip` files reliably (bypasses browser download prompts).
  - Relays download completion events back to `agent.py` via WebSocket.
- **`content.js` (DOM Automation):**
  - Injected into M365 Copilot Web tab.
  - Handles: Model Selection → Prompt Input → Send → Response Observation.
  - Uses `MutationObserver` to detect when Copilot finishes generating and find download URLs.

---

## 3. Verified DOM Selectors (M365 Copilot Web UI)

Based on live DOM inspection (Fluent UI React / Bebop components):

| UI Component | Verified Selector | Notes |
| :--- | :--- | :--- |
| **New Chat** | **No button exists.** Use URL navigation: `chrome.tabs.update(tabId, { url: BASE_COPILOT_URL })` from `background.js` | M365 Copilot Web does not expose a "New Chat" button in the DOM |
| **Model Selector** | `button#gptModeSwitcher` or `button[aria-label="Model Selector"]` | Opens a dropdown/popup menu with model options |
| **Model Menu Items** | After clicking Model Selector, find menu items by matching `innerText` against desired model name (e.g., "Think", "GPT-4") | Menu items rendered dynamically; select by text content |
| **Chat Input** | `span#m365-chat-editor-target-element` (Fluent UI rich text editor) | **Not a `<textarea>`.** Must use `document.execCommand('insertText', false, text)` or dispatch `InputEvent` with `inputType: 'insertText'` after focusing the element |
| **Send Button** | `button[aria-label="Send"]` or `button.fai-SendButton` | Located inside the chat input container |
| **Temporary Chat** | `button[aria-label="Temporary chat"]` | Toggle for ephemeral chat mode (optional use) |
| **Download Links** | `a[download]`, `a[href*=".zip"]`, or buttons with download icons inside response blocks | **Not yet verified at runtime** — Copilot's output format for file downloads needs live testing |

---

## 4. WebSocket Payload Protocol

### 4.1 CLI ➔ Extension: `START_TASK`

```json
{
  "action": "START_TASK",
  "onedrive_link": "https://company-my.sharepoint.com/.../workspace.zip",
  "model": "Think",
  "prompt": "Sửa hàm validate_email trong file auth.py để chấp nhận domain .vn",
  "system_instruction": "Bạn là AI Software Engineer. Hãy đọc file mã nguồn tại link OneDrive sau, thực hiện yêu cầu, và xuất kết quả ra file zip tên output.zip kèm nút Download."
}
```

### 4.2 Extension ➔ CLI: `STATUS_UPDATE`

```json
{
  "event": "STATUS_UPDATE",
  "status": "NAVIGATING_NEW_CHAT",
  "message": "Navigating to new chat URL..."
}
```

Status values: `NAVIGATING_NEW_CHAT` | `PAGE_READY` | `MODEL_SELECTED` | `PROMPT_SENT` | `WAITING_RESPONSE` | `DOWNLOADING` | `ERROR`

### 4.3 Extension ➔ CLI: `TASK_COMPLETE`

```json
{
  "event": "TASK_COMPLETE",
  "status": "FILE_DOWNLOADED",
  "filename": "output.zip"
}
```

### 4.4 Extension ➔ CLI: `ERROR`

```json
{
  "event": "ERROR",
  "status": "ERROR",
  "message": "Model Selector button not found after 10s timeout",
  "step": "MODEL_SELECTION"
}
```

---

## 5. End-to-End Workflow Sequence

1. **Start CLI:** User runs `python agent.py`. WebSocket server starts on `ws://localhost:8765`.
2. **Repo Packaging:** CLI zips workspace files to `workspace.zip` in sync directory.
3. **Task Dispatch:** CLI sends `START_TASK` message via WebSocket to Extension.
4. **New Chat (background.js):** `background.js` navigates the Copilot tab to the base chat URL using `chrome.tabs.update()`. Waits for page load via `chrome.tabs.onUpdated` listener.
5. **Model Selection (content.js):** Clicks `button#gptModeSwitcher`, waits for dropdown to appear, selects the menu item matching the `"model"` field by text content.
6. **Prompt Delivery (content.js):**
   - Focus `span#m365-chat-editor-target-element`.
   - Use `document.execCommand('insertText', false, fullPrompt)` to inject text into the Fluent UI rich text editor (ensures React state picks up the change).
   - Click `button[aria-label="Send"]`.
7. **Response & Download Observation (content.js → background.js):**
   - `content.js` attaches `MutationObserver` to the chat response container.
   - Detects when Copilot stops generating (no more DOM mutations for N seconds, or stop button disappears).
   - Finds download link (`a[download]`, `a[href*=".zip"]`) and sends URL to `background.js` via `chrome.runtime.sendMessage()`.
   - `background.js` calls `chrome.downloads.download({ url, filename: "CopilotAgent/output.zip" })`.
8. **Extraction & Verification (agent.py):**
   - `background.js` notifies `agent.py` via WebSocket with `TASK_COMPLETE` event upon download completion.
   - `agent.py` extracts `output.zip` into workspace repo, overwriting modified files.
   - `agent.py` runs verification command (`pytest` or `python -m unittest discover`).
   - **Success (exit code 0):** Print success message + `git diff` for review.
   - **Failure (exit code ≠ 0):** Capture stdout/stderr, optionally trigger a new task cycle with error logs appended to prompt.

---

## 6. Error Handling & Edge Cases

| Scenario | Handling |
| :--- | :--- |
| WebSocket disconnected | Extension retries connection every 5s with exponential backoff (max 30s) |
| DOM selector not found | Retry with 2s interval, max 5 attempts. Send `ERROR` event to CLI after exhausting retries |
| Copilot response has no download link | Send `ERROR` with `message: "No download link found in response"`. CLI can retry with modified prompt |
| Download fails | `chrome.downloads.onChanged` listener detects failure state, sends `ERROR` to CLI |
| Verification fails (exit ≠ 0) | CLI logs error output. Optionally auto-retries by sending new task with error context appended |

---

## 7. File Structure

```text
copilot-agent/
├── idea.md                    # Original idea document
├── agent.py                   # Python CLI: WebSocket Server, Zip, Unzip, Verify
├── config.json                # Configurable paths and settings
├── extension/
│   ├── manifest.json          # Chrome Extension Manifest v3
│   ├── background.js          # Service Worker: WebSocket Client, chrome.downloads, tab navigation
│   └── content.js             # DOM Automation: Model Select, Prompt Input, Send, MutationObserver
└── docs/
    └── superpowers/
        └── specs/
            └── 2026-07-25-copilot-agent-poc-design.md  # This file
```

---

## 8. Configuration (`config.json`)

```json
{
  "repo_path": "./my_project",
  "sync_path": "~/OneDrive/CopilotWorkspace",
  "download_path": "~/Downloads/CopilotAgent",
  "onedrive_link": "https://company-my.sharepoint.com/.../workspace.zip",
  "copilot_base_url": "https://m365.cloud.microsoft/chat",
  "websocket_port": 8765,
  "default_model": "Think",
  "verify_command": "python -m unittest discover",
  "max_retry_on_failure": 3,
  "zip_exclude_dirs": [".git", "__pycache__", "node_modules", ".venv"]
}
```

---

## 9. Browser Compatibility Note

- **Target browser:** Google Chrome (Manifest v3 Chrome Extension).
- DOM selectors were verified on Firefox accessing M365 Copilot Web. Fluent UI component selectors (`#gptModeSwitcher`, `#m365-chat-editor-target-element`, `button[aria-label="Send"]`) are framework-generated and should be consistent across browsers.
- The Chrome Extension uses Chrome-specific APIs (`chrome.downloads`, `chrome.tabs`, `chrome.runtime`) which are not compatible with Firefox. A Firefox WebExtension port would require using the `browser.*` namespace.

---

## 10. Known Risks & Open Questions

1. **Copilot file output format:** It is unverified whether M365 Copilot Web consistently generates downloadable `.zip` files when instructed. The prompt engineering for this is critical and may need iteration.
2. **DOM selector stability:** M365 Copilot Web UI updates frequently. Selectors like `#gptModeSwitcher` may change without notice. The Extension should log warnings when selectors fail to match.
3. **Rate limiting:** Rapid automated interactions may trigger Microsoft's anti-bot protections. Adding human-like delays (randomized 1-3s between actions) is recommended.
4. **OneDrive link accessibility:** The shared OneDrive link must be accessible to Copilot. Verify that Copilot can read files from OneDrive links in the chat context.
