# Design Specification: M365 Copilot Web Agent PoC

## 1. Overview
The goal of this Proof of Concept (PoC) is to build an automated AI Coding Agent loop using Microsoft 365 Copilot Web. The architecture leverages a local Python CLI (`agent.py`) working in tandem with an unpacked Manifest v3 Chrome Extension (`extension/`).

Instead of parsing raw text/code snippets from chat responses, Copilot Web is instructed to output complete modified project files inside a `.zip` archive with a download link. The Chrome Extension automates browser interactions (New Chat, Model Selection, Prompt Injection, Download detection), while the Python CLI packages the repository, listens for output files, overwrites local code, and runs automated tests.

---

## 2. System Architecture & Component Responsibilities

```text
[Local Workspace Repo] ◄──── (Unzip & Overwrite) ──── [Python CLI: agent.py]
                                                             │
                                                   (WebSocket ws://localhost:8765)
                                                             ▼
[M365 Copilot Web Tab] ◄──── (DOM Automation) ────── [Chrome Extension]
  (Chrome Browser)                                        ├─ content.js (DOM Inspector & Actions)
                                                          └─ background.js (WebSocket Client & chrome.downloads)
```

### 2.1 Python CLI (`agent.py`)
- **WebSocket Server:** Runs on `ws://localhost:8765`.
- **Zip & Sync:** Packages the current workspace files into `workspace.zip` in the designated sync directory.
- **Task Dispatcher:** Sends JSON payload containing task instructions, model preference, and OneDrive zip link to Chrome Extension.
- **Extractor & Verifier:** Monitors the browser `Downloads/CopilotAgent/` directory for `output.zip`, extracts and overwrites project files, then executes `pytest` or `python -m unittest`.

### 2.2 Chrome Extension (`extension/`)
- **`manifest.json`:** Manifest v3 specifying host permissions for `https://copilot.microsoft.com/*`, `https://*.cloud.microsoft/*`, `downloads`, `storage`, and `activeTab`.
- **`background.js` (Service Worker):**
  - Maintains persistent WebSocket connection to `ws://localhost:8765`.
  - Uses `chrome.downloads.download()` to download output `.zip` files reliably without browser prompt blocks.
  - Relays download completion events back to `agent.py`.
- **`content.js` (DOM Automation):**
  - Injected directly into the M365 Copilot Web tab.
  - Controls DOM element interaction sequence.
  - Observes Copilot response output using `MutationObserver` to find download URLs.

---

## 3. Empirical DOM Selectors (M365 Copilot Web UI)

Based on live DOM inspection of Fluent UI React components on M365 Copilot Web:

| UI Component | Verified Selector / Strategy |
| :--- | :--- |
| **New Chat Button** | `button[aria-label*="New"]` / `button[aria-label="New topic"]` |
| **Model Selector** | `button#gptModeSwitcher` / `button[aria-label="Model Selector"]` |
| **Chat Input** | `span#m365-chat-editor-target-element` (or child `div[contenteditable="true"]`) |
| **Send Button** | `button[aria-label="Send"]` or `button.fai-SendButton` |
| **Download Links** | `a[download]`, `a[href*=".zip"]`, or buttons containing download icons inside chat response blocks |

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
  "status": "CLICKED_NEW_CHAT" // Options: CREATING_CHAT | MODEL_SELECTED | PROMPT_SENT | WAITING_RESPONSE | DOWNLOADING | ERROR
}
```

### 4.3 Extension ➔ CLI: `TASK_COMPLETE`
```json
{
  "event": "TASK_COMPLETE",
  "status": "FILE_DOWNLOADED",
  "filename": "output.zip"
}
```

---

## 5. End-to-End Workflow Sequence

1. **Start CLI:** User runs `python agent.py`. WebSocket server starts listening on `ws://localhost:8765`.
2. **Repo Packaging:** CLI zips workspace files to `workspace.zip`.
3. **Task Broadcast:** CLI sends `START_TASK` message via WebSocket to Extension.
4. **New Chat:** `content.js` clicks `button[aria-label*="New"]` to reset chat context. Wait 1.5s.
5. **Model Selection:** `content.js` clicks `button#gptModeSwitcher`, selects model matching payload `"model"` field (if specified).
6. **Prompt Delivery:**
   - Focus `span#m365-chat-editor-target-element`.
   - Insert system prompt + OneDrive link + user prompt.
   - Dispatch `input` and `change` events.
   - Click `button[aria-label="Send"]`.
7. **Response & Download Observation:**
   - `content.js` uses `MutationObserver` to watch chat response container.
   - Once output file link/button is rendered and generation stops, `content.js` passes download URL to `background.js`.
   - `background.js` executes `chrome.downloads.download({ url: downloadUrl, filename: "CopilotAgent/output.zip" })`.
8. **Extraction & Verification:**
   - `background.js` notifies `agent.py` upon download completion.
   - `agent.py` extracts `output.zip` into workspace repo, overwriting modified files.
   - `agent.py` runs verification command (`python -m unittest discover` or `pytest`).
   - CLI prints result logs and displays `git diff`.

---

## 6. Verification & Test Plan

1. **Unit Test for Packaging/Unzipping (`agent.py`):** Test zipping local sample files and unzipping mock output zips.
2. **WebSocket Communication Test:** Verify bi-directional JSON messaging between Python WebSocket server and Chrome Extension Service Worker.
3. **Live DOM Interaction Test:** Test Chrome Extension automation sequence (New Chat -> Select Model -> Paste Prompt -> Click Send -> Detect Output Link) on an active M365 Copilot Web session.
