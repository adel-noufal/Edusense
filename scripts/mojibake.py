"""Core helpers for detecting and reversing UTF-8 mojibake.

Mojibake here means: UTF-8 bytes decoded as Windows-1252 and re-saved as UTF-8.
A line is considered mojibake when re-encoding it to Windows-1252 bytes and
decoding those bytes as UTF-8 succeeds and produces text with fewer
"mis-decoded" characters than the original.

Ordinary accented text (e.g. "cafe\u0301" or "\u00e9") does not round-trip that
way because a lone 0xE9 byte is not a valid UTF-8 start byte, so false
positives are avoided.
"""
import os
import subprocess

C1_CONTROLS = set(range(0x80, 0xA0))


def tracked_files(root="."):
    out = subprocess.run(
        ["git", "ls-files"], cwd=root, capture_output=True, text=True, encoding="utf-8"
    )
    return [f for f in out.stdout.splitlines() if f]


TEXT_EXTENSIONS = {
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".json", ".html", ".htm",
    ".css", ".scss", ".md", ".txt", ".py", ".svg", ".yml", ".yaml", ".bat",
    ".ps1", ".sql", ".toml", ".ini", ".cfg", ".xml", ".csv",
}

# Build output is often git-ignored but is exactly what a browser serves, so
# the scanner must inspect it too (addendum #11 §5).
BUILD_DIRS = ("frontend/dist", "dist", "build")


def working_tree_files(root="."):
    """Tracked + untracked (not ignored) files."""
    out = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard"],
        cwd=root, capture_output=True, text=True, encoding="utf-8",
    )
    return [f for f in out.stdout.splitlines() if f]


def build_files(root="."):
    found = []
    for build_dir in BUILD_DIRS:
        base = os.path.join(root, build_dir)
        if not os.path.isdir(base):
            continue
        for dirpath, _dirnames, filenames in os.walk(base):
            for name in filenames:
                if os.path.splitext(name)[1].lower() in TEXT_EXTENSIONS:
                    found.append(os.path.relpath(os.path.join(dirpath, name), root))
    return found


def encode_cp1252(text):
    """Encode like Windows-1252, keeping undefined C1 code points as raw bytes."""
    out = bytearray()
    for ch in text:
        try:
            out += ch.encode("cp1252")
        except UnicodeEncodeError:
            if ord(ch) in C1_CONTROLS:
                out.append(ord(ch))
            else:
                raise
    return bytes(out)


def _suspicion(text):
    """Higher means more likely to be mojibake."""
    score = 0
    for ch in text:
        cp = ord(ch)
        if cp in C1_CONTROLS:
            score += 3
        elif 0xA0 <= cp <= 0xFF:
            score += 1
        elif cp >= 0x2000 and cp not in (0x2018, 0x2019, 0x201C, 0x201D, 0x2013, 0x2014):
            # Typographic punctuation produced by mojibake is not suspicious by
            # itself; genuine CJK/Arabic/emoji is definitely not.
            score -= 1
    return score


def try_fix_line(line):
    """Return repaired line, or None if the line is not reversible mojibake."""
    if not line or line.isascii():
        return None
    try:
        repaired = encode_cp1252(line).decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return None
    if repaired == line:
        return None
    if _suspicion(repaired) >= _suspicion(line):
        return None
    return repaired


def line_has_mojibake(line):
    return try_fix_line(line) is not None


def scan_text(text):
    newline = "\r\n" if "\r\n" in text else "\n"
    return [ln for ln in text.split(newline) if line_has_mojibake(ln)]


def read_text(path):
    data = open(path, "rb").read()
    if b"\x00" in data[:4000]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def repair_text(text):
    newline = "\r\n" if "\r\n" in text else "\n"
    had_trailing = text.endswith(newline)
    out = []
    changed = 0
    for line in text.split(newline):
        fixed = try_fix_line(line)
        if fixed is None:
            out.append(line)
        else:
            out.append(fixed)
            changed += 1
    repaired = newline.join(out)
    if had_trailing and not repaired.endswith(newline):
        repaired += newline
    return repaired, changed


def iter_text_files(root=".", extended=False):
    """Yield (relative path, full path, text) for scannable text files.

    extended=True also covers untracked, non-ignored files and built bundles
    (frontend/dist), so a stale compiled string cannot hide from the gate.
    """
    seen = set()
    sources = tracked_files(root)
    if extended:
        sources = sources + working_tree_files(root) + build_files(root)
    for rel in sources:
        rel = rel.replace("\\", "/")
        if rel in seen:
            continue
        seen.add(rel)
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            continue
        if os.path.splitext(rel)[1].lower() not in TEXT_EXTENSIONS:
            continue
        if rel.endswith(("package-lock.json", "package.json")) and not extended:
            pass
        text = read_text(path)
        if text is None:
            continue
        yield rel, path, text
