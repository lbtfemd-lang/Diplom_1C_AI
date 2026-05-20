"""
Build DOCX from markdown with correct academic formatting:
- Times New Roman 14pt, 1.5 line spacing
- First-line indent 1.25 cm for body paragraphs
- Justified alignment
- Proper bullet/numbered lists
- Code blocks in Courier New 10pt
- Images at full page width
"""
import os
import re
from docx import Document
from docx.shared import Inches, Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn

BASE = os.path.dirname(os.path.abspath(__file__))
MD_PATH = os.path.join(BASE, "04_Глава4_БЖД.md")
FIGURES_DIR = os.path.join(BASE, "figures")
OUT_PATH = os.path.join(BASE, "Глава4_БЖД.docx")

PAGE_WIDTH_CM = 21.0
PAGE_HEIGHT_CM = 29.7
LEFT_CM = 3.0
RIGHT_CM = 1.5
TOP_CM = 2.0
BOTTOM_CM = 2.0

FIGURE_MAP = {
    "Рисунок 4.1": "fig_4_1.png",
}


def set_run_font(run, name="Times New Roman", size=14, bold=False, italic=False, color=RGBColor(0x1A, 0x1A, 0x2E)):
    run.font.name = name
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    run._element.rPr.rFonts.set(qn('w:eastAsia'), name)


def setup_styles(doc):
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(14)
    style.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    style.paragraph_format.space_after = Pt(0)
    style.paragraph_format.space_before = Pt(0)
    style.paragraph_format.first_line_indent = Cm(1.25)
    style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    h1 = doc.styles["Heading 1"]
    h1.font.name = "Times New Roman"
    h1.font.size = Pt(14)
    h1.font.bold = True
    h1.font.italic = False
    h1.font.color.rgb = RGBColor(0x00, 0x00, 0x00)
    h1.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
    h1.paragraph_format.first_line_indent = Cm(1.25)
    h1.paragraph_format.space_before = Pt(12)
    h1.paragraph_format.space_after = Pt(6)
    h1.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE

    h2 = doc.styles["Heading 2"]
    h2.font.name = "Times New Roman"
    h2.font.size = Pt(14)
    h2.font.bold = True
    h2.font.italic = False
    h2.font.color.rgb = RGBColor(0x00, 0x00, 0x00)
    h2.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
    h2.paragraph_format.first_line_indent = Cm(1.25)
    h2.paragraph_format.space_before = Pt(12)
    h2.paragraph_format.space_after = Pt(6)
    h2.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE

    h3 = doc.styles["Heading 3"]
    h3.font.name = "Times New Roman"
    h3.font.size = Pt(14)
    h3.font.bold = True
    h3.font.italic = False
    h3.font.color.rgb = RGBColor(0x00, 0x00, 0x00)
    h3.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
    h3.paragraph_format.first_line_indent = Cm(1.25)
    h3.paragraph_format.space_before = Pt(12)
    h3.paragraph_format.space_after = Pt(6)
    h3.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE


def set_page_size(doc):
    section = doc.sections[0]
    section.page_width = Cm(PAGE_WIDTH_CM)
    section.page_height = Cm(PAGE_HEIGHT_CM)
    section.left_margin = Cm(LEFT_CM)
    section.right_margin = Cm(RIGHT_CM)
    section.top_margin = Cm(TOP_CM)
    section.bottom_margin = Cm(BOTTOM_CM)


def add_image(doc, png_name, caption_text):
    path = os.path.join(FIGURES_DIR, png_name)
    if not os.path.exists(path):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(f"[Место для {png_name} — файл не найден]")
        set_run_font(run, italic=True, size=12, color=RGBColor(0x7F, 0x8C, 0x8D))
        return

    # Image
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    max_width = Inches((PAGE_WIDTH_CM - LEFT_CM - RIGHT_CM) / 2.54)
    run.add_picture(path, width=max_width)

    # Caption
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = cap.add_run(caption_text)
    set_run_font(run, italic=True, size=12)
    cap.paragraph_format.space_after = Pt(12)
    cap.paragraph_format.space_before = Pt(6)


def add_body_paragraph(doc, text, indent=True, bold=False):
    """Add a normal body paragraph with proper academic formatting."""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.space_before = Pt(0)
    if indent:
        p.paragraph_format.first_line_indent = Cm(1.25)
    else:
        p.paragraph_format.first_line_indent = Cm(0)
    run = p.add_run(text.strip())
    set_run_font(run, bold=bold)
    return p


def add_bullet_paragraph(doc, text, level=0):
    p = doc.add_paragraph(style='List Paragraph')
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.left_indent = Cm(1.25 + level * 0.6)
    p.paragraph_format.first_line_indent = Cm(-0.6)
    run = p.add_run(text.strip())
    set_run_font(run)
    return p


def add_number_paragraph(doc, text, level=0):
    p = doc.add_paragraph(style='List Paragraph')
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.left_indent = Cm(1.25 + level * 0.6)
    p.paragraph_format.first_line_indent = Cm(-0.6)
    num_run = p.add_run()
    num_run.font.name = "Times New Roman"
    num_run.font.size = Pt(14)
    run = p.add_run(text.strip())
    set_run_font(run)
    return p


def add_code_block(doc, code_text):
    """Add a code block paragraph."""
    lines = code_text.splitlines()
    for line in lines:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.first_line_indent = Cm(0)
        run = p.add_run(line)
        set_run_font(run, name="Times New Roman", size=12, color=RGBColor(0x2C, 0x3E, 0x50))
    # Add small spacing after code block
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.space_before = Pt(0)


def parse_markdown(md_text):
    """Yield structured blocks."""
    lines = md_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Heading
        m = re.match(r'^(#{1,3})\s+(.*)$', stripped)
        if m:
            level = len(m.group(1))
            text = m.group(2)
            yield ('heading', text, {'level': level})
            i += 1
            continue

        # Empty line
        if not stripped:
            i += 1
            continue

        # Figure reference
        fig_m = re.match(r'^(Рисунок\s+\d+\.\d+.*)$', stripped)
        if fig_m:
            caption = fig_m.group(1)
            yield ('figure', caption, {})
            i += 1
            continue

        # Code fragment label
        frag_m = re.match(r'^(Фрагмент:\s+.*)$', stripped)
        if frag_m:
            yield ('fragment_label', frag_m.group(1), {})
            i += 1
            continue

        # Code block
        if stripped.startswith('```'):
            lang = stripped[3:].strip()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code_lines.append(lines[i])
                i += 1
            yield ('code', '\n'.join(code_lines), {'lang': lang})
            i += 1
            continue

        # Table
        if stripped.startswith('|') and '|' in stripped[1:]:
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_lines.append(lines[i].strip())
                i += 1
            yield ('table', '\n'.join(table_lines), {})
            continue

        # Collect paragraph/list lines
        para_lines = [line]
        i += 1
        while i < len(lines) and lines[i].strip():
            para_lines.append(lines[i])
            i += 1

        block_text = '\n'.join(para_lines)
        yield ('block', block_text, {})


def process_block(doc, text):
    """Process a text block: split into body paragraphs, lists, etc."""
    lines = text.splitlines()
    buf = []

    def flush_buffer():
        if not buf:
            return
        combined = ' '.join(buf)
        add_body_paragraph(doc, combined)
        buf.clear()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush_buffer()
            continue

        # Bullet list item
        if re.match(r'^[-–•]\s+', stripped):
            flush_buffer()
            item_text = re.sub(r'^[-–•]\s+', '', stripped)
            add_bullet_paragraph(doc, item_text)
            continue

        # Numbered list item (e.g., "1) text" or "2. text")
        if re.match(r'^\d+[).]\s+', stripped):
            flush_buffer()
            item_text = re.sub(r'^\d+[).]\s+', '', stripped)
            add_number_paragraph(doc, item_text)
            continue

        # Sub-bullet with indent (spaces/tabs before dash)
        m = re.match(r'^(\s+)[-–•]\s+(.*)$', line)
        if m:
            flush_buffer()
            add_bullet_paragraph(doc, m.group(2), level=1)
            continue

        # Bold inline header within paragraph (e.g., "**text**")
        if re.match(r'^\*\*.*\*\*$', stripped):
            flush_buffer()
            add_body_paragraph(doc, stripped.replace('**', ''), bold=True, indent=False)
            continue

        # Regular text line
        buf.append(stripped)

    flush_buffer()


def add_table_from_markdown(doc, table_text):
    rows = [r.strip().strip('|') for r in table_text.split('\n') if r.strip()]
    if not rows:
        return
    # Filter separator rows
    data_rows = [r for r in rows if not re.match(r'^\s*[-:]+\s*(\|\s*[-:]+\s*)*$', r)]
    if not data_rows:
        return
    cells = [c.strip() for c in data_rows[0].split('|')]
    table = doc.add_table(rows=len(data_rows), cols=len(cells))
    table.style = 'Table Grid'
    for ri, row_text in enumerate(data_rows):
        cells_text = [c.strip() for c in row_text.split('|')]
        for ci, cell_text in enumerate(cells_text):
            if ci < len(cells):
                table.rows[ri].cells[ci].text = cell_text
                # Format cell text
                for paragraph in table.rows[ri].cells[ci].paragraphs:
                    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
                    for run in paragraph.runs:
                        set_run_font(run, size=11)
    # Spacing after table
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(6)


def build_docx():
    print("Reading markdown...")
    with open(MD_PATH, 'r', encoding='utf-8') as f:
        md = f.read()

    doc = Document()
    setup_styles(doc)
    set_page_size(doc)

    print("Building DOCX with proper formatting...")
    for block_type, content, meta in parse_markdown(md):
        if block_type == 'heading':
            level = meta['level']
            if level > 3:
                level = 3
            p = doc.add_heading(content, level=level)
            for run in p.runs:
                if level == 1:
                    set_run_font(run, bold=True, size=14)
                elif level == 2:
                    set_run_font(run, bold=True, size=14)
                else:
                    set_run_font(run, bold=True, size=14)

        elif block_type == 'block':
            process_block(doc, content)

        elif block_type == 'code':
            add_code_block(doc, content)

        elif block_type == 'fragment_label':
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(content)
            set_run_font(run, italic=True, size=12)
            p.paragraph_format.space_before = Pt(6)
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.first_line_indent = Cm(0)

        elif block_type == 'figure':
            found = False
            for prefix, png in FIGURE_MAP.items():
                if content.startswith(prefix):
                    add_image(doc, png, content)
                    found = True
                    break
            if not found:
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = p.add_run(f"[Место для {content} — скриншот требуется]")
                set_run_font(run, italic=True, size=12, color=RGBColor(0x7F, 0x8C, 0x8D))

        elif block_type == 'table':
            add_table_from_markdown(doc, content)

    doc.save(OUT_PATH)
    print(f"Saved: {OUT_PATH}")


if __name__ == '__main__':
    build_docx()
