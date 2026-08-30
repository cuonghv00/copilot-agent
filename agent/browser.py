"""
agent/browser.py — Playwright browser controller cho M365 Copilot.

Thay thế toàn bộ Chrome Extension (content.js + background.js).
Điều khiển browser qua CDP, không qua WebSocket — ổn định hơn trong
môi trường mạng doanh nghiệp.
"""

import asyncio
import re
from pathlib import Path
from typing import Callable, Awaitable

from playwright.async_api import (
    async_playwright,
    BrowserContext,
    Page,
    Playwright,
    Download,
    TimeoutError as PWTimeoutError,
)

from agent.ui import print_sys

# ── Selectors (port từ content.js) ──────────────────────────────────────────

SELECTORS = {
    "new_chat":      'a[aria-label="New chat"], button[aria-label="New chat"]',
    "model_selector":'#gptModeSwitcher, button[aria-label="Model Selector"]',
    "chat_input":    "#m365-chat-editor-target-element",
    "send_button":   'button[aria-label="Send"], button.fai-SendButton',
    "response_done": '[data-testid="copy-button"], button[aria-label="Copy"], button[aria-label="Like"]',
}

MODEL_MAPPING: dict[str, list[str]] = {
    "auto":    ["Auto"],
    "quick":   ["Quick response"],
    "think":   ["Think deeper"],
    "gpt5.5":  ["GPT", "5.5"],
    "gpt 5.5": ["GPT", "5.5"],
    "gpt5.6":  ["GPT", "5.6"],
    "gpt 5.6": ["GPT", "5.6"],
    "sonnet":  ["Anthropic", "Sonnet"],
    "opus":    ["Anthropic", "Opus"],
    "gpt":     ["OpenAI"],
}

COPILOT_BASE = "https://m365.cloud.microsoft/chat"

# Callback type: nhận status string để update UI
StatusCallback = Callable[[str, str], Awaitable[None]] | None


# ── JS helpers (chạy trong page context) ────────────────────────────────────

_JS_PASTE_TEXT = """
(text) => {
    // Tìm editor
    let editor = document.querySelector('#m365-chat-editor-target-element');
    if (!editor) editor = document.querySelector('[contenteditable="true"]');
    if (!editor) return false;

    editor.focus();
    // Clear
    document.execCommand('selectAll', false, null);
    document.execCommand('delete', false, null);

    // ClipboardEvent paste — giữ nguyên newline trong ProseMirror editor
    try {
        const dt = new DataTransfer();
        dt.setData('text/plain', text);
        editor.dispatchEvent(new ClipboardEvent('paste', {
            clipboardData: dt, bubbles: true, cancelable: true,
        }));
        editor.dispatchEvent(new Event('input', { bubbles: true }));
        return true;
    } catch(_) {
        // Fallback: insertText line by line
        const lines = text.split('\\n');
        for (let i = 0; i < lines.length; i++) {
            if (lines[i]) document.execCommand('insertText', false, lines[i]);
            if (i < lines.length - 1) document.execCommand('insertParagraph', false, null);
        }
        editor.dispatchEvent(new Event('input', { bubbles: true }));
        return true;
    }
}
"""

_JS_EXTRACT_SESSION_ID = """
() => {
    const m = window.location.href.match(/\\/conversation\\/([0-9a-f-]{36})/i);
    return m ? m[1] : null;
}
"""

_JS_EXTRACT_RESPONSE_TEXT = """
() => {
    const blocks = document.querySelectorAll(
        '[data-testid*="message"], .message-content, [class*="response"], [class*="assistant"]'
    );
    if (!blocks.length) return '';
    const last = blocks[blocks.length - 1];
    return (last.innerText || last.textContent || '').trim().slice(0, 1500);
}
"""

_JS_FIND_DOWNLOAD_LINK = """
() => {
    function isDownloadable(url) {
        if (!url) return false;
        if (url.startsWith('blob:') || url.startsWith('data:')) return true;
        try {
            const u = new URL(url);
            const p = u.pathname.toLowerCase();
            if ((u.hostname.includes('m365.cloud.microsoft') ||
                 u.hostname.includes('copilot.microsoft.com')) &&
                (p.includes('/chat') || p.includes('/conversation'))) return false;
            return /\\.(zip|tar\\.gz|tgz|gz|rar|7z)$/i.test(p);
        } catch { return false; }
    }

    // Priority 1: <a download> with zip href
    for (const a of document.querySelectorAll('a[download]')) {
        if (isDownloadable(a.href)) return { url: a.href, filename: a.download || 'output.zip' };
    }
    // Priority 2: <a href*=".zip">
    for (const a of document.querySelectorAll('a[href*=".zip"]')) {
        if (isDownloadable(a.href)) return { url: a.href, filename: a.download || 'output.zip' };
    }
    // Priority 3: blob: links
    for (const a of document.querySelectorAll('a[href^="blob:"]')) {
        if (a.href) return { url: a.href, filename: a.download || 'output.zip' };
    }
    // Priority 4: aria-label Download
    for (const a of document.querySelectorAll('a[aria-label*="Download" i]')) {
        if (isDownloadable(a.href)) return { url: a.href, filename: a.download || 'output.zip' };
    }
    return null;
}
"""

_JS_CLICK_DOWNLOAD_BUTTON = """
() => {
    const hints = ['zip', 'source', 'code', 'archive', 'project', '.zip'];
    const btn = Array.from(document.querySelectorAll('button')).find(b => {
        const t = (b.textContent || '').toLowerCase().trim();
        const l = (b.getAttribute('aria-label') || '').toLowerCase();
        if (!(t === 'download' || t.startsWith('download ') || l.includes('download'))) return false;
        const ctx = (b.closest('[data-testid], .message-content, article, section')
            ?.textContent || '').toLowerCase();
        return hints.some(h => l.includes(h) || t.includes(h) || ctx.includes(h));
    });
    if (btn) { btn.click(); return true; }
    return false;
}
"""

_JS_COPY_BTN_COUNT = """
() => document.querySelectorAll(
    '[data-testid="copy-button"], button[aria-label="Copy"], button[aria-label="Like"]'
).length
"""


# ── BrowserController ────────────────────────────────────────────────────────

class BrowserController:
    """
    Điều khiển M365 Copilot qua Playwright (CDP).
    Thay thế Chrome Extension — không phụ thuộc WebSocket.
    """

    def __init__(self, config: dict):
        self.config = config
        self.profile_dir = (
            Path(config.get("browser_profile_dir", "~/.copilot-agent-profile"))
            .expanduser()
            .resolve()
        )
        self.headless: bool = config.get("browser_headless", False)
        self.timeout: int = config.get("browser_timeout_ms", 30_000)
        self.executable: str = config.get("browser_executable_path", "")
        self.copilot_url: str = config.get("copilot_base_url", COPILOT_BASE)
        self.onedrive_delay: int = config.get("onedrive_link_delay_ms", 3_000)
        self.download_path = (
            Path(config.get("download_path", "~/Downloads/CopilotAgent"))
            .expanduser()
            .resolve()
        )

        self._pw: Playwright | None = None
        self._ctx: BrowserContext | None = None
        self._page: Page | None = None
        self.ready: bool = False

        # Callback để update status lên CLI UI
        self._on_status: StatusCallback = None

    def set_status_callback(self, cb: StatusCallback) -> None:
        self._on_status = cb

    async def _status(self, status: str, msg: str = "") -> None:
        if self._on_status:
            await self._on_status(status, msg)
        else:
            print_sys(f"↳ {msg or status}", "dim")

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def launch(self) -> None:
        """Khởi động browser với persistent profile (lưu cookies/session)."""
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.download_path.mkdir(parents=True, exist_ok=True)

        self._pw = await async_playwright().start()

        launch_kwargs: dict = {
            "user_data_dir": str(self.profile_dir),
            "headless":      self.headless,
            "downloads_path": str(self.download_path),
            "args": [
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
            "ignore_default_args": ["--enable-automation"],
        }

        if self.executable:
            # Dùng Chrome/Edge đã cài sẵn (khuyến nghị cho doanh nghiệp)
            launch_kwargs["executable_path"] = self.executable
        else:
            # Dùng system Chrome qua channel (không cần download Chromium)
            launch_kwargs["channel"] = "chrome"

        try:
            self._ctx = await self._pw.chromium.launch_persistent_context(**launch_kwargs)
        except Exception as e:
            if "channel" in launch_kwargs and not self.executable:
                # Chrome không có sẵn → fallback Playwright Chromium
                print_sys(
                    f"⚠ System Chrome không tìm thấy ({e}). "
                    "Thử dùng Playwright Chromium…", "yellow"
                )
                del launch_kwargs["channel"]
                self._ctx = await self._pw.chromium.launch_persistent_context(**launch_kwargs)
            else:
                raise

        # Lấy page đầu tiên hoặc tạo mới
        pages = self._ctx.pages
        self._page = pages[0] if pages else await self._ctx.new_page()
        self._page.set_default_timeout(self.timeout)

        # Navigate tới Copilot nếu chưa đúng trang
        if not self._page.url.startswith("https://m365.cloud.microsoft"):
            await self._page.goto(self.copilot_url, wait_until="domcontentloaded")

        self.ready = True
        print_sys("✓ Browser ready — M365 Copilot loaded", "green")

    async def close(self) -> None:
        """Đóng browser và giải phóng resources."""
        if self._ctx:
            await self._ctx.close()
        if self._pw:
            await self._pw.stop()
        self.ready = False

    # ── Step 0: New Chat ─────────────────────────────────────────────────────

    async def new_chat(self) -> None:
        await self._status("NAVIGATING_NEW_CHAT", "Opening new chat…")
        page = self._page
        await page.goto(self.copilot_url, wait_until="domcontentloaded")
        try:
            btn = page.locator(SELECTORS["new_chat"]).first
            await btn.click(timeout=5_000)
            await page.wait_for_timeout(1_500)
        except PWTimeoutError:
            pass  # Button không xuất hiện — đã ở trang mới rồi

    async def resume_session(self, session_id: str) -> None:
        await self._status("CONTINUING_CHAT", f"Resuming session {session_id[:8]}…")
        url = f"{self.copilot_url}/conversation/{session_id}"
        await self._page.goto(url, wait_until="domcontentloaded")
        await self._page.wait_for_timeout(2_000)

    # ── Step 1: Model Selection ──────────────────────────────────────────────

    async def select_model(self, model_name: str) -> None:
        await self._status("MODEL_SELECTION", f"Selecting model: {model_name}")
        page = self._page
        path = MODEL_MAPPING.get(model_name.lower(), [model_name])

        try:
            btn = page.locator(SELECTORS["model_selector"]).first
            await btn.click(timeout=5_000)
            await page.wait_for_timeout(800)
        except PWTimeoutError:
            await self._status("MODEL_SKIPPED", "Model selector not found")
            return

        found = False
        for step_text in path:
            try:
                # Tìm menu item chứa text (case-insensitive)
                item = page.locator(
                    '.fai-CapabilityPickerMenuItem, [role="menuitem"], [role="option"]'
                ).filter(has_text=re.compile(step_text, re.IGNORECASE)).first
                await item.click(timeout=3_000)
                await page.wait_for_timeout(600)
                found = True
            except PWTimeoutError:
                break

        if not found:
            # Đóng menu lại
            try:
                await page.locator(SELECTORS["model_selector"]).first.click(timeout=2_000)
            except PWTimeoutError:
                pass
            await self._status("MODEL_SKIPPED", f"Model '{model_name}' not in menu, using current")
        else:
            await self._status("MODEL_SELECTED", f"Model selected: {model_name}")

    # ── Step 2: Input Prompt ─────────────────────────────────────────────────

    async def input_prompt(self, full_prompt: str) -> bool:
        await self._status("PROMPT_FINDING", "Finding chat input…")
        page = self._page

        # Chờ editor sẵn sàng
        try:
            await page.wait_for_selector(SELECTORS["chat_input"], timeout=8_000)
        except PWTimeoutError:
            try:
                await page.wait_for_selector('[contenteditable="true"]', timeout=3_000)
            except PWTimeoutError:
                print_sys("❌ Chat input not found", "red")
                return False

        ok = await page.evaluate(_JS_PASTE_TEXT, full_prompt)
        if not ok:
            print_sys("❌ Failed to paste prompt into editor", "red")
            return False

        await page.wait_for_timeout(300)
        await self._status("PROMPT_ENTERED", "Prompt entered")
        return True

    # ── Step 3: Send ─────────────────────────────────────────────────────────

    async def click_send(self) -> bool:
        await self._page.wait_for_timeout(500)
        try:
            btn = self._page.locator(SELECTORS["send_button"]).first
            await btn.click(timeout=5_000)
            await self._status("PROMPT_SENT", "Prompt sent")
            return True
        except PWTimeoutError:
            print_sys("❌ Send button not found", "red")
            return False

    # ── Step 4: Wait for Response + Download ────────────────────────────────

    async def wait_for_response(self) -> dict:
        """
        Chờ Copilot trả lời xong, detect download link.
        Returns:
            {"type": "text", "response": str}
            {"type": "file", "path": Path, "response": str}
            {"type": "error", "message": str}
        """
        await self._status("WAITING_RESPONSE", "Waiting for Copilot response…")
        page = self._page

        # Đếm số copy buttons hiện có (từ các response cũ)
        initial_done_count: int = await page.evaluate(_JS_COPY_BTN_COUNT)

        # Chờ response mới hoàn tất (copy button count tăng lên)
        HARD_TIMEOUT = 480_000  # 8 phút
        POLL_INTERVAL = 1_500   # ms
        elapsed = 0

        while elapsed < HARD_TIMEOUT:
            await page.wait_for_timeout(POLL_INTERVAL)
            elapsed += POLL_INTERVAL

            current_count: int = await page.evaluate(_JS_COPY_BTN_COUNT)
            if current_count > initial_done_count:
                # Response xong — thêm thời gian ngắn để DOM render đầy đủ
                await page.wait_for_timeout(1_500)
                break
        else:
            return {"type": "error", "message": "Timeout (8 min) waiting for response"}

        # Trích xuất text response
        response_text: str = await page.evaluate(_JS_EXTRACT_RESPONSE_TEXT)
        if response_text:
            print_sys(f"\n📋 Copilot: {response_text[:300]}{'…' if len(response_text) > 300 else ''}", "cyan")

        # Cập nhật session ID từ URL
        session_id: str | None = await page.evaluate(_JS_EXTRACT_SESSION_ID)

        # Kiểm tra download link
        dl_data: dict | None = await page.evaluate(_JS_FIND_DOWNLOAD_LINK)

        if dl_data is None:
            # Thử click Download button nếu có
            clicked = await page.evaluate(_JS_CLICK_DOWNLOAD_BUTTON)
            if clicked:
                dl_data = {"url": "__BUTTON_CLICKED__", "filename": "output.zip"}

        if dl_data is None:
            return {"type": "text", "response": response_text, "session_id": session_id}

        # Trigger download
        await self._status("DOWNLOADING", f"Downloading: {dl_data['url'][:60]}…")
        filename = dl_data.get("filename", "output.zip")
        save_path = self.download_path / filename

        try:
            if dl_data["url"] == "__BUTTON_CLICKED__":
                # Download đã được trigger bởi button click trên
                # Chờ download event từ Playwright
                async with page.expect_download(timeout=60_000) as dl_info:
                    pass  # download đã triggered rồi
                download: Download = await dl_info.value
                save_path = self.download_path / (download.suggested_filename or filename)
                await download.save_as(save_path)

            elif dl_data["url"].startswith("blob:") or dl_data["url"].startswith("data:"):
                # Playwright tự xử lý blob: download khi click link
                async with page.expect_download(timeout=30_000) as dl_info:
                    await page.evaluate(
                        f"() => {{ const a = document.querySelector('a[href^=\"blob:\"]'); if(a) a.click(); }}"
                    )
                download = await dl_info.value
                save_path = self.download_path / (download.suggested_filename or filename)
                await download.save_as(save_path)

            else:
                # HTTP URL — click anchor tag hoặc navigate trực tiếp
                anchor = page.locator(f'a[href="{dl_data["url"]}"]').first
                async with page.expect_download(timeout=30_000) as dl_info:
                    try:
                        await anchor.click(timeout=3_000)
                    except PWTimeoutError:
                        # Fallback: open link in new page to trigger download
                        await page.goto(dl_data["url"])
                download = await dl_info.value
                save_path = self.download_path / (download.suggested_filename or filename)
                await download.save_as(save_path)

        except PWTimeoutError:
            return {"type": "error", "message": "Download timeout (60s)"}
        except Exception as e:
            return {"type": "error", "message": f"Download failed: {e}"}

        return {"type": "file", "path": save_path, "response": response_text, "session_id": session_id}

    # ── Orchestrator ─────────────────────────────────────────────────────────

    async def execute_task(
        self,
        prompt: str,
        model: str,
        is_new_session: bool,
        last_session_id: str = "",
        onedrive_link_delay_ms: int = 0,
    ) -> dict:
        """Chạy full flow: navigate → model → input → send → wait → download."""
        page = self._page

        # Navigation
        if is_new_session:
            await self.new_chat()
        elif last_session_id:
            current_sid: str | None = await page.evaluate(_JS_EXTRACT_SESSION_ID)
            if current_sid != last_session_id:
                await self.resume_session(last_session_id)
        # else: giữ nguyên tab hiện tại (continue chat)

        # Model selection
        if model:
            await self.select_model(model)

        # Input
        ok = await self.input_prompt(prompt)
        if not ok:
            return {"type": "error", "message": "Failed to input prompt"}

        # OneDrive delay — đợi platform nhận diện file link trước khi Send
        if onedrive_link_delay_ms > 0:
            await self._status(
                "ONEDRIVE_WAIT",
                f"Waiting {onedrive_link_delay_ms}ms for OneDrive file recognition…"
            )
            await page.wait_for_timeout(onedrive_link_delay_ms)

        # Send
        ok = await self.click_send()
        if not ok:
            return {"type": "error", "message": "Failed to click Send"}

        # Cập nhật session ID ngay sau khi send (URL thường update)
        await page.wait_for_timeout(2_000)
        session_id: str | None = await page.evaluate(_JS_EXTRACT_SESSION_ID)

        # Chờ response
        result = await self.wait_for_response()

        # Gắn session ID nếu chưa có từ response
        if "session_id" not in result or not result.get("session_id"):
            result["session_id"] = session_id

        return result
