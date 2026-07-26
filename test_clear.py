import asyncio
from prompt_toolkit import PromptSession
async def main():
    session = PromptSession()
    ans = await session.prompt_async("❯ ")
    print("\033[F\033[K", end="")
    print(f"YOU typed: {ans}")
asyncio.run(main())
