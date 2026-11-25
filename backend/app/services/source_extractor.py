"""Extract plain text from instructor-uploaded session resources for AI context."""
from pathlib import Path


def _read_text_file(path: Path, limit: int = 12000) -> str:
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return path.read_text(encoding=encoding)[:limit]
        except Exception:
            continue
    return ""


def _read_docx(path: Path, limit: int = 12000) -> str:
    try:
        from docx import Document
        doc = Document(str(path))
        parts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        return "\n".join(parts)[:limit]
    except Exception:
        return ""


def _read_pptx(path: Path, limit: int = 12000) -> str:
    try:
        from pptx import Presentation
        prs = Presentation(str(path))
        parts = []
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text.strip():
                    parts.append(shape.text.strip())
        return "\n".join(parts)[:limit]
    except Exception:
        return ""


def _read_pdf(path: Path, limit: int = 12000) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        parts = []
        for page in reader.pages[:20]:
            text = page.extract_text() or ""
            if text.strip():
                parts.append(text.strip())
        return "\n".join(parts)[:limit]
    except Exception:
        return ""


_WORDS_RE = __import__("re").compile(r"[\w'-]+", __import__("re").UNICODE)
_PARA_RE = __import__("re").compile(r"\n\s*\n")


def extract_text_from_file(file_path: str, file_type: str = "") -> str:
    path = Path(file_path)
    if not path.exists():
        return ""
    suffix = path.suffix.lower()
    mime = (file_type or "").lower()
    if suffix in {".txt", ".md", ".csv", ".json"}:
        return _read_text_file(path)
    if suffix in {".docx", ".doc"} or "word" in mime:
        return _read_docx(path)
    if suffix in {".pptx", ".ppt"} or "presentation" in mime or "powerpoint" in mime:
        return _read_pptx(path)
    if suffix == ".pdf" or "pdf" in mime:
        return _read_pdf(path)
    return ""


def _rank_passages(text: str, topic: str, limit: int = 16000) -> str:
    """Select the passages most relevant to the topic instead of the first pages.

    Cover pages, copyright notices and tables of contents are what the opening
    pages of a PDF contain, so dumping them produced videos about the title page.
    """
    topic_terms = {t for t in _WORDS_RE.findall((topic or "").lower()) if len(t) > 3}
    paragraphs = [p.strip() for p in _PARA_RE.split(text) if len(p.strip()) > 80]
    if not paragraphs:
        return text.strip()[:limit]
    if not topic_terms:
        return "\n\n".join(paragraphs)[:limit]

    ranked = []
    for index, paragraph in enumerate(paragraphs):
        words = set(_WORDS_RE.findall(paragraph.lower()))
        score = len(topic_terms & words)
        # Slight preference for earlier real content over the tail of the doc.
        ranked.append((score, -index, paragraph))
    ranked.sort(reverse=True)
    selected = [p for score, _, p in ranked if score > 0][:12]
    if not selected:
        selected = [p for _, _, p in ranked[:8]]
    return "\n\n".join(selected)[:limit]


def build_session_source_context(resources: list, topic: str = "") -> str:
    """Combine topic-relevant excerpts from multiple session resources."""
    chunks = []
    for resource in resources:
        text = extract_text_from_file(resource.file_path, getattr(resource, "file_type", "") or "")
        if text.strip():
            name = getattr(resource, "name", Path(resource.file_path).name)
            excerpts = _rank_passages(text, topic)
            chunks.append(f"--- Source: {name} ---\n{excerpts}")
    if not chunks:
        return ""
    combined = "\n\n".join(chunks)
    return combined[:16000]
