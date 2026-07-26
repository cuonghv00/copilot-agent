#!/usr/bin/env python3
"""Copilot Agent — Rich CLI + WebSocket server."""

import asyncio
import json
import re
import shutil
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path

import websockets
from prompt_toolkit import PromptSession
from prompt_toolkit.application import get_app
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live

console = Console()

# ── Config ────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    config_path = Path(__file__).parent / "config.json"
    with open(config_path) as f:
        return json.load(f)

# ── Session State ─────────────────────────────────────────────────────────────

class AgentState:
    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.last_session_id: str | None = None
        self.model: str = "auto"
        self._load()

    def _load(self):
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text())
                self.last_session_id = data.get("last_session_id")
                self.model = data.get("model", "auto")
            except Exception:
                pass

    def save(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps({
            "last_session_id": self.last_session_id,
            "model": self.model,
            "timestamp": datetime.now().isoformat(),
        }, indent=2))

# ── Skill Loader ──────────────────────────────────────────────────────────────

def load_skill_content(prompt: str, skills_dir: Path) -> str:
    """Parse @skill_name mentions from prompt and load matching skills/name/skills.md."""
    mentions = re.findall(r'@([\w-]+)', prompt)
    parts = []
    for name in mentions:
        skill_file = skills_dir / name / "skills.md"
        if skill_file.exists():
            content = skill_file.read_text().strip()
            # Skip empty or comment-only files
            non_comment = "\n".join(
                l for l in content.splitlines()
                if l.strip() and not l.strip().startswith("<!--")
            )
            if non_comment:
                parts.append(content)
    return "\n\n".join(parts)

# ── Prompt Builder ────────────────────────────────────────────────────────────

_PLACEHOLDER_URLS = {'', 'https://example.com/workspace.zip'}

OUTPUT_RULES_TEMPLATE = """\n─── QUY ĐỊNH KẾT QUẢ ───
Sau khi hoàn thành, hãy:
1. Tóm tắt ngắn các thay đổi đã thực hiện
2. Liệt kê bảng các file thay đổi: tên file | đường dẫn | mô tả ngắn
3. Xuất file nén (.zip) chứa toàn bộ mã nguồn với cấu trúc thư mục giữ nguyên, kèm nút Download
4. Liệt kê các lệnh để verify kết quả"""

OUTPUT_RULES_SHORT = "\nVui lòng xuất lại file zip cập nhật và cung cấp nút Download."


def build_full_prompt(
    user_prompt: str,
    onedrive_link: str,
    skill_content: str,
    request_output: bool,
    is_new_session: bool,
) -> str:
    parts: list[str] = []

    # OneDrive link — only if configured (not placeholder/empty)
    link = (onedrive_link or "").strip()
    if link and link not in _PLACEHOLDER_URLS:
        parts.append(f"📎 Mã nguồn dự án: {link}")
        parts.append("⚠️ Lưu ý: Vì hệ thống OneDrive có thể bị delay đồng bộ, nếu bạn tải file về mà thấy source code chưa được cập nhật, hãy đợi 10 giây rồi thử tải lại nhé.")
        parts.append("")

    # User prompt (unchanged)
    parts.append(user_prompt)

    # Skill content
    if skill_content:
        parts.append("")
        parts.append(skill_content)

    # Output rules — only when explicitly requested via /out
    if request_output:
        if is_new_session:
            parts.append(OUTPUT_RULES_TEMPLATE)
        else:
            parts.append(OUTPUT_RULES_SHORT)

    return "\n".join(parts)


# ── Repo Operations ───────────────────────────────────────────────────────────

def zip_repo(repo_path: Path, output_zip: Path, sync_command: str = None) -> Path:
    """Zip repo using git archive."""
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "archive", "--format=zip", "HEAD", "-o", str(output_zip)],
        cwd=repo_path, check=False, capture_output=True
    )
    if sync_command:
        cmd = sync_command.replace("{sync_dir}", str(output_zip.parent)).replace("{zip_path}", str(output_zip))
        subprocess.run(cmd, shell=True)
    return output_zip


def apply_downloaded_zip(zip_path: Path, repo_path: Path) -> list[str]:
    """Safely apply files from zip into repo, preserving relative paths."""
    applied = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.namelist():
            if member.endswith("/"):
                continue  # skip directory entries
            target = repo_path / member
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, open(target, "wb") as dst:
                dst.write(src.read())
            applied.append(member)
    zip_path.unlink(missing_ok=True)
    return applied


def run_verify(command: str, cwd: Path) -> tuple[bool, str]:
    result = subprocess.run(
        command, shell=True, capture_output=True, text=True, cwd=cwd
    )
    return result.returncode == 0, result.stdout + result.stderr

# ── UI Helpers ────────────────────────────────────────────────────────────────

def print_header(state: AgentState, ws_connected: bool, model: str, output_on: bool = False):
    console.rule("[bold blue]COPILOT AGENT[/bold blue]")


def _print_header_and_pad(state, ws_connected, model, output_on=False):
    """Print header then fill blank lines to push prompt near bottom."""
    print_header(state, ws_connected, model, output_on)
    term_h = shutil.get_terminal_size().lines
    # Leave room for: toolbar (1 line) + prompt (1 line) + some buffer
    content_lines = 2
    pad = max(0, term_h - content_lines - 3)
    if pad > 0:
        console.print("\n" * pad, end="")


def print_user_msg(prompt: str):
    console.print(Panel(
        Text(prompt, style="white"),
        title="[bold cyan]YOU[/bold cyan]",
        title_align="left",
        border_style="cyan", padding=(0, 2),
    ))


def print_copilot_summary(summary: str):
    console.print(Panel(
        Text(summary, style="dim white"),
        title="[bold green]COPILOT[/bold green]",
        title_align="left",
        border_style="green", padding=(0, 2),
    ))

def get_agent_panel(status: str):
    return Panel(
        Text(status, style="yellow"),
        title="[bold yellow]AGENT[/bold yellow]",
        title_align="left",
        border_style="yellow", padding=(0, 2),
    )


def print_applied(files: list[str]):
    if not files:
        return
    t = Table(box=box.SIMPLE, show_header=True, header_style="bold dim")
    t.add_column("Applied files", style="cyan")
    for f in files[:20]:  # cap display at 20
        t.add_row(f)
    if len(files) > 20:
        t.add_row(f"… and {len(files)-20} more")
    console.print(t)


def print_verify(success: bool, output: str):
    snippet = output[:2000] + ("…" if len(output) > 2000 else "")
    if not snippet.strip():
        snippet = "No output"
        
    if success:
        console.print(Panel(
            Text(snippet, style="dim white"),
            title="[bold green]✅ VERIFY PASSED[/bold green]",
            border_style="green",
        ))
    else:
        console.print(Panel(
            Text(snippet, style="red"),
            title="[bold red]❌ VERIFY FAILED[/bold red]",
            border_style="red",
        ))


def print_sys(msg: str, style: str = "dim"):
    if style:
        console.print(f"[{style}]{msg}[/{style}]")
    else:
        console.print(msg)


def print_help():
    console.print(Panel(
        "[bold]Session[/bold]\n"
        "  /new [model]   Bắt đầu chat mới (reset session)\n"
        "  /model [name]  Đổi model, giữ nguyên session\n"
        "  /resume [id]   Resume session ID đã lưu\n"
        "  /exit          Thoát\n\n"
        "[bold]Repo[/bold]\n"
        "  /zip           Re-zip repo lên sync_path\n"
        "  /diff          Xem git diff hiện tại\n"
        "  /verify        Chạy verify command lại\n\n"
        "[bold]Prompt[/bold]\n"
        "  /out           Toggle output rules template (mặc định: OFF)\n"
        "  @skill-name    Gắn local skill vào prompt\n"
        "  /skill list    Liệt kê skill có sẵn\n\n"
        "[bold]Khác[/bold]\n"
        "  /help          Hiển thị menu này",
        title="[bold]COMMANDS[/bold]",
        border_style="blue",
    ))


def make_toolbar(state: AgentState, runner, model: str, output_on: bool):
    """Bottom toolbar: commands on left, session id on right, transparent background."""
    def _toolbar():
        term_width = shutil.get_terminal_size().columns
        top_line = "─" * (term_width - 2)
        bottom_line = "─" * (term_width - 2)

        ws_dot = '<style fg="ansigreen">●</style>' if runner.connected else '<style fg="ansired">●</style>'
        out_flag = ' <style fg="ansiyellow">[OUT]</style>' if output_on else ''
        out_plain = ' [OUT]' if output_on else ''
        
        left_text = f'{ws_dot} <style fg="ansiyellow">[{model}]</style> /new   /model   /help   /exit'
        left_plain = f'● [{model}] /new   /model   /help   /exit'
        
        sid = state.last_session_id or "none"
        sid_short = sid[:10] + "…" if sid != "none" and len(sid) > 10 else sid
        right_plain = f'session: {sid_short}{out_plain}'
        
        term_width = shutil.get_terminal_size().columns
        
        content_width = term_width - 4 
        pad_len = content_width - len(left_plain) - len(right_plain)
        if pad_len < 1:
            pad_len = 1
        pad = " " * pad_len
        
        top_line = "─" * (term_width - 2)
        bottom_line = "─" * (term_width - 2)
        
        return HTML(
            f'<style fg="ansiblue">╭{top_line}╮</style>\n'
            f'<style fg="ansiblue">│</style> {left_text}{pad}<style fg="ansicyan">session: {sid_short}</style>{out_flag} <style fg="ansiblue">│</style>\n'
            f'<style fg="ansiblue">╰{bottom_line}╯</style>'
        )
    return _toolbar


# prompt_toolkit style: transparent toolbar background, inherit terminal fg
TOOLBAR_STYLE = Style.from_dict({
    'bottom-toolbar': 'noreverse bg:default fg:default',
})

# ── Task Runner ───────────────────────────────────────────────────────────────

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

    async def handle_connection(self, websocket):
        self.ws = websocket
        self.connected = True
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
            # Only surface meaningful status, not every DOM event
            status = data.get("status", "")
            _noisy = {"NEW_CHAT_CLICKED", "PROMPT_FINDING", "PROMPT_ENTERED", "SENDING"}
            if status not in _noisy:
                if not hasattr(self, 'status_history'):
                    self.status_history = []
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
                # Text-only response — already displayed via RESPONSE_TEXT
                if self._pending and not self._pending.done():
                    self._pending.set_result({"type": "text"})

        elif event == "ERROR":
            msg = data.get("message", "Unknown error")
            step = data.get("step", "?")
            console.print(f"[red]❌ [{step}] {msg}[/red]")
            if self._pending and not self._pending.done():
                self._pending.set_result({"type": "error", "message": f"[{step}] {msg}"})

    async def send_task(
        self, user_prompt: str, is_new_session: bool, model: str, request_output: bool = False
    ) -> dict | None:
        if not self.connected or not self.ws:
            print_sys("❌ Extension chưa kết nối. Hãy mở browser và đảm bảo extension đang chạy.", "red")
            return None

        if is_new_session:
            self.state.last_session_id = ""
            self.state.save()

        self._current_model = model
        skill_content = load_skill_content(user_prompt, self.skills_dir)
        
        repo_name = self.repo_path.name
        zip_filename = f"{repo_name}.zip"
        dynamic_link = self.config.get("onedrive_link", "").replace("{zip_filename}", zip_filename).replace("{repo_name}", repo_name)
        
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
                
                # Update final status
                self.status_history.append("↳ Done ✓")
                if len(self.status_history) > 3:
                    self.status_history.pop(0)
                live.update(get_agent_panel("\n".join(self.status_history)))
        finally:
            self.task_running = False
            self._pending = None
            self.live_display = None

        return result

# ── Main Loop ─────────────────────────────────────────────────────────────────

async def main():
    config = load_config()

    download_path = Path(config["download_path"]).expanduser()
    download_path.mkdir(parents=True, exist_ok=True)

    state_file = Path(config.get("session_state_file", "./.copilot-agent-state.json")).expanduser()
    state = AgentState(state_file)

    runner = TaskRunner(config, state)
    repo_path = Path(config["repo_path"]).expanduser().resolve()
    sync_path = Path(config["sync_path"]).expanduser().resolve()
    max_retry = config.get("max_retry_on_failure", 1)
    sync_command = config.get("sync_command")

    # Start WebSocket server
    port = config["websocket_port"]
    server = await websockets.serve(runner.handle_connection, "0.0.0.0", port)
    print_sys(f"WebSocket server on ws://localhost:{port} — waiting for extension…", "dim")

    # Zip on startup
    print_sys("Zipping repository…", "dim")
    repo_name = repo_path.name
    zip_filename = f"{repo_name}.zip"
    zip_output = sync_path / zip_filename
    await asyncio.to_thread(zip_repo, repo_path, zip_output, sync_command)
    print_sys(f"✓ Zipped → {zip_output}", "green")

    # Prompt session
    history_path = Path("~/.copilot-agent-history").expanduser()
    prompt_session = PromptSession(history=FileHistory(str(history_path)))

    current_model = state.model or config["default_model"]
    is_new_session = True
    output_mode = False  # /out toggle: append output rules template to prompt

    console.clear()
    _print_header_and_pad(state, runner.connected, current_model, output_mode)

    while True:
        try:
            with patch_stdout(raw=True):
                raw: str = await prompt_session.prompt_async(
                    "❯ ",
                    bottom_toolbar=make_toolbar(
                        state, runner,
                        current_model, output_mode
                    ),
                    style=TOOLBAR_STYLE,
                )
        except (EOFError, KeyboardInterrupt):
            print_sys("\nGoodbye!", "dim")
            if state.last_session_id:
                print_sys(f"💡 Để tiếp tục session này lần sau, gõ: /resume {state.last_session_id}", "dim cyan")
            break

        cmd = raw.strip()
        if not cmd:
            continue
            
        print("\033[F\033[K", end="")

        # ── Built-in commands ──────────────────────────────────────────────────
        if cmd.lower() == "/exit":
            print_sys("Goodbye!", "dim")
            if state.last_session_id:
                print_sys(f"💡 Để tiếp tục session này lần sau, gõ: /resume {state.last_session_id}", "dim cyan")
            break

        if cmd.lower() == "/help":
            print_help()
            continue

        if cmd.lower() == "/zip":
            print_sys("Re-zipping…", "dim")
            await asyncio.to_thread(zip_repo, repo_path, zip_output, sync_command)
            print_sys(f"✓ Re-zipped → {zip_output}", "green")
            continue

        if cmd.lower() == "/diff":
            _, diff = await asyncio.to_thread(run_verify, "git diff", repo_path)
            if diff.strip():
                console.print(Panel(diff, title="git diff", border_style="yellow"))
            else:
                print_sys("No changes in working tree.", "dim")
            continue

        if cmd.lower() == "/verify":
            print_sys(f"Running: {config['verify_command']}", "dim")
            success, output = await asyncio.to_thread(
                run_verify, config["verify_command"], repo_path
            )
            print_verify(success, output)
            continue

        if cmd.lower().startswith("/skill"):
            parts = cmd.split()
            if len(parts) > 1 and parts[1] == "list":
                skills_dir = Path(config.get("skills_dir", "./skills")).expanduser().resolve()
                if skills_dir.exists():
                    skills = sorted(
                        d.name for d in skills_dir.iterdir()
                        if d.is_dir() and (d / "skills.md").exists()
                    )
                    print_sys(f"Available skills: {', '.join(skills) or 'none'}", "cyan")
                else:
                    print_sys(f"Skills directory not found: {skills_dir}", "yellow")
            continue

        if cmd.lower().startswith("/resume"):
            parts = cmd.split(maxsplit=1)
            if len(parts) > 1:
                # ID provided inline: /resume <uuid>
                given_id = parts[1].strip()
                state.last_session_id = given_id
                state.save()
                is_new_session = False
                console.print(f"Session set to: [cyan]{given_id}[/cyan] — next prompt will resume this conversation.")
            elif state.last_session_id:
                is_new_session = False
                console.print(f"Will resume session: [cyan]{state.last_session_id}[/cyan]")
            else:
                print_sys("No saved session. Provide ID: /resume <uuid>", "yellow")
            continue

        if cmd.lower() == "/out":
            output_mode = not output_mode
            state_str = "[green]ON[/green]" if output_mode else "[dim]OFF[/dim]"
            console.print(f"Output rules template: {state_str} "
                          "(sẽ đính kèm vào prompt tiếp theo nếu ON)")
            continue

        if cmd.lower().startswith("/model"):
            parts = cmd.split(maxsplit=2)
            if len(parts) > 1:
                current_model = parts[1].strip()
            else:
                models = list({"auto", "quick", "think", "sonnet", "opus", "gpt5.5", "gpt5.6", "gpt"})
                console.print(f"Available models: [dim]{' · '.join(sorted(models))}[/dim]")
                try:
                    mi = await prompt_session.prompt_async(
                        f"Model [{current_model}]: "
                    )
                    current_model = mi.strip() or current_model
                except (EOFError, KeyboardInterrupt):
                    continue
                console.print(f"[dim cyan]Model switched to: {current_model}[/dim cyan]")
            
            state.model = current_model
            state.save()
            
            if len(parts) > 2:
                cmd = parts[2].strip()
            else:
                continue

        if cmd.lower().startswith("/new"):
            is_new_session = True
            parts = cmd.split(maxsplit=2)
            if len(parts) > 1:
                current_model = parts[1].strip()
            else:
                try:
                    mi = await prompt_session.prompt_async(
                        f"Model [{config['default_model']}]: "
                    )
                    current_model = mi.strip() or config["default_model"]
                except (EOFError, KeyboardInterrupt):
                    current_model = config["default_model"]
            state.model = current_model
            state.save()
            console.clear()
            _print_header_and_pad(state, runner.connected, current_model, output_mode)
            
            if len(parts) > 2:
                cmd = parts[2].strip()
            else:
                continue


        # ── Send task ──────────────────────────────────────────────────────────
        # Parse inline /out from prompt (e.g. "fix auth.py /out")
        inline_out = bool(re.search(r'(?:^|\s)/out(?:\s|$)', cmd))
        clean_cmd = re.sub(r'\s*/out\b', '', cmd).strip()
        request_output = output_mode or inline_out

        print_user_msg(clean_cmd)
        result = await runner.send_task(clean_cmd, is_new_session, current_model,
                                        request_output=request_output)
        is_new_session = False  # subsequent turns continue same session

        if result is None:
            continue

        if result["type"] == "error":
            # Already printed inline; just continue
            continue

        if result["type"] != "file":
            continue

        # Apply zip — validate first
        zip_file: Path = result["path"]
        if not zip_file.exists():
            print_sys(f"❌ Downloaded file not found: {zip_file}", "red")
            print_sys("Copilot response was shown above. No file to apply.", "dim")
            continue

        # Check zip magic bytes (PK\x03\x04)
        try:
            header = zip_file.read_bytes()[:4]
            if header != b'PK\x03\x04':
                print_sys(f"❌ File is not a valid zip (got: {header!r}). Skipping apply.", "red")
                zip_file.unlink(missing_ok=True)
                continue
        except OSError as e:
            print_sys(f"❌ Cannot read file: {e}", "red")
            continue

        try:
            applied = await asyncio.to_thread(apply_downloaded_zip, zip_file, repo_path)
        except zipfile.BadZipFile as e:
            print_sys(f"❌ Bad zip file: {e}", "red")
            zip_file.unlink(missing_ok=True)
            continue

        if not applied:
            print_sys("⚠ No files in zip to apply.", "yellow")
            continue

        print_sys(f"✓ Applied {len(applied)} file(s):", "green")
        print_applied(applied)

        # Auto verify + optional retry
        retry_left = max_retry
        verify_prompt_suffix = ""
        while True:
            print_sys(f"Running verify: {config['verify_command']}", "dim")
            success, output = await asyncio.to_thread(
                run_verify, config["verify_command"], repo_path
            )
            print_verify(success, output)

            if success or retry_left <= 0:
                break

            retry_left -= 1
            print_sys(f"Auto-retrying with error context ({retry_left} retries left)…", "yellow")
            retry_prompt = (
                f"Verify thất bại với lỗi sau:\n\n{output[:3000]}\n\n"
                "Hãy phân tích lỗi và sửa lại."
            )
            r2 = await runner.send_task(retry_prompt, False, current_model,
                                        request_output=output_mode)
            if r2 is None or r2["type"] != "file":
                break
            zip2: Path = r2["path"]
            if not zip2.exists():
                break
            applied2 = await asyncio.to_thread(apply_downloaded_zip, zip2, repo_path)
            if applied2:
                print_sys(f"✓ Retry applied {len(applied2)} file(s)", "green")
                print_applied(applied2)

    server.close()
    try:
        await asyncio.wait_for(server.wait_closed(), timeout=2.0)
    except asyncio.TimeoutError:
        pass  # Force close if connections linger


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass  # Clean exit on Ctrl+C at top level
