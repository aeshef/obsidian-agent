#!/usr/bin/env python3
"""English docstring omitted (see domain_messages.yaml)."""
import asyncio
import sys
from pathlib import Path

current_dir = Path(__file__).resolve().parent
package_parent = current_dir.parent

if str(package_parent) not in sys.path:
    sys.path.insert(0, str(package_parent))

from knowledge_bot.app.bot import main

if __name__ == "__main__":
    asyncio.run(main())
