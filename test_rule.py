from rich.console import Console, Group
from rich.rule import Rule
from rich.text import Text
from rich.live import Live
import time

console = Console()

console.rule("[bold cyan]You[/bold cyan]", style="cyan")
console.print("test switch model in this session\n")

def get_agent_panel(status):
    return Group(
        Rule("[bold yellow]Agent[/bold yellow]", style="yellow"),
        Text(status, style="yellow")
    )

with Live(get_agent_panel("↳ Prompt sent\n↳ Waiting for Copilot response..."), console=console):
    time.sleep(2)

console.print("\n")
console.rule("[bold green]M365 Copilot[/bold green]", style="green")
console.print("Đã giữ nguyên session và model như bạn yêu cầu...")
