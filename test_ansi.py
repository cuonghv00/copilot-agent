import asyncio
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console
console = Console()
async def background_task():
    for i in range(2):
        await asyncio.sleep(1)
        console.print("[green]✓ Chrome Extension connected[/green]")
async def main():
    session = PromptSession()
    asyncio.create_task(background_task())
    with patch_stdout():
        ans = await session.prompt_async("❯ ")
asyncio.run(main())
