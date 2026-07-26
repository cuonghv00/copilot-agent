import asyncio
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout

async def background_task():
    for i in range(3):
        await asyncio.sleep(2)
        print(f"Async log {i}")

async def main():
    session = PromptSession()
    asyncio.create_task(background_task())
    with patch_stdout():
        ans = await session.prompt_async("❯ ")
    print(f"Done: {ans}")

asyncio.run(main())
