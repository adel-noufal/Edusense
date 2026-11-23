"""Export and reversibly archive leftover test/QA session rows (U11).

Usage (run from the backend folder):

    .venv/Scripts/python.exe scripts/archive_test_sessions.py            # dry run
    .venv/Scripts/python.exe scripts/archive_test_sessions.py --apply    # backup + archive
    .venv/Scripts/python.exe scripts/archive_test_sessions.py --restore data/backups/sessions-archive-...json

A row is archived only when its title is exactly "Empty Test Session",
"B5 Future" or "Test Session" AND it has no registrations, resources or reports.
The JSON backup is written before anything is modified, and --restore clears
archived_at, so the rows reappear with their original ids.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import SessionLocal  # noqa: E402
from app.services.session_archive import (  # noqa: E402
    TEST_TITLES,
    archive_rows,
    restore_rows,
    row_to_dict,
    find_test_session_rows,
)


def _describe(rows) -> None:
    print(f"Matched {len(rows)} of {len(TEST_TITLES)} title patterns "
          f"({', '.join(TEST_TITLES)}):")
    for row in rows:
        print(f"  id={row.id:>4}  {row.date}  {row.status:<10}  {row.title}")
    if not rows:
        print("  (nothing to do)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the backup and archive the rows")
    parser.add_argument("--restore", metavar="BACKUP_JSON", help="un-archive the ids listed in a backup")
    parser.add_argument("--backup-dir", default=str(BACKEND_DIR.parent / "data" / "backups"))
    args = parser.parse_args()

    from app.db.seed import init_db
    init_db(seed=False)  # ensures the archived_at column exists

    db = SessionLocal()
    try:
        if args.restore:
            payload = json.loads(Path(args.restore).read_text(encoding="utf-8"))
            ids = [int(item["id"]) for item in payload.get("sessions", [])]
            count = restore_rows(db, ids)
            print(f"Restored {count} session row(s): {ids}")
            return 0

        rows = find_test_session_rows(db)
        _describe(rows)
        if not rows:
            return 0
        if not args.apply:
            print("\nDry run only. Re-run with --apply to export and archive these rows.")
            return 0

        backup_dir = Path(args.backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = backup_dir / f"sessions-archive-{stamp}.json"
        payload = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "reason": "Reversible archive of leftover test/QA session rows (Addendum #13 U11)",
            "match_rules": {
                "titles": list(TEST_TITLES),
                "require_empty": ["registrations", "resources", "reports"],
            },
            "sessions": [row_to_dict(db, row) for row in rows],
        }
        backup_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nBackup written: {backup_path}")

        count = archive_rows(db, rows)
        print(f"Archived {count} row(s). Restore with:")
        print(f"  .venv/Scripts/python.exe scripts/archive_test_sessions.py --restore {backup_path}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
