"""
agent/runner.py — TaskRunner

Orchestrate task execution: zip repo → upload → send to Copilot via Playwright.
Không còn phụ thuộc WebSocket hay Chrome Extension.
"""

import asyncio
from pathlib import Path

from rich.live import Live

from agent.browser import BrowserController
from agent.config import AgentState
from agent.prompt import load_skill_content, build_full_prompt
from agent.ui import console, print_sys, print_copilot_summary, get_agent_panel


class TaskRunner:
    def __init__(self, config: dict, state: AgentState):
        self.config = config
        self.state = state
        self.repo_path = Path(config["repo_path"]).expanduser().resolve()
        self.sync_path = Path(config["sync_path"]).expanduser().resolve()
        self.download_path = Path(config["download_path"]).expanduser().resolve()
        self.skills_dir = Path(config.get("skills_dir", "./skills")).expanduser().resolve()

        self._current_model = config["default_model"]
        self.status_history: list[str] = []
        self.live_display: Live | None = None
        self._task_lock = asyncio.Lock()  # serialize tasks

        # Playwright browser controller
        self.browser = BrowserController(config)
        self.browser.set_status_callback(self._handle_status)

    # ── Status callback từ BrowserController ────────────────────────────────

    async def _handle_status(self, status: str, msg: str) -> None:
        """Cập nhật live display khi browser gửi status update."""
        _noisy = {"NEW_CHAT_CLICKED", "PROMPT_FINDING", "PROMPT_ENTERED", "SENDING"}
        if status not in _noisy:
            self.status_history.append(f"↳ {msg or status}")
            if len(self.status_history) > 3:
                self.status_history.pop(0)
            if self.live_display:
                self.live_display.update(get_agent_panel("\n".join(self.status_history)))

    # ── Main task sender ─────────────────────────────────────────────────────

    async def send_task(
        self,
        user_prompt: str,
        is_new_session: bool,
        model: str,
        request_output: bool = False,
        include_onedrive_link: bool = True,
    ) -> dict | None:
        if not self.browser.ready:
            print_sys("❌ Browser chưa sẵn sàng. Thử khởi động lại agent.", "red")
            return None

        if self._task_lock.locked():
            print_sys("⏳ Task trước đang chạy, đang chờ hoàn thành…", "yellow")

        async with self._task_lock:
            if is_new_session:
                self.state.last_session_id = ""
                self.state.save()

            self._current_model = model
            skill_content = load_skill_content(user_prompt, self.skills_dir)

            repo_name = self.repo_path.name
            zip_filename = f"{repo_name}.zip"

            dynamic_link = ""
            if include_onedrive_link:
                dynamic_link = (
                    self.config.get("onedrive_link", "")
                    .replace("{zip_filename}", zip_filename)
                    .replace("{repo_name}", repo_name)
                )

            full_prompt = build_full_prompt(
                user_prompt, dynamic_link, skill_content,
                request_output, is_new_session
            )

            onedrive_delay_ms = (
                self.config.get("onedrive_link_delay_ms", 3_000)
                if include_onedrive_link and dynamic_link
                else 0
            )

            self.status_history = ["↳ Starting task…"]

            try:
                with Live(
                    get_agent_panel(self.status_history[0]),
                    refresh_per_second=4,
                    console=console,
                ) as live:
                    self.live_display = live

                    result = await self.browser.execute_task(
                        prompt=full_prompt,
                        model=model,
                        is_new_session=is_new_session,
                        last_session_id=self.state.last_session_id or "",
                        onedrive_link_delay_ms=onedrive_delay_ms,
                    )

                    # Lưu session ID nếu nhận được
                    sid = result.get("session_id")
                    if sid and sid != self.state.last_session_id:
                        self.state.last_session_id = sid
                        self.state.model = model
                        self.state.save()
                        print_sys(f"📌 Session ID: {sid}", "dim cyan")

                    # Hiển thị response text
                    response_text = result.get("response", "")
                    if response_text:
                        print_copilot_summary(response_text)

                    self.status_history.append("↳ Done ✓")
                    if len(self.status_history) > 3:
                        self.status_history.pop(0)
                    live.update(get_agent_panel("\n".join(self.status_history)))

            finally:
                self.live_display = None

            return result
