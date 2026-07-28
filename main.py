#!/usr/bin/env python3
import asyncio
import sys
from agent.cli import main_loop

# Windows: dùng SelectorEventLoop thay vì ProactorEventLoop mặc định.
# ProactorEventLoop có vấn đề với websockets trên một số phiên bản Python/Windows.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        pass
