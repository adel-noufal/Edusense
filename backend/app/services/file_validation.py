import re
from typing import Tuple

# Standard magic byte signatures
PDF_MAGIC = b"%PDF"
DOCX_ZIP_MAGIC = b"PK\x03\x04"
EXECUTABLE_MAGICS = [
    b"MZ",              # DOS / Windows PE executable (.exe, .dll)
    b"\x7fELF",         # Linux ELF binary
    b"\xca\xfe\xba\xbe", # Java class / Mach-O Fat Binary
    b"\xce\xfa\xed\xfe", # Mach-O 32-bit
    b"\xcf\xfa\xed\xfe", # Mach-O 64-bit
]


def validate_file_signature(filename: str, first_bytes: bytes) -> Tuple[bool, str]:
    """
    Validates file content signature (magic bytes) against its declared extension.
    Guards against spoofed extensions (e.g. executable renamed to .pdf).

    Returns:
        (is_valid: bool, reason: str)
    """
    if not first_bytes:
        return False, "File is empty (0 bytes)."

    lower_name = (filename or "").lower()

    # Immediate rejection if file matches any known executable/binary header
    for exe_magic in EXECUTABLE_MAGICS:
        if first_bytes.startswith(exe_magic):
            return False, "Dangerous file content detected: executable binary format is not permitted."

    # Check for embedded script execution in uploaded documents
    header_1k = first_bytes[:1024].lower()
    if b"<script" in header_1k or b"javascript:" in header_1k:
        return False, "Dangerous file content detected: embedded script markup is not permitted."

    if lower_name.endswith(".pdf"):
        # Standard PDF files begin with %PDF within the first 1024 bytes (some generators prepend UTF-8 BOM or comments)
        if PDF_MAGIC in first_bytes[:1024]:
            return True, "Valid PDF signature."
        return False, "Invalid PDF file: content signature does not match PDF format (%PDF header missing)."

    if lower_name.endswith((".docx", ".pptx", ".xlsx")):
        # Modern Office files are ZIP archives starting with PK\x03\x04
        if first_bytes.startswith(DOCX_ZIP_MAGIC):
            return True, "Valid Office archive signature."
        return False, "Invalid Office document: content signature does not match expected format."

    if lower_name.endswith((".txt", ".md", ".csv", ".json")):
        # Ensure it's valid UTF-8 text without embedded null bytes
        if b"\x00" in first_bytes[:2048]:
            return False, "Invalid text document: binary null bytes detected in text content."
        try:
            first_bytes[:4096].decode("utf-8")
            return True, "Valid text signature."
        except UnicodeDecodeError:
            return False, "Invalid text document: content cannot be decoded as valid UTF-8 text."

    # Default: allow if no dangerous binary signature was detected
    return True, "File signature check passed."
