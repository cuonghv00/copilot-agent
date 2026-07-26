import shutil
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style

console = Console()

TOOLBAR_STYLE = Style.from_dict({
    'bottom-toolbar': 'noreverse bg:default fg:default',
})

def print_header(ws_connected: bool, model: str, output_on: bool = False):
    console.rule("[bold blue]COPILOT AGENT[/bold blue]")

def print_header_and_pad(ws_connected: bool, model: str, output_on: bool = False):
    print_header(ws_connected, model, output_on)
    term_h = shutil.get_terminal_size().lines
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
    for f in files[:20]:
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

def make_toolbar(state_sid: str, runner_connected: bool, model: str, output_on: bool):
    def _toolbar():
        term_width = shutil.get_terminal_size().columns
        top_line = "─" * (term_width - 2)
        bottom_line = "─" * (term_width - 2)

        ws_dot = '<style fg="ansigreen">●</style>' if runner_connected else '<style fg="ansired">●</style>'
        out_flag = ' <style fg="ansiyellow">[OUT]</style>' if output_on else ''
        out_plain = ' [OUT]' if output_on else ''
        
        left_text = f'{ws_dot} <style fg="ansiyellow">[{model}]</style> /new   /model   /help   /exit'
        left_plain = f'● [{model}] /new   /model   /help   /exit'
        
        sid = state_sid or "none"
        sid_short = sid[:10] + "…" if sid != "none" and len(sid) > 10 else sid
        right_plain = f'session: {sid_short}{out_plain}'
        
        content_width = term_width - 4 
        pad_len = content_width - len(left_plain) - len(right_plain)
        if pad_len < 1:
            pad_len = 1
        pad = " " * pad_len
        
        return HTML(
            f'<style fg="ansiblue">╭{top_line}╮</style>\n'
            f'<style fg="ansiblue">│</style> {left_text}{pad}<style fg="ansicyan">session: {sid_short}</style>{out_flag} <style fg="ansiblue">│</style>\n'
            f'<style fg="ansiblue">╰{bottom_line}╯</style>'
        )
    return _toolbar
