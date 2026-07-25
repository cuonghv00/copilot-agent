# M365 Copilot Web Agent PoC — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working PoC that automates the loop: zip local repo → send task to M365 Copilot Web via Chrome Extension → auto-download output zip → extract and verify.

**Architecture:** Python CLI (`agent.py`) runs a WebSocket server and handles file packaging/extraction/verification. A Chrome Manifest v3 Extension connects to the CLI via WebSocket, automates DOM interactions on M365 Copilot Web (model selection, prompt input, send, download detection), and triggers file downloads via `chrome.downloads` API.

**Tech Stack:** Python 3.10+ (websockets, zipfile, subprocess, json, pathlib), Chrome Extension Manifest v3 (Service Worker, Content Script, chrome.downloads API, chrome.tabs API)

## Global Constraints

- Python dependency: `websockets` library only (no other third-party deps for PoC)
- Chrome Extension: Manifest v3 only (no Manifest v2)
- All configurable paths go in `config.json` at project root
- DOM selectors verified on M365 Copilot Web (Fluent UI / Bebop): `button#gptModeSwitcher`, `span#m365-chat-editor-target-element`, `button[aria-label="Send"]`
- New Chat strategy: URL navigation via `chrome.tabs.update()` (no "New Chat" button exists)
- Text input into Copilot editor: `document.execCommand('insertText')` (not `.value` or `.textContent`)
- WebSocket port: `8765`

---

### Task 1: Project Scaffolding & Configuration

**Files:**
- Create: `config.json`
- Create: `agent.py` (skeleton only)
- Create: `extension/manifest.json`
- Create: `extension/background.js` (skeleton only)
- Create: `extension/content.js` (skeleton only)

**Interfaces:**
- Consumes: Nothing (first task)
- Produces: `config.json` schema used by `agent.py`; `manifest.json` consumed by Chrome

- [ ] **Step 1: Create `config.json`**

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

- [ ] **Step 2: Create `extension/manifest.json`**

```json
{
  "manifest_version": 3,
  "name": "Copilot Agent",
  "version": "0.1.0",
  "description": "Automates M365 Copilot Web for AI coding agent loop",
  "permissions": [
    "downloads",
    "storage",
    "activeTab",
    "tabs"
  ],
  "host_permissions": [
    "https://m365.cloud.microsoft/*",
    "https://copilot.microsoft.com/*"
  ],
  "background": {
    "service_worker": "background.js"
  },
  "content_scripts": [
    {
      "matches": [
        "https://m365.cloud.microsoft/*",
        "https://copilot.microsoft.com/*"
      ],
      "js": ["content.js"],
      "run_at": "document_idle"
    }
  ]
}
```

- [ ] **Step 3: Create skeleton `extension/background.js`**

```javascript
// background.js — Service Worker
// Handles: WebSocket connection to Python CLI, chrome.downloads, tab navigation
console.log('[CopilotAgent] Background service worker loaded');
```

- [ ] **Step 4: Create skeleton `extension/content.js`**

```javascript
// content.js — DOM Automation
// Handles: Model selection, prompt input, send, MutationObserver for response
console.log('[CopilotAgent] Content script loaded on', window.location.href);
```

- [ ] **Step 5: Create skeleton `agent.py`**

```python
#!/usr/bin/env python3
"""Copilot Agent CLI — WebSocket server, repo packaging, verification."""
import json
from pathlib import Path

def load_config():
    """Load configuration from config.json."""
    config_path = Path(__file__).parent / "config.json"
    with open(config_path) as f:
        return json.load(f)

if __name__ == "__main__":
    config = load_config()
    print(f"[CLI] Config loaded: WebSocket port {config['websocket_port']}")
```

- [ ] **Step 6: Verify Extension loads in Chrome**

1. Open `chrome://extensions/`
2. Enable "Developer mode"
3. Click "Load unpacked" and select the `extension/` directory
4. Verify no errors in the extension card
5. Open `https://m365.cloud.microsoft/chat` and check browser console for `[CopilotAgent] Content script loaded`

- [ ] **Step 7: Commit**

```bash
git add config.json agent.py extension/
git commit -m "feat: project scaffolding with config, extension manifest, and skeletons"
```

---

### Task 2: Python CLI — Zip & Config Utilities

**Files:**
- Modify: `agent.py`
- Create: `tests/test_agent.py`

**Interfaces:**
- Consumes: `config.json` schema from Task 1
- Produces: `zip_repo(repo_path: Path, output_path: Path, exclude_dirs: list[str]) -> Path` — returns path to created zip file. `load_config() -> dict` — returns parsed config dictionary.

- [ ] **Step 1: Write failing tests for `zip_repo` and `load_config`**

Create `tests/test_agent.py`:

```python
import json
import os
import tempfile
import zipfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_load_config():
    """load_config returns a dict with expected keys."""
    from agent import load_config
    config = load_config()
    assert isinstance(config, dict)
    assert "repo_path" in config
    assert "websocket_port" in config
    assert config["websocket_port"] == 8765

def test_zip_repo_creates_zip():
    """zip_repo creates a valid zip file from a directory."""
    from agent import zip_repo
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a fake repo
        repo = Path(tmpdir) / "repo"
        repo.mkdir()
        (repo / "main.py").write_text("print('hello')")
        (repo / "utils.py").write_text("def add(a, b): return a + b")
        sub = repo / "src"
        sub.mkdir()
        (sub / "core.py").write_text("# core module")

        output = Path(tmpdir) / "output"
        output.mkdir()

        result = zip_repo(repo, output / "workspace.zip", [])
        assert result.exists()
        assert result.name == "workspace.zip"

        with zipfile.ZipFile(result) as zf:
            names = zf.namelist()
            assert "main.py" in names
            assert "utils.py" in names
            assert "src/core.py" in names

def test_zip_repo_excludes_dirs():
    """zip_repo skips directories listed in exclude_dirs."""
    from agent import zip_repo
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir) / "repo"
        repo.mkdir()
        (repo / "app.py").write_text("# app")
        git_dir = repo / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("# git config")
        cache_dir = repo / "__pycache__"
        cache_dir.mkdir()
        (cache_dir / "app.cpython-310.pyc").write_bytes(b"\x00")

        output = Path(tmpdir) / "output"
        output.mkdir()

        result = zip_repo(repo, output / "workspace.zip", [".git", "__pycache__"])
        with zipfile.ZipFile(result) as zf:
            names = zf.namelist()
            assert "app.py" in names
            assert not any(".git" in n for n in names)
            assert not any("__pycache__" in n for n in names)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_agent.py -v`
Expected: FAIL with `ImportError` or `AttributeError` (zip_repo not defined)

- [ ] **Step 3: Implement `zip_repo` in `agent.py`**

```python
#!/usr/bin/env python3
"""Copilot Agent CLI — WebSocket server, repo packaging, verification."""
import json
import os
import zipfile
from pathlib import Path


def load_config():
    """Load configuration from config.json."""
    config_path = Path(__file__).parent / "config.json"
    with open(config_path) as f:
        return json.load(f)


def zip_repo(repo_path: Path, output_zip: Path, exclude_dirs: list[str]) -> Path:
    """Zip all files in repo_path into output_zip, excluding specified directories.

    Args:
        repo_path: Path to the repository directory to zip.
        output_zip: Path where the zip file will be created.
        exclude_dirs: List of directory names to skip (e.g., ['.git', '__pycache__']).

    Returns:
        Path to the created zip file.
    """
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for file in files:
                file_path = Path(root) / file
                arcname = file_path.relative_to(repo_path)
                zipf.write(file_path, arcname)
    return output_zip


if __name__ == "__main__":
    config = load_config()
    print(f"[CLI] Config loaded: WebSocket port {config['websocket_port']}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_agent.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add agent.py tests/test_agent.py
git commit -m "feat: implement zip_repo and load_config with tests"
```

---

### Task 3: Python CLI — Extract & Verify Utilities

**Files:**
- Modify: `agent.py`
- Modify: `tests/test_agent.py`

**Interfaces:**
- Consumes: `load_config()` from Task 2
- Produces: `extract_zip(zip_path: Path, target_dir: Path) -> bool` — extracts zip, returns True on success. `run_verify(command: str, cwd: Path) -> tuple[bool, str]` — runs shell command, returns (success, combined_output).

- [ ] **Step 1: Write failing tests for `extract_zip` and `run_verify`**

Append to `tests/test_agent.py`:

```python
def test_extract_zip():
    """extract_zip extracts files into target directory."""
    from agent import extract_zip
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a zip to extract
        zip_path = Path(tmpdir) / "output.zip"
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr("fixed_file.py", "print('fixed')")
            zf.writestr("src/module.py", "# fixed module")

        target = Path(tmpdir) / "repo"
        target.mkdir()

        result = extract_zip(zip_path, target)
        assert result is True
        assert (target / "fixed_file.py").read_text() == "print('fixed')"
        assert (target / "src" / "module.py").read_text() == "# fixed module"


def test_extract_zip_cleans_up():
    """extract_zip deletes the zip file after extraction."""
    from agent import extract_zip
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = Path(tmpdir) / "output.zip"
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr("file.py", "content")

        target = Path(tmpdir) / "repo"
        target.mkdir()

        extract_zip(zip_path, target)
        assert not zip_path.exists()


def test_run_verify_success():
    """run_verify returns (True, output) when command succeeds."""
    from agent import run_verify
    with tempfile.TemporaryDirectory() as tmpdir:
        success, output = run_verify("echo 'hello world'", Path(tmpdir))
        assert success is True
        assert "hello world" in output


def test_run_verify_failure():
    """run_verify returns (False, output) when command fails."""
    from agent import run_verify
    with tempfile.TemporaryDirectory() as tmpdir:
        success, output = run_verify("exit 1", Path(tmpdir))
        assert success is False
```

- [ ] **Step 2: Run tests to verify new tests fail**

Run: `python -m pytest tests/test_agent.py -v -k "extract or verify"`
Expected: FAIL with `ImportError` (extract_zip, run_verify not defined)

- [ ] **Step 3: Implement `extract_zip` and `run_verify` in `agent.py`**

Add these functions after `zip_repo` in `agent.py`:

```python
import subprocess


def extract_zip(zip_path: Path, target_dir: Path) -> bool:
    """Extract a zip file into target_dir and delete the zip afterwards.

    Args:
        zip_path: Path to the zip file to extract.
        target_dir: Directory to extract files into.

    Returns:
        True if extraction succeeded, False otherwise.
    """
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(target_dir)
        zip_path.unlink()
        return True
    except (zipfile.BadZipFile, OSError) as e:
        print(f"[CLI] Extract error: {e}")
        return False


def run_verify(command: str, cwd: Path) -> tuple[bool, str]:
    """Run a shell command and return (success, combined_output).

    Args:
        command: Shell command string to execute.
        cwd: Working directory for the command.

    Returns:
        Tuple of (success: bool, output: str).
    """
    result = subprocess.run(
        command, shell=True, capture_output=True, text=True, cwd=cwd
    )
    combined = result.stdout + result.stderr
    return result.returncode == 0, combined
```

- [ ] **Step 4: Run all tests to verify they pass**

Run: `python -m pytest tests/test_agent.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add agent.py tests/test_agent.py
git commit -m "feat: implement extract_zip and run_verify with tests"
```

---

### Task 4: Python CLI — WebSocket Server

**Files:**
- Modify: `agent.py`

**Interfaces:**
- Consumes: `load_config()`, `zip_repo()`, `extract_zip()`, `run_verify()` from Tasks 2-3
- Produces: WebSocket server on `ws://localhost:8765` that accepts Extension connections, sends `START_TASK` JSON, and listens for `STATUS_UPDATE` / `TASK_COMPLETE` / `ERROR` events.

- [ ] **Step 1: Implement the WebSocket server and main orchestration loop**

Add to `agent.py`, replacing the `if __name__` block:

```python
import asyncio
import websockets


async def handle_task(websocket, config):
    """Handle a single task lifecycle with the Chrome Extension."""
    repo_path = Path(config["repo_path"]).expanduser().resolve()
    sync_path = Path(config["sync_path"]).expanduser().resolve()
    download_path = Path(config["download_path"]).expanduser().resolve()

    # Step 1: Zip the repo
    print("[CLI] Zipping repository...")
    zip_output = sync_path / "workspace.zip"
    zip_repo(repo_path, zip_output, config["zip_exclude_dirs"])
    print(f"[CLI] Repo zipped to {zip_output}")

    # Step 2: Wait for user prompt input
    prompt = input("[CLI] Enter task prompt (or press Enter for default): ").strip()
    if not prompt:
        prompt = "Review the codebase and fix any bugs you find."

    model = input(f"[CLI] Enter model name (default: {config['default_model']}): ").strip()
    if not model:
        model = config["default_model"]

    # Step 3: Send START_TASK to Extension
    payload = {
        "action": "START_TASK",
        "onedrive_link": config["onedrive_link"],
        "model": model,
        "prompt": prompt,
        "system_instruction": (
            "Bạn là AI Software Engineer. Hãy đọc file mã nguồn tại link OneDrive sau, "
            "thực hiện yêu cầu, và xuất kết quả ra file zip tên output.zip kèm nút Download."
        ),
    }
    await websocket.send(json.dumps(payload))
    print("[CLI] Task sent to Extension. Waiting for Copilot to process...")

    # Step 4: Listen for status updates and completion
    async for message in websocket:
        data = json.loads(message)
        event = data.get("event", "")
        status = data.get("status", "")

        if event == "STATUS_UPDATE":
            print(f"[CLI] Status: {status} — {data.get('message', '')}")

        elif event == "TASK_COMPLETE" and status == "FILE_DOWNLOADED":
            filename = data.get("filename", "output.zip")
            print(f"[CLI] File downloaded: {filename}. Applying changes...")

            zip_file = download_path / filename
            if extract_zip(zip_file, repo_path):
                print("[CLI] Changes applied to repo.")
                success, output = run_verify(config["verify_command"], repo_path)
                if success:
                    print("[CLI] ✅ Verification PASSED!")
                    # Show git diff
                    _, diff = run_verify("git diff", repo_path)
                    if diff.strip():
                        print(f"[CLI] Changes:\n{diff}")
                else:
                    print(f"[CLI] ❌ Verification FAILED:\n{output}")
            else:
                print("[CLI] ❌ Failed to extract downloaded file.")
            break

        elif event == "ERROR":
            print(f"[CLI] ❌ Error at step '{data.get('step', '?')}': {data.get('message', '')}")
            break


async def main():
    """Start WebSocket server and wait for Extension to connect."""
    config = load_config()
    download_path = Path(config["download_path"]).expanduser()
    download_path.mkdir(parents=True, exist_ok=True)

    port = config["websocket_port"]
    print(f"[CLI] Starting WebSocket server on ws://localhost:{port}")
    print("[CLI] Waiting for Chrome Extension to connect...")

    async with websockets.serve(
        lambda ws: handle_task(ws, config), "localhost", port
    ):
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Test manually — start the server**

Run: `python agent.py`
Expected output:
```
[CLI] Starting WebSocket server on ws://localhost:8765
[CLI] Waiting for Chrome Extension to connect...
```
Verify the server starts without errors and listens on port 8765.

- [ ] **Step 3: Commit**

```bash
git add agent.py
git commit -m "feat: implement WebSocket server and task orchestration loop"
```

---

### Task 5: Chrome Extension — Background Service Worker (WebSocket + Downloads)

**Files:**
- Modify: `extension/background.js`

**Interfaces:**
- Consumes: WebSocket messages from `agent.py` (Task 4) with `START_TASK` action
- Produces: 
  - Forwards `START_TASK` payload to content script via `chrome.tabs.sendMessage(tabId, payload)`
  - Navigates Copilot tab to base URL via `chrome.tabs.update()`
  - Downloads files via `chrome.downloads.download()`
  - Sends `TASK_COMPLETE` / `ERROR` events back to `agent.py` via WebSocket

- [ ] **Step 1: Implement `extension/background.js`**

```javascript
// background.js — Service Worker
// Responsibilities: WebSocket ↔ Python CLI, chrome.downloads, tab navigation

let ws = null;
let copilotTabId = null;
const WS_URL = 'ws://localhost:8765';
const COPILOT_BASE_URL = 'https://m365.cloud.microsoft/chat';

// --- WebSocket Connection ---

function connectWebSocket() {
    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
        console.log('[CopilotAgent BG] Connected to Python CLI');
    };

    ws.onmessage = async (event) => {
        const data = JSON.parse(event.data);
        console.log('[CopilotAgent BG] Received:', data);

        if (data.action === 'START_TASK') {
            await handleStartTask(data);
        }
    };

    ws.onclose = () => {
        console.log('[CopilotAgent BG] WebSocket disconnected. Reconnecting in 5s...');
        setTimeout(connectWebSocket, 5000);
    };

    ws.onerror = (err) => {
        console.error('[CopilotAgent BG] WebSocket error:', err);
        ws.close();
    };
}

function sendToServer(payload) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(payload));
    } else {
        console.error('[CopilotAgent BG] WebSocket not connected');
    }
}

// --- Task Handling ---

async function handleStartTask(taskData) {
    // Step 1: Find or create Copilot tab
    sendToServer({ event: 'STATUS_UPDATE', status: 'NAVIGATING_NEW_CHAT', message: 'Navigating to new chat...' });

    const tabs = await chrome.tabs.query({ url: ['https://m365.cloud.microsoft/*', 'https://copilot.microsoft.com/*'] });

    if (tabs.length > 0) {
        copilotTabId = tabs[0].id;
        await chrome.tabs.update(copilotTabId, { url: COPILOT_BASE_URL, active: true });
    } else {
        const tab = await chrome.tabs.create({ url: COPILOT_BASE_URL, active: true });
        copilotTabId = tab.id;
    }

    // Step 2: Wait for page to load, then send task to content script
    chrome.tabs.onUpdated.addListener(function listener(tabId, changeInfo) {
        if (tabId === copilotTabId && changeInfo.status === 'complete') {
            chrome.tabs.onUpdated.removeListener(listener);

            // Small delay to let Copilot UI fully render
            setTimeout(() => {
                sendToServer({ event: 'STATUS_UPDATE', status: 'PAGE_READY', message: 'Copilot page loaded' });
                chrome.tabs.sendMessage(copilotTabId, {
                    type: 'EXECUTE_TASK',
                    ...taskData
                });
            }, 3000);
        }
    });
}

// --- Messages from Content Script ---

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    console.log('[CopilotAgent BG] Message from content script:', message);

    if (message.type === 'DOWNLOAD_FILE') {
        // Content script found a download URL
        const downloadUrl = message.url;
        const filename = message.filename || 'CopilotAgent/output.zip';

        chrome.downloads.download({
            url: downloadUrl,
            filename: filename,
            conflictAction: 'overwrite'
        }, (downloadId) => {
            if (chrome.runtime.lastError) {
                sendToServer({
                    event: 'ERROR',
                    status: 'ERROR',
                    message: `Download failed: ${chrome.runtime.lastError.message}`,
                    step: 'DOWNLOAD'
                });
            } else {
                console.log(`[CopilotAgent BG] Download started: ${downloadId}`);
            }
        });
    }

    if (message.type === 'STATUS_UPDATE') {
        sendToServer({ event: 'STATUS_UPDATE', status: message.status, message: message.message || '' });
    }

    if (message.type === 'ERROR') {
        sendToServer({ event: 'ERROR', status: 'ERROR', message: message.message, step: message.step });
    }
});

// --- Download Completion Listener ---

chrome.downloads.onChanged.addListener((delta) => {
    if (delta.state && delta.state.current === 'complete') {
        chrome.downloads.search({ id: delta.id }, (results) => {
            if (results.length > 0 && results[0].filename.includes('CopilotAgent')) {
                const filename = results[0].filename.split('/').pop();
                console.log(`[CopilotAgent BG] Download complete: ${filename}`);
                sendToServer({
                    event: 'TASK_COMPLETE',
                    status: 'FILE_DOWNLOADED',
                    filename: filename
                });
            }
        });
    }

    if (delta.state && delta.state.current === 'interrupted') {
        sendToServer({
            event: 'ERROR',
            status: 'ERROR',
            message: `Download interrupted: ${delta.error?.current || 'unknown'}`,
            step: 'DOWNLOAD'
        });
    }
});

// --- Initialize ---
connectWebSocket();
console.log('[CopilotAgent BG] Background service worker initialized');
```

- [ ] **Step 2: Reload Extension and verify**

1. Go to `chrome://extensions/`, click "Reload" on the Copilot Agent extension
2. Click "Service Worker" link to open the background console
3. Start `python agent.py` in terminal
4. Verify background console shows: `[CopilotAgent BG] Connected to Python CLI`
5. Verify Python CLI shows the connection

- [ ] **Step 3: Commit**

```bash
git add extension/background.js
git commit -m "feat: implement background.js with WebSocket, tab navigation, and downloads"
```

---

### Task 6: Chrome Extension — Content Script (DOM Automation)

**Files:**
- Modify: `extension/content.js`

**Interfaces:**
- Consumes: `EXECUTE_TASK` message from `background.js` (Task 5) containing `{ model, prompt, system_instruction, onedrive_link }`
- Produces: 
  - `chrome.runtime.sendMessage({ type: 'DOWNLOAD_FILE', url, filename })` when download link found
  - `chrome.runtime.sendMessage({ type: 'STATUS_UPDATE', status, message })` for progress updates
  - `chrome.runtime.sendMessage({ type: 'ERROR', message, step })` on failures

- [ ] **Step 1: Implement `extension/content.js`**

```javascript
// content.js — DOM Automation for M365 Copilot Web
// Responsibilities: Model Selection → Prompt Input → Send → Observe Response → Find Download

const SELECTORS = {
    modelSelector: '#gptModeSwitcher, button[aria-label="Model Selector"]',
    chatInput: '#m365-chat-editor-target-element',
    sendButton: 'button[aria-label="Send"], button.fai-SendButton',
    temporaryChat: 'button[aria-label="Temporary chat"]',
};

const MAX_RETRIES = 5;
const RETRY_DELAY_MS = 2000;

// --- Utility Functions ---

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function waitForElement(selector, timeoutMs = 15000) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
        const el = document.querySelector(selector);
        if (el) return el;
        await sleep(500);
    }
    return null;
}

function sendStatus(status, message = '') {
    chrome.runtime.sendMessage({ type: 'STATUS_UPDATE', status, message });
}

function sendError(message, step) {
    chrome.runtime.sendMessage({ type: 'ERROR', message, step });
}

// --- Step 1: Select Model ---

async function selectModel(modelName) {
    const modelBtn = await waitForElement(SELECTORS.modelSelector);
    if (!modelBtn) {
        sendError('Model Selector button not found', 'MODEL_SELECTION');
        return false;
    }

    modelBtn.click();
    await sleep(1000);

    // Find the menu item matching the model name
    const menuItems = Array.from(document.querySelectorAll(
        '[role="menuitem"], [role="option"], [role="menuitemradio"]'
    ));
    const target = menuItems.find(item =>
        item.textContent.toLowerCase().includes(modelName.toLowerCase())
    );

    if (target) {
        target.click();
        sendStatus('MODEL_SELECTED', `Selected model: ${modelName}`);
        await sleep(500);
        return true;
    } else {
        // Close the menu by clicking elsewhere
        modelBtn.click();
        sendStatus('MODEL_SELECTED', `Model "${modelName}" not found in menu, using default`);
        await sleep(500);
        return true;  // Continue with default model
    }
}

// --- Step 2: Input Prompt ---

async function inputPrompt(fullPrompt) {
    const editor = await waitForElement(SELECTORS.chatInput);
    if (!editor) {
        sendError('Chat input element not found', 'PROMPT_INPUT');
        return false;
    }

    editor.focus();
    await sleep(300);

    // Clear existing content
    document.execCommand('selectAll', false, null);
    document.execCommand('delete', false, null);
    await sleep(200);

    // Insert text using execCommand for Fluent UI React compatibility
    document.execCommand('insertText', false, fullPrompt);
    await sleep(300);

    // Dispatch events to ensure React state updates
    editor.dispatchEvent(new Event('input', { bubbles: true }));
    editor.dispatchEvent(new Event('change', { bubbles: true }));

    sendStatus('PROMPT_ENTERED', 'Prompt typed into chat input');
    return true;
}

// --- Step 3: Click Send ---

async function clickSend() {
    // Wait a moment for the Send button to become active
    await sleep(500);
    const sendBtn = await waitForElement(SELECTORS.sendButton);
    if (!sendBtn) {
        sendError('Send button not found', 'SEND');
        return false;
    }

    sendBtn.click();
    sendStatus('PROMPT_SENT', 'Prompt sent to Copilot');
    return true;
}

// --- Step 4: Observe Response & Find Download ---

async function observeResponse() {
    sendStatus('WAITING_RESPONSE', 'Waiting for Copilot to generate response...');

    return new Promise((resolve) => {
        let lastMutationTime = Date.now();
        let checkInterval = null;
        let downloadFound = false;

        const observer = new MutationObserver((mutations) => {
            lastMutationTime = Date.now();

            // Check for download links in new content
            if (!downloadFound) {
                const downloadLink = findDownloadLink();
                if (downloadLink) {
                    downloadFound = true;
                    // Wait a bit more to ensure response is fully complete
                    setTimeout(() => {
                        cleanup();
                        resolve(downloadLink);
                    }, 3000);
                }
            }
        });

        observer.observe(document.body, { childList: true, subtree: true, characterData: true });

        // Periodically check if response has stopped generating
        checkInterval = setInterval(() => {
            const elapsed = Date.now() - lastMutationTime;

            // If no mutations for 10 seconds, response is likely complete
            if (elapsed > 10000 && !downloadFound) {
                const downloadLink = findDownloadLink();
                if (downloadLink) {
                    downloadFound = true;
                    cleanup();
                    resolve(downloadLink);
                } else {
                    // Response finished but no download link found
                    cleanup();
                    resolve(null);
                }
            }
        }, 2000);

        // Timeout after 5 minutes
        const timeout = setTimeout(() => {
            if (!downloadFound) {
                cleanup();
                resolve(null);
            }
        }, 300000);

        function cleanup() {
            observer.disconnect();
            clearInterval(checkInterval);
            clearTimeout(timeout);
        }
    });
}

function findDownloadLink() {
    // Strategy 1: Look for <a> tags with download attribute
    const downloadAnchors = document.querySelectorAll('a[download]');
    for (const a of downloadAnchors) {
        if (a.href) return a.href;
    }

    // Strategy 2: Look for links to zip files
    const zipLinks = document.querySelectorAll('a[href*=".zip"]');
    for (const a of zipLinks) {
        if (a.href) return a.href;
    }

    // Strategy 3: Look for buttons with download-related text
    const buttons = Array.from(document.querySelectorAll('button'));
    const downloadBtn = buttons.find(b => {
        const text = (b.textContent || '').toLowerCase();
        const label = (b.getAttribute('aria-label') || '').toLowerCase();
        return text.includes('download') || label.includes('download');
    });
    if (downloadBtn) {
        // Click the download button and let the browser handle it
        downloadBtn.click();
        return '__CLICKED_DOWNLOAD_BUTTON__';
    }

    return null;
}

// --- Main Task Executor ---

async function executeTask(taskData) {
    const { model, prompt, system_instruction, onedrive_link } = taskData;

    // Build full prompt
    const fullPrompt = [
        system_instruction || '',
        '',
        `Link OneDrive chứa mã nguồn: ${onedrive_link}`,
        '',
        `YÊU CẦU: ${prompt}`,
        '',
        'QUY ĐỊNH KẾT QUẢ: Sau khi hoàn thành, hãy tạo file nén (.zip) chứa toàn bộ các file đã được chỉnh sửa và cung cấp link/nút TẢI VỀ cho file này.'
    ].join('\n');

    // Step 1: Select model
    if (model) {
        const modelOk = await selectModel(model);
        if (!modelOk) return;
    }

    // Step 2: Input prompt
    const inputOk = await inputPrompt(fullPrompt);
    if (!inputOk) return;

    // Step 3: Click Send
    const sendOk = await clickSend();
    if (!sendOk) return;

    // Step 4: Observe response and find download link
    const downloadUrl = await observeResponse();

    if (downloadUrl && downloadUrl !== '__CLICKED_DOWNLOAD_BUTTON__') {
        sendStatus('DOWNLOADING', `Found download URL: ${downloadUrl}`);
        chrome.runtime.sendMessage({
            type: 'DOWNLOAD_FILE',
            url: downloadUrl,
            filename: 'CopilotAgent/output.zip'
        });
    } else if (downloadUrl === '__CLICKED_DOWNLOAD_BUTTON__') {
        sendStatus('DOWNLOADING', 'Clicked download button, waiting for browser to handle...');
        // The browser download will be caught by background.js download listener
    } else {
        sendError('No download link found in Copilot response', 'DOWNLOAD_DETECTION');
    }
}

// --- Message Listener ---

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === 'EXECUTE_TASK') {
        console.log('[CopilotAgent CS] Received task:', message);
        executeTask(message);
    }
});

console.log('[CopilotAgent CS] Content script loaded on', window.location.href);
```

- [ ] **Step 2: Reload Extension and test DOM interaction**

1. Go to `chrome://extensions/`, click "Reload"
2. Open `https://m365.cloud.microsoft/chat`
3. Open DevTools console on the Copilot page
4. Verify: `[CopilotAgent CS] Content script loaded on https://m365.cloud.microsoft/chat`

- [ ] **Step 3: Commit**

```bash
git add extension/content.js
git commit -m "feat: implement content.js with model selection, prompt input, send, and response observer"
```

---

### Task 7: End-to-End Integration Test

**Files:**
- No new files — manual integration test

**Interfaces:**
- Consumes: All components from Tasks 1-6

- [ ] **Step 1: Prepare a test project**

Create a small test repo:

```bash
mkdir -p my_project
echo 'def greet(name): return f"Hello {name}"' > my_project/app.py
echo 'import unittest
from app import greet

class TestGreet(unittest.TestCase):
    def test_greet(self):
        self.assertEqual(greet("World"), "Hello World")

if __name__ == "__main__":
    unittest.main()' > my_project/test_app.py
```

- [ ] **Step 2: Update `config.json` with real paths**

Edit `config.json` to point `repo_path` to `./my_project`, update `onedrive_link` with your actual OneDrive share link, and set `download_path` to your browser's download directory + `/CopilotAgent`.

- [ ] **Step 3: Run the full loop**

1. Start the Python CLI: `python agent.py`
2. Open Chrome with the Copilot Agent extension loaded
3. Navigate to `https://m365.cloud.microsoft/chat`
4. Verify WebSocket connection in both background console and Python terminal
5. Enter a task prompt when prompted by the CLI (e.g., "Add a farewell function to app.py")
6. Observe the automation:
   - Extension navigates to new chat
   - Model is selected
   - Prompt is typed and sent
   - Response is observed
   - Download is triggered (if Copilot produces one)
7. Check Python CLI output for verification result

- [ ] **Step 4: Document findings and known issues**

Note in terminal/log:
- Which steps worked correctly
- Which steps need adjustment (selector changes, timing issues)
- Whether Copilot actually produced a downloadable zip file

- [ ] **Step 5: Commit any fixes from integration testing**

```bash
git add -A
git commit -m "test: end-to-end integration test and fixes"
```
