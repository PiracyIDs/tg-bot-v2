"""
Convenience entry point.
Run from the project root with:  python run.py

Equivalent to:  python -m bot.main
Both require you to be in the directory that CONTAINS the 'bot/' folder.
"""
import sys
import pathlib

# Guarantee the project root is on sys.path regardless of how/where Python
# was invoked.  This is the one place it's acceptable to mutate sys.path.
ROOT = pathlib.Path(__file__).parent.resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.main import main  # noqa: E402 — must come after path fix
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
