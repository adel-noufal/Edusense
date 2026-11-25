"""Locate external binaries (ffmpeg/ffprobe) reliably on Windows and POSIX.

The backend is often started from a shell whose PATH predates a WinGet install,
so `shutil.which("ffmpeg")` alone is not enough. Resolution order:

1. EDUSENSE_FFMPEG_PATH / EDUSENSE_FFPROBE_PATH (explicit override)
2. PATH (`shutil.which`)
3. WinGet "Links" shims (%LOCALAPPDATA%\\Microsoft\\WinGet\\Links)
4. WinGet package folders (Gyan.FFmpeg* under %LOCALAPPDATA%\\Microsoft\\WinGet\\Packages)
5. Common manual installs (C:\\ffmpeg\\bin, Program Files)

Nothing is downloaded: if ffmpeg is genuinely absent the caller gets None and
must degrade gracefully.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

_WINGET_LINKS = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links"
_WINGET_PACKAGES = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"


def _winget_package_matches(exe: str) -> list[Path]:
    if not _WINGET_PACKAGES.exists():
        return []
    found: list[Path] = []
    try:
        for package in _WINGET_PACKAGES.glob("Gyan.FFmpeg*"):
            found.extend(package.rglob(exe))
    except OSError:
        return found
    return found


def find_binary(name: str, env_var: str) -> Optional[str]:
    override = os.environ.get(env_var)
    if override:
        candidate = Path(override)
        if candidate.exists():
            return str(candidate)

    on_path = shutil.which(name)
    if on_path:
        return on_path

    exe = f"{name}.exe" if os.name == "nt" else name
    shim = _WINGET_LINKS / exe
    if shim.exists():
        return str(shim)

    matches = _winget_package_matches(exe)
    if matches:
        return str(matches[0])

    for base in (Path(r"C:\ffmpeg\bin"), Path(r"C:\Program Files\ffmpeg\bin")):
        candidate = base / exe
        if candidate.exists():
            return str(candidate)
    return None


def find_ffmpeg() -> Optional[str]:
    return find_binary("ffmpeg", "EDUSENSE_FFMPEG_PATH")


def find_ffprobe() -> Optional[str]:
    return find_binary("ffprobe", "EDUSENSE_FFPROBE_PATH")


def ffmpeg_available() -> bool:
    return find_ffmpeg() is not None
