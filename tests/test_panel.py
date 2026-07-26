from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()

console.print(Panel(
    Text("test ui", style="white"),
    title="[bold cyan]YOU[/bold cyan]",
    title_align="left",
    border_style="cyan", 
    padding=(0, 2),
    expand=False
))
