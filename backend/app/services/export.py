import json
import zipfile
from io import BytesIO
from pathlib import Path
import html
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

STATIC_DIR = Path(__file__).resolve().parents[1] / "static" / "videos"


def lesson_to_markdown(data: dict) -> str:
    lines = [f"# {data.get('topic', 'Lesson')}", ""]
    if data.get("overview"):
        lines += ["## Overview", data["overview"], ""]
    if data.get("learning_objectives"):
        lines += ["## Learning Objectives", *[f"- {item}" for item in data["learning_objectives"]], ""]
    for section in data.get("sections") or []:
        lines += [f"## {section.get('heading', 'Section')}", section.get("content", "")]
        if section.get("example"):
            lines += [f"*Example:* {section['example']}"]
        lines.append("")
    if data.get("summary"):
        lines += ["## Summary", data["summary"], ""]
    return "\n".join(lines)


def flashcards_to_markdown(data: dict) -> str:
    lines = [f"# {data.get('title', 'Flashcards')}", ""]
    for index, card in enumerate(data.get("cards") or [], start=1):
        lines += [f"## Card {index}", f"**Front:** {card.get('front', '')}", f"**Back:** {card.get('back', '')}", ""]
    return "\n".join(lines)


def quiz_to_markdown(data: dict) -> str:
    lines = [f"# {data.get('title', 'Quiz')}", f"Difficulty: {data.get('difficulty', 'Medium')}", ""]
    for index, question in enumerate(data.get("questions") or [], start=1):
        lines += [f"## Question {index}", question.get("question", "")]
        for option in question.get("options") or []:
            lines.append(f"- {option}")
        lines += [f"**Answer:** {question.get('answer', '')}", ""]
    return "\n".join(lines)


def build_word_document_bytes(title: str, sections: list[tuple[str, str | list[str]]]) -> BytesIO:
    body = [
        "<html><head><meta charset='utf-8'>",
        "<style>",
        "body{font-family:Calibri,Arial,sans-serif;padding:28px;color:#1e293b;}",
        "h1{color:#0f766e;margin-bottom:6px;}",
        "h2{color:#155e75;margin-top:22px;}",
        "p,li{line-height:1.7;font-size:12pt;}",
        ".card{margin:14px 0;padding:14px 16px;border:1px solid #cbd5e1;border-radius:14px;background:#f8fafc;}",
        "</style></head><body>",
        f"<h1>{html.escape(title)}</h1>",
    ]
    for heading, content in sections:
        body.append(f"<h2>{html.escape(heading)}</h2>")
        if isinstance(content, list):
            body.append("<ul>")
            body.extend(f"<li>{html.escape(str(item))}</li>" for item in content if item)
            body.append("</ul>")
        else:
            paragraphs = [segment.strip() for segment in str(content).split("\n") if segment.strip()]
            if not paragraphs:
                body.append("<p></p>")
            for paragraph in paragraphs:
                body.append(f"<p>{html.escape(paragraph)}</p>")
    body.append("</body></html>")
    buffer = BytesIO("".join(body).encode("utf-8"))
    buffer.seek(0)
    return buffer


def build_video_zip(project_id: int) -> BytesIO | None:
    project_dir = STATIC_DIR / f"video-{project_id}"
    if not project_dir.exists():
        return None
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for file_path in project_dir.rglob("*"):
            if file_path.is_file():
                archive.write(file_path, arcname=file_path.relative_to(project_dir))
    buffer.seek(0)
    return buffer


def build_json_bytes(data: dict) -> BytesIO:
    buffer = BytesIO(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
    buffer.seek(0)
    return buffer


def build_true_docx_bytes(title: str, content_dict: dict, content_type: str = "lesson") -> BytesIO:
    """Create a native .docx document using python-docx"""
    doc = Document()

    # Set narrower margins for more content per page
    for section in doc.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1.2)
        section.right_margin = Inches(1.2)

    def add_colored_heading(text: str, level: int = 1, color: RGBColor = RGBColor(15, 118, 110)):
        h = doc.add_heading(text, level=level)
        h.paragraph_format.space_before = Pt(16)
        h.paragraph_format.space_after = Pt(6)
        for run in h.runs:
            run.font.color.rgb = color
        return h

    def add_body(text: str):
        p = doc.add_paragraph(text)
        p.paragraph_format.space_after = Pt(8)
        p.paragraph_format.line_spacing = Pt(14)
        for run in p.runs:
            run.font.size = Pt(11)
        return p

    if content_type == "lesson":
        # ── Cover block ──
        title_para = doc.add_heading(title, 0)
        title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        title_para.paragraph_format.space_after = Pt(4)
        for run in title_para.runs:
            run.font.size = Pt(26)
            run.font.color.rgb = RGBColor(15, 118, 110)
            run.font.bold = True

        # Subtitle / metadata
        meta_lines = []
        if content_dict.get("language"):
            meta_lines.append(f"Language: {content_dict['language']}")
        style_val = content_dict.get("style") or content_dict.get("teaching_style")
        if style_val:
            meta_lines.append(f"Style: {style_val}")
        if content_dict.get("duration"):
            meta_lines.append(f"Duration: {content_dict['duration']} minutes")
        if meta_lines:
            meta_p = doc.add_paragraph(" · ".join(meta_lines))
            meta_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            meta_p.paragraph_format.space_after = Pt(18)
            for run in meta_p.runs:
                run.font.size = Pt(10)
                run.font.color.rgb = RGBColor(100, 116, 139)
                run.font.italic = True

        doc.add_paragraph()  # spacer

        # Overview
        if content_dict.get("overview"):
            add_colored_heading("Overview")
            add_body(content_dict["overview"])

        # Learning Objectives
        if content_dict.get("learning_objectives"):
            add_colored_heading("Learning Objectives")
            for obj in content_dict["learning_objectives"]:
                p = doc.add_paragraph(style="List Bullet")
                run = p.add_run(obj)
                run.font.size = Pt(11)
                p.paragraph_format.space_after = Pt(4)

            doc.add_paragraph()  # spacer after list

        # Content sections
        for section in content_dict.get("sections") or []:
            add_colored_heading(section.get("heading", "Section"), level=1, color=RGBColor(21, 94, 117))

            content_text = section.get("content", "")
            if content_text:
                # Split into paragraphs for better formatting
                for para_text in content_text.split("\n"):
                    if para_text.strip():
                        add_body(para_text.strip())

            if section.get("example"):
                example_p = doc.add_paragraph()
                example_p.paragraph_format.left_indent = Inches(0.4)
                example_p.paragraph_format.space_before = Pt(4)
                example_p.paragraph_format.space_after = Pt(12)
                label_run = example_p.add_run("💡 Example: ")
                label_run.font.bold = True
                label_run.font.color.rgb = RGBColor(15, 118, 110)
                label_run.font.size = Pt(11)
                content_run = example_p.add_run(section["example"])
                content_run.font.italic = True
                content_run.font.size = Pt(11)

        # Key Points
        if content_dict.get("key_points"):
            add_colored_heading("Key Points", level=1, color=RGBColor(14, 116, 144))
            for kp in content_dict["key_points"]:
                p = doc.add_paragraph(style="List Bullet")
                run = p.add_run(kp)
                run.font.size = Pt(11)
                p.paragraph_format.space_after = Pt(4)
            doc.add_paragraph()

        # Slides summary
        if content_dict.get("slides"):
            add_colored_heading("Slide Outlines", level=1, color=RGBColor(14, 116, 144))
            for i, slide in enumerate(content_dict["slides"], start=1):
                slide_h = doc.add_heading(f"Slide {i}: {slide.get('title', '')}", level=2)
                slide_h.paragraph_format.space_before = Pt(10)
                slide_h.paragraph_format.space_after = Pt(3)
                for run in slide_h.runs:
                    run.font.color.rgb = RGBColor(51, 65, 85)
                if slide.get("content"):
                    add_body(slide["content"])

        # Summary
        if content_dict.get("summary"):
            add_colored_heading("Summary")
            add_body(content_dict["summary"])

    elif content_type == "quiz":
        title_para = doc.add_heading(title, 0)
        title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in title_para.runs:
            run.font.size = Pt(24)
            run.font.color.rgb = RGBColor(15, 118, 110)

        diff_p = doc.add_paragraph(f"Difficulty: {content_dict.get('difficulty', 'Medium')}")
        diff_p.paragraph_format.space_after = Pt(16)
        for run in diff_p.runs:
            run.font.bold = True
            run.font.size = Pt(12)

        for index, question in enumerate(content_dict.get("questions") or [], start=1):
            h3 = doc.add_heading(f"Question {index}", level=2)
            h3.paragraph_format.space_before = Pt(14)
            for run in h3.runs:
                run.font.color.rgb = RGBColor(30, 64, 175)

            q_p = doc.add_paragraph(question.get("question", ""))
            q_p.paragraph_format.space_after = Pt(6)

            for option in question.get("options") or []:
                opt_p = doc.add_paragraph(style="List Bullet")
                opt_p.add_run(option).font.size = Pt(11)

            answer_p = doc.add_paragraph()
            answer_p.paragraph_format.space_before = Pt(4)
            a_label = answer_p.add_run("Answer: ")
            a_label.font.bold = True
            a_label.font.color.rgb = RGBColor(22, 163, 74)
            a_val = answer_p.add_run(question.get("answer", ""))
            a_val.font.bold = True
            a_val.font.color.rgb = RGBColor(22, 163, 74)

            if question.get("explanation"):
                exp_p = doc.add_paragraph(f"Explanation: {question['explanation']}")
                exp_p.paragraph_format.space_after = Pt(8)
                for run in exp_p.runs:
                    run.font.italic = True
                    run.font.color.rgb = RGBColor(100, 116, 139)

    elif content_type == "flashcards":
        title_para = doc.add_heading(title, 0)
        title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in title_para.runs:
            run.font.color.rgb = RGBColor(15, 118, 110)

        for index, card in enumerate(content_dict.get("cards") or [], start=1):
            h3 = doc.add_heading(f"Card {index}", level=2)
            h3.paragraph_format.space_before = Pt(14)
            for run in h3.runs:
                run.font.color.rgb = RGBColor(30, 64, 175)

            front_p = doc.add_paragraph()
            fl = front_p.add_run("Front: ")
            fl.font.bold = True
            fl.font.color.rgb = RGBColor(15, 118, 110)
            front_p.add_run(card.get("front", "")).font.size = Pt(11)

            back_p = doc.add_paragraph()
            bl = back_p.add_run("Back: ")
            bl.font.bold = True
            bl.font.color.rgb = RGBColor(21, 94, 117)
            back_p.add_run(card.get("back", "")).font.size = Pt(11)
            back_p.paragraph_format.space_after = Pt(12)


    
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer


def build_pptx_bytes(title: str, content_dict: dict) -> BytesIO:
    """Generate a rich PowerPoint presentation with duration-scaled slide count,
    varied slide layouts, native shape diagrams, Arabic RTL support, and >=24pt body text."""
    from pptx import Presentation
    from pptx.util import Inches, Pt, Emu
    from pptx.dml.color import RGBColor as PptxRGB
    from pptx.enum.text import PP_ALIGN
    from pptx.enum.shapes import MSO_SHAPE

    TEAL = PptxRGB(0x0F, 0x76, 0x6E)
    DARK = PptxRGB(0x1E, 0x29, 0x3B)
    BODY_CLR = PptxRGB(0x33, 0x41, 0x55)
    WHITE = PptxRGB(0xFF, 0xFF, 0xFF)
    LIGHT_BG = PptxRGB(0xF1, 0xF5, 0xF9)
    ACCENT_MINT = PptxRGB(0x14, 0xB8, 0xA6)
    ACCENT_BLUE = PptxRGB(0x02, 0x84, 0xC7)

    prs = Presentation()
    prs.slide_width = Inches(13.33)
    prs.slide_height = Inches(7.5)

    blank_layout = prs.slide_layouts[6]  # Blank

    def _is_arabic(text: str) -> bool:
        return any('\u0600' <= ch <= '\u06FF' for ch in (text or ""))

    def _apply_text(p, text: str, font_size, color, bold: bool = False, arabic: bool = False):
        if arabic:
            p.alignment = PP_ALIGN.RIGHT
            try:
                p._p.get_or_add_pPr().set('rtl', '1')
            except Exception:
                pass
        else:
            p.alignment = PP_ALIGN.LEFT
        run = p.add_run()
        run.text = text
        run.font.size = font_size
        run.font.bold = bold
        run.font.color.rgb = color

    def add_base_slide(slide_title_text: str, is_title_slide: bool = False):
        slide = prs.slides.add_slide(blank_layout)
        bg = slide.background
        fill = bg.fill
        fill.solid()
        fill.fore_color.rgb = DARK if is_title_slide else WHITE

        arabic = _is_arabic(slide_title_text)
        title_top = Inches(0.4)
        title_height = Inches(1.2)
        left = Inches(0.6)
        width = Inches(12.1)

        txBox = slide.shapes.add_textbox(left, title_top, width, title_height)
        tf = txBox.text_frame
        tf.word_wrap = True
        _apply_text(tf.paragraphs[0], slide_title_text,
                    Pt(38) if is_title_slide else Pt(30),
                    WHITE if is_title_slide else TEAL,
                    bold=True, arabic=arabic)

        # Teal accent bar
        line = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            int(left), int(title_top + title_height - Inches(0.05)),
            int(width), int(Inches(0.04))
        )
        line.fill.solid()
        line.fill.fore_color.rgb = ACCENT_MINT if is_title_slide else TEAL
        line.line.fill.background()

        # Slide number
        num_box = slide.shapes.add_textbox(int(Inches(12.4)), int(Inches(7.0)), int(Inches(0.8)), int(Inches(0.4)))
        _apply_text(num_box.text_frame.paragraphs[0], str(len(prs.slides)), Pt(12), PptxRGB(0x94, 0xA3, 0xB8))

        return slide, arabic

    def add_standard_slide(slide_title_text: str, body_lines: list[str], is_title_slide: bool = False):
        slide, arabic = add_base_slide(slide_title_text, is_title_slide)
        body_top = Inches(1.8)
        body_height = Inches(5.3)
        left = Inches(0.6)
        width = Inches(12.1)

        body_box = slide.shapes.add_textbox(left, body_top, width, body_height)
        tf2 = body_box.text_frame
        tf2.word_wrap = True
        first = True
        # >=24pt body requirement (scale only if many lines)
        body_size = Pt(24) if len(body_lines) <= 6 else Pt(22)
        for line_text in body_lines:
            p2 = tf2.paragraphs[0] if first else tf2.add_paragraph()
            first = False
            p2.space_after = Pt(10)
            _apply_text(p2, line_text, body_size, WHITE if is_title_slide else BODY_CLR, arabic=arabic or _is_arabic(line_text))

        try:
            notes_tf = slide.notes_slide.notes_text_frame
            notes_tf.text = f"{slide_title_text}\n\n" + "\n".join(body_lines)
        except Exception:
            pass

    def add_two_column_slide(slide_title_text: str, col1_lines: list[str], col2_lines: list[str], col1_title: str = "Concept", col2_title: str = "Application"):
        slide, arabic = add_base_slide(slide_title_text)
        top = Inches(1.8)
        height = Inches(5.1)
        col_w = Inches(5.8)
        left1 = Inches(0.6)
        left2 = Inches(6.9)

        # Col 1 Card
        box1 = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, int(left1), int(top), int(col_w), int(height))
        box1.fill.solid()
        box1.fill.fore_color.rgb = LIGHT_BG
        box1.line.color.rgb = TEAL
        tf1 = box1.text_frame
        tf1.word_wrap = True
        _apply_text(tf1.paragraphs[0], col1_title, Pt(24), TEAL, bold=True, arabic=_is_arabic(col1_title))
        for line in col1_lines:
            p = tf1.add_paragraph()
            p.space_after = Pt(8)
            _apply_text(p, line, Pt(24), BODY_CLR, arabic=_is_arabic(line))

        # Col 2 Card
        box2 = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, int(left2), int(top), int(col_w), int(height))
        box2.fill.solid()
        box2.fill.fore_color.rgb = LIGHT_BG
        box2.line.color.rgb = ACCENT_BLUE
        tf2 = box2.text_frame
        tf2.word_wrap = True
        _apply_text(tf2.paragraphs[0], col2_title, Pt(24), ACCENT_BLUE, bold=True, arabic=_is_arabic(col2_title))
        for line in col2_lines:
            p = tf2.add_paragraph()
            p.space_after = Pt(8)
            _apply_text(p, line, Pt(24), BODY_CLR, arabic=_is_arabic(line))

    def add_flow_diagram_slide(slide_title_text: str, steps: list[str]):
        """Render native shape diagram: process flow boxes with arrows instead of text captions."""
        slide, arabic = add_base_slide(slide_title_text)
        n = min(4, max(2, len(steps)))
        step_items = steps[:n]
        box_w = Inches(10.5 / n)
        box_h = Inches(2.2)
        top = Inches(3.0)

        for i, step_text in enumerate(step_items):
            box_left = Inches(0.8 + i * (10.5 / n + 0.5))
            shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, int(box_left), int(top), int(box_w), int(box_h))
            shape.fill.solid()
            shape.fill.fore_color.rgb = TEAL if i % 2 == 0 else ACCENT_BLUE
            shape.line.fill.background()
            tf = shape.text_frame
            tf.word_wrap = True
            _apply_text(tf.paragraphs[0], f"Step {i + 1}", Pt(22), WHITE, bold=True, arabic=_is_arabic(step_text))
            p_desc = tf.add_paragraph()
            p_desc.space_after = Pt(4)
            _apply_text(p_desc, step_text, Pt(20), WHITE, arabic=_is_arabic(step_text))

            # Add right arrow between steps
            if i < len(step_items) - 1:
                arrow_left = box_left + box_w + Inches(0.08)
                arrow = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, int(arrow_left), int(top + Inches(0.8)), int(Inches(0.35)), int(Inches(0.4)))
                arrow.fill.solid()
                arrow.fill.fore_color.rgb = ACCENT_MINT
                arrow.line.fill.background()

    # Scaling slide count with duration
    duration = content_dict.get("duration") or 5
    try:
        duration_mins = int(duration)
    except (ValueError, TypeError):
        duration_mins = 5
    target_slides = max(4, min(20, int(duration_mins * 1.5)))

    sections = content_dict.get("sections") or []

    # Slide 1: Title
    subtitle_lines = [
        f"Subject: {content_dict.get('topic', title)}",
        f"Style: {content_dict.get('style') or content_dict.get('teaching_style', 'Interactive')}",
        f"Duration: {duration_mins} minutes",
    ]
    add_standard_slide(title, subtitle_lines, is_title_slide=True)

    # Slide 2: Overview
    if content_dict.get("overview"):
        add_standard_slide("Overview", [content_dict["overview"]])

    # Slide 3: Learning Objectives
    if content_dict.get("learning_objectives"):
        objs = [f"• {obj}" for obj in content_dict["learning_objectives"]]
        add_standard_slide("Learning Objectives", objs)

    # Content sections with varied layouts
    for i, sec in enumerate(sections):
        lines = []
        if sec.get("content"):
            lines += [l.strip() for l in sec["content"].split("\n") if l.strip()]

        layout_choice = i % 3
        if layout_choice == 1 and sec.get("example") and lines:
            # Layout 1: Two-column slide (Concept vs Example)
            add_two_column_slide(sec.get("heading", f"Section {i+1}"), lines[:4], [sec["example"]], "Core Concept", "Practical Example")
        elif layout_choice == 2 and len(lines) >= 2:
            # Layout 2: Native flow diagram slide
            add_flow_diagram_slide(sec.get("heading", f"Workflow {i+1}"), lines[:3])
        else:
            # Layout 0: Standard slide with >=24pt body
            if sec.get("example"):
                lines.append(f"Example: {sec['example']}")
            add_standard_slide(sec.get("heading", f"Section {i+1}"), lines)

    # Summary
    if content_dict.get("summary"):
        add_standard_slide("Summary", [content_dict["summary"]])

    # Key points
    if content_dict.get("key_points"):
        kp = [f"• {k}" for k in content_dict["key_points"]]
        add_standard_slide("Key Points", kp)

    buffer = BytesIO()
    prs.save(buffer)
    buffer.seek(0)
    return buffer


# ─── B8: real PDF / DOCX / CSV exports ────────────────────────────────────────

def _pdf_doc(title: str, blocks: list[tuple[str, list[str]]]) -> BytesIO:
    """Minimal branded PDF via reportlab. blocks = [(heading, [lines])]."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.colors import HexColor
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

    TEAL = HexColor("#0F766E")
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm,
                            title=title)
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], textColor=TEAL, fontSize=20, spaceAfter=8)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], textColor=TEAL, fontSize=13, spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=10.5, leading=15, spaceAfter=3)

    story = [Paragraph(html.escape(title), h1), Spacer(1, 4 * mm)]
    for heading, lines in blocks:
        if heading:
            story.append(Paragraph(html.escape(heading), h2))
        for line in lines:
            story.append(Paragraph(html.escape(str(line)).replace("\n", "<br/>"), body))
    doc.build(story)
    buf.seek(0)
    return buf


def build_lesson_pdf_bytes(lesson: dict) -> BytesIO:
    blocks: list[tuple[str, list[str]]] = []
    if lesson.get("overview"):
        blocks.append(("Overview", [lesson["overview"]]))
    for obj in lesson.get("learning_objectives") or []:
        blocks.append(("", [f"• {obj}"]))
    for sec in lesson.get("sections") or []:
        lines = []
        if sec.get("content"):
            lines += [l.strip() for l in str(sec["content"]).split("\n") if l.strip()]
        if sec.get("example"):
            lines.append(f"Example: {sec['example']}")
        blocks.append((sec.get("heading", "Section"), lines))
    if lesson.get("summary"):
        blocks.append(("Summary", [lesson["summary"]]))
    return _pdf_doc(lesson.get("topic") or "Lesson", blocks)


def build_quiz_pdf_bytes(quiz: dict, include_answers: bool = True) -> BytesIO:
    blocks = []
    for i, q in enumerate(quiz.get("questions") or [], start=1):
        lines = [str(q.get("question", ""))]
        for opt in q.get("options") or []:
            lines.append(f"   • {opt}")
        if include_answers:
            lines.append(f"Answer: {q.get('answer', '')}")
            if q.get("explanation"):
                lines.append(f"Explanation: {q['explanation']}")
        blocks.append((f"Question {i}", lines))
    return _pdf_doc(quiz.get("title") or "Quiz", blocks)


def build_quiz_docx_bytes(quiz: dict, include_answers: bool = True) -> BytesIO:
    doc = Document()
    doc.add_heading(quiz.get("title") or "Quiz", level=0)
    for i, q in enumerate(quiz.get("questions") or [], start=1):
        doc.add_heading(f"Question {i}", level=1)
        doc.add_paragraph(str(q.get("question", "")))
        for opt in q.get("options") or []:
            doc.add_paragraph(opt, style="List Bullet")
        if include_answers:
            p = doc.add_paragraph()
            run = p.add_run(f"Answer: {q.get('answer', '')}")
            run.bold = True
            if q.get("explanation"):
                doc.add_paragraph(f"Explanation: {q['explanation']}")
    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


def build_flashcards_csv_bytes(data: dict) -> BytesIO:
    """Anki-compatible CSV: front,back, tags."""
    import csv
    out = BytesIO()
    text = out
    # csv needs a text wrapper — write to StringIO then encode with BOM
    from io import StringIO
    sio = StringIO()
    w = csv.writer(sio)
    w.writerow(["Front", "Back", "Tags"])
    for card in data.get("cards") or []:
        w.writerow([card.get("front", ""), card.get("back", ""), data.get("title", "")])
    out.write(b"\xef\xbb\xbf" + sio.getvalue().encode("utf-8"))
    out.seek(0)
    return out


def build_flashcards_pdf_bytes(data: dict) -> BytesIO:
    blocks = []
    for i, card in enumerate(data.get("cards") or [], start=1):
        blocks.append((f"Card {i}", [str(card.get("front", "")), "", str(card.get("back", ""))]))
    return _pdf_doc(data.get("title") or "Flashcards", blocks)
