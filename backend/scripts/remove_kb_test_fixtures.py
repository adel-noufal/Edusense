"""Remove test-only fixtures from the live Knowledge Base (U7).

`test_async_guide.pdf` and `notes.txt` were indexed into the live collection by
API-level tests on 2026-11-23. This script exports their chunks (text + metadata)
to data/backups/ first, then deletes only those two sources. Real documents are
never touched.

    .venv/Scripts/python.exe scripts/remove_kb_test_fixtures.py           # dry run
    .venv/Scripts/python.exe scripts/remove_kb_test_fixtures.py --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings  # noqa: E402

FIXTURE_SOURCES = ("test_async_guide.pdf", "notes.txt")
COLLECTION = "edusense_knowledge"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="export the chunks then delete them")
    parser.add_argument("--backup-dir", default=str(BACKEND_DIR.parent / "data" / "backups"))
    args = parser.parse_args()

    import chromadb

    settings = get_settings()
    client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
    names = {c.name if hasattr(c, "name") else str(c) for c in client.list_collections()}
    if COLLECTION not in names:
        print(f"Collection {COLLECTION} not found in {settings.chroma_persist_dir}")
        return 1
    collection = client.get_collection(COLLECTION)

    exported = []
    ids_to_delete = []
    for source in FIXTURE_SOURCES:
        found = collection.get(where={"source_id": source}, include=["documents", "metadatas"])
        for chunk_id, text, meta in zip(found["ids"], found["documents"], found["metadatas"]):
            exported.append({"id": chunk_id, "text": text, "metadata": meta})
            ids_to_delete.append(chunk_id)
        print(f"{source}: {len(found['ids'])} chunk(s)")

    if not ids_to_delete:
        print("No test fixtures in the live collection.")
        return 0
    if not args.apply:
        print("\nDry run only. Re-run with --apply to export and delete these chunks.")
        return 0

    backup_dir = Path(args.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = backup_dir / f"kb-test-fixtures-{stamp}.json"
    backup_path.write_text(json.dumps({
        "created_at": datetime.now(timezone.utc).isoformat(),
        "collection": COLLECTION,
        "persist_dir": settings.chroma_persist_dir,
        "reason": "Test fixtures indexed into the live KB by API-level tests (Addendum #13 U7)",
        "chunks": exported,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nBackup written: {backup_path}")

    collection.delete(ids=ids_to_delete)
    print(f"Deleted {len(ids_to_delete)} fixture chunk(s). Remaining count: {collection.count()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
