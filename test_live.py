import asyncio
import json
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.live import Live

console = Console()

def get_agent_panel(status: str):
    return Panel(
        Text(status, style="yellow"),
        title="[bold yellow]AGENT[/bold yellow]",
        border_style="yellow", padding=(0, 1),
    )

async def main():
    console.print("YOU: test session 3")
    with Live(get_agent_panel("↳ Opening new chat..."), refresh_per_second=10, console=console) as live:
        await asyncio.sleep(1)
        live.update(get_agent_panel("↳ Selecting model..."))
        await asyncio.sleep(1)
        live.update(get_agent_panel("↳ Waiting for response..."))
        await asyncio.sleep(1)
    
    console.print("COPILOT: Session 3 received")

asyncio.run(main())
