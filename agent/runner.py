import asyncio
import json
from pathlib import Path
import websockets
from prompt_toolkit.application import get_app
from rich.live import Live

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
        self.ws: websockets.ServerConnection | None = None
        self.connected = False
        self.task_running = False
        self._pending: asyncio.Future | None = None
        self._current_model = config["default_model"]
        self.status_history = []
        self.live_display = None
        self._task_lock = asyncio.Lock()  # LOG-1: serialize tasks — task 2 chờ task 1 xong
        self.connected_event = asyncio.Event()  # bắt khi extension kết nối lần đầu

    async def handle_connection(self, websocket):
        self.ws = websocket
        self.connected = True
        self.connected_event.set()  # thông báo cho cli biết extension đã kết nối
        print_sys("✓ Chrome Extension connected", "green")
        try:
            get_app().invalidate()
        except Exception:
            pass
        try:
            async for raw in websocket:
                await self._on_message(json.loads(raw))
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self.connected = False
            self.ws = None
            print_sys("Extension disconnected", "yellow")
            try:
                get_app().invalidate()
            except Exception:
                pass

    async def _on_message(self, data: dict):
        event = data.get("event", "")

        if event == "SESSION_ID":
            sid = data.get("id", "")
            if sid:
                self.state.last_session_id = sid
                self.state.model = self._current_model
                self.state.save()
                print_sys(f"📌 Session ID: {sid}", "dim cyan")
                try:
                    get_app().invalidate()
                except Exception:
                    pass

        elif event == "STATUS_UPDATE":
            status = data.get("status", "")
            _noisy = {"NEW_CHAT_CLICKED", "PROMPT_FINDING", "PROMPT_ENTERED", "SENDING"}
            if status not in _noisy:
                self.status_history.append(f"↳ {data.get('message', status)}")
                if len(self.status_history) > 3:
                    self.status_history.pop(0)
                
                if getattr(self, 'live_display', None):
                    self.live_display.update(get_agent_panel("\n".join(self.status_history)))

        elif event == "RESPONSE_TEXT":
            text = data.get("text", "")
            if text:
                print_copilot_summary(text)

        elif event == "TASK_COMPLETE":
            status = data.get("status", "")
            if status == "FILE_DOWNLOADED":
                filepath = data.get("filepath", "")
                filename = data.get("filename", "output.zip")
                zip_file = (
                    Path(filepath)
                    if filepath and Path(filepath).exists()
                    else self.download_path / filename
                )
                if self._pending and not self._pending.done():
                    self._pending.set_result({"type": "file", "path": zip_file})
            elif status == "NO_FILE":
                if self._pending and not self._pending.done():
                    self._pending.set_result({"type": "text"})

        elif event == "ERROR":
            msg = data.get("message", "Unknown error")
            step = data.get("step", "?")
            console.print(f"[red]❌ [{step}] {msg}[/red]")
            if self._pending and not self._pending.done():
                self._pending.set_result({"type": "error", "message": f"[{step}] {msg}"})

    async def send_task(
        self, user_prompt: str, is_new_session: bool, model: str,
        request_output: bool = False,
        include_onedrive_link: bool = True,
    ) -> dict | None:
        if not self.connected or not self.ws:
            print_sys("❌ Extension chưa kết nối. Hãy mở browser và đảm bảo extension đang chạy.", "red")
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
            # Chỉ build link khi include_onedrive_link=True (user đã zip repo)
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

            payload = {
                "action": "START_TASK",
                "onedrive_link": dynamic_link,
                "model": model,
                "prompt": full_prompt,
                "is_new_session": is_new_session,
                "last_session_id": self.state.last_session_id,
            }

            self.task_running = True
            self.status_history = ["↳ Starting task…"]
            loop = asyncio.get_running_loop()
            self._pending = loop.create_future()

            try:
                with Live(get_agent_panel(self.status_history[0]), refresh_per_second=4, console=console) as live:
                    self.live_display = live
                    try:
                        await self.ws.send(json.dumps(payload))
                    except websockets.exceptions.ConnectionClosed:
                        self.task_running = False
                        self._pending = None
                        self.live_display = None
                        return None

                    try:
                        result = await asyncio.wait_for(asyncio.shield(self._pending), timeout=600)
                    except asyncio.TimeoutError:
                        result = {"type": "error", "message": "Timeout (10 min) waiting for response"}

                    self.status_history.append("↳ Done ✓")
                    if len(self.status_history) > 3:
                        self.status_history.pop(0)
                    live.update(get_agent_panel("\n".join(self.status_history)))
            finally:
                self.task_running = False
                self._pending = None
                self.live_display = None

            return result
