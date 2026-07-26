#!/usr/bin/env python3
import asyncio
from agent.cli import main_loop

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        pass
