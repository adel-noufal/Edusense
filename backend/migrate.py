"""
EduSense Alembic Migration Helper
==================================
Run this script from the `backend/` directory using the project's venv.

Usage:
  python migrate.py upgrade        # Apply all pending migrations
  python migrate.py downgrade -1   # Roll back one migration
  python migrate.py current        # Show current migration state
  python migrate.py history        # Show migration history
  python migrate.py make "msg"     # Generate a new migration from model changes
"""

import sys
import subprocess
import os

ALEMBIC = os.path.join(os.path.dirname(__file__), ".venv", "Scripts", "alembic.exe")
if not os.path.exists(ALEMBIC):
    # Linux/macOS path
    ALEMBIC = os.path.join(os.path.dirname(__file__), ".venv", "bin", "alembic")


def run(args: list[str]):
    result = subprocess.run([ALEMBIC] + args, cwd=os.path.dirname(__file__))
    sys.exit(result.returncode)


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)

    cmd = args[0]

    if cmd == "upgrade":
        run(["upgrade", args[1] if len(args) > 1 else "head"])
    elif cmd == "downgrade":
        run(["downgrade", args[1] if len(args) > 1 else "-1"])
    elif cmd == "current":
        run(["current"])
    elif cmd == "history":
        run(["history", "--verbose"])
    elif cmd == "make":
        msg = args[1] if len(args) > 1 else "auto_migration"
        run(["revision", "--autogenerate", "-m", msg])
    else:
        # Pass through any alembic command directly
        run(args)