"""Reverse UTF-8 -> Windows-1252 -> UTF-8 double encoding in place.

Only lines that actually round-trip cleanly are rewritten, so real code changes
and already-correct text are preserved.
"""
import sys

from mojibake import iter_text_files, repair_text, scan_text


def main(apply=False):
    changed = []
    leftover = []
    for rel, path, text in iter_text_files("."):
        if not scan_text(text):
            continue
        repaired, n = repair_text(text)
        remain = scan_text(repaired)
        changed.append((rel, n, len(remain)))
        if apply:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(repaired)
        if remain:
            leftover.append((rel, remain[0][:120]))

    for rel, n, remain in changed:
        print(f"{rel}: {n} lines repaired, {remain} left")
    print(f"\n{'REPAIRED' if apply else 'WOULD REPAIR'} FILES={len(changed)}")
    if leftover:
        print(f"LEFTOVER FILES={len(leftover)}")
        for rel, sample in leftover:
            print(f"  {rel}: {sample!r}")


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
