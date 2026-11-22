"""Scan git-tracked text files for UTF-8 mojibake (double-encoded UTF-8).

Exit code 1 when any mojibake line is found, so it can gate verify/CI.
"""
import sys

from mojibake import iter_text_files, scan_text


def scan(root=".", verbose=True):
    hits = {}
    for rel, _path, text in iter_text_files(root, extended=True):
        bad = scan_text(text)
        if bad:
            hits[rel] = bad
    total = sum(len(v) for v in hits.values())
    if verbose:
        for rel in sorted(hits, key=lambda x: -len(hits[x])):
            sample = hits[rel][0][:100]
            print(f"{rel}: {len(hits[rel])} lines, e.g. {sample!r}")
        print()
        print(f"FILES={len(hits)} LINES={total}")
    return hits, total


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    _, total = scan(root)
    sys.exit(1 if total else 0)
