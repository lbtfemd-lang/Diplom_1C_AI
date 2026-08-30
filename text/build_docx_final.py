"""
Build DOCX from markdown matching ГОСТ diploma format (friend's example):
- Custom styles: Заг1 (H1, outline 0), Заг2 (H2, outline 1), Ааа (body), Перечисление (list)
- TNR 14pt, 1.5 line, justified, firstLine=709 twips (1.25cm) everywhere
- Headings: justified + firstLine indent + 14pt bold + no extra spacing
- Page break before each chapter (H1)
- Word native TOC field (autoupdate via F9)
- Code: 12pt single spacing, no indent
- Black text color (no dark blue)
"""
import os
import re
from docx import Document
from docx.shared import Inches, Pt, Cm, RGBColor, Twips
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from lxml import etree

BASE = os.path.dirname(os.path.abspath(__file__))
MD_PATH = os.path.join(BASE, "Диплом_ИИ_ассистент_1С_полный_рерайт.md")
FIGURES_DIR = os.path.join(BASE, "figures")
OUT_PATH = os.path.join(BASE, "Диплом_ИИ_ассистент_1С_окончательный.docx")

PAGE_WIDTH_CM = 21.0
PAGE_HEIGHT_CM = 29.7
LEFT_CM = 3.0
RIGHT_CM = 1.5
TOP_CM = 2.0
BOTTOM_CM = 2.0

FIGURE_MAP = {
    "Рисунок 1.1": "fig_1_1.png",
    "Рисунок 1.2": "fig_1_2.png",
    "Рисунок 1.3": "fig_1_3.png",
    "Рисунок 1.4": "fig_1_4.png",
    "Рисунок 2.1": "fig_2_1.png",
    "Рисунок 2.2": "fig_2_2.png",
    "Рисунок 2.3": "fig_2_3.png",
    "Рисунок 2.4": "fig_2_4.png",
    "Рисунок 2.5": "fig_2_5.png",
    "Рисунок 2.6": "fig_2_6.png",
    "Рисунок 2.7": "fig_2_7.png",
    "Рисунок 3.1": "fig_3_1.png",
    "Рисунок 3.2": "fig_3_2.png",
    "Рисунок 3.3": "fig_3_3.png",
    "Рисунок 4.1": "fig_4_1.png",
}

FIRST_LINE_TWIPS = 709


def _add_or_update_style(doc, name, base_style_id, para_props=None, run_props=None):
    try:
        style = doc.styles[name]
    except KeyError:
        style = doc.styles.add_style(name, 1)
    style.base_style = doc.styles[base_style_id]
    style.hidden = False
    style.priority = 2
    style.unhide_when_used = True

    pPr = style.element.find(qn('w:pPr'))
    if pPr is None:
        pPr = OxmlElement('w:pPr')
        style.element.append(pPr)
    for child in list(pPr):
        pPr.remove(child)
    if para_props:
        for tag, attrs in para_props:
            el = OxmlElement(tag)
            for k, v in attrs.items():
                el.set(qn(k), v)
            pPr.append(el)

    rPr = style.element.find(qn('w:rPr'))
    if rPr is None:
        rPr = OxmlElement('w:rPr')
        style.element.append(rPr)
    for child in list(rPr):
        rPr.remove(child)
    if run_props:
        for tag, attrs in run_props.items():
            el = OxmlElement(tag)
            for k, v in attrs.items():
                el.set(qn(k), v)
            rPr.append(el)

    return style


def setup_styles(doc):
    # The template already has Normal, Заг1, Заг2, Ааа, Перечисление, Фото, Таблица.
    # We only need to check if 'Код' is missing, and if so, add it.
    if 'Код' not in doc.styles:
        _add_or_update_style(doc, "Код", "Normal",
            para_props=[
                ('w:spacing', {'w:line': '240', 'w:lineRule': 'auto',
                               'w:before': '0', 'w:after': '0'}),
                ('w:ind', {'w:firstLine': '0'}),
                ('w:jc', {'w:val': 'left'}),
            ],
            run_props={'w:sz': {'w:val': '20'}})


def set_page_size(doc):
    sec = doc.sections[0]
    sec.page_width = Cm(PAGE_WIDTH_CM)
    sec.page_height = Cm(PAGE_HEIGHT_CM)
    sec.left_margin = Cm(LEFT_CM)
    sec.right_margin = Cm(RIGHT_CM)
    sec.top_margin = Cm(TOP_CM)
    sec.bottom_margin = Cm(BOTTOM_CM)


def add_image(doc, png_name, caption_text):
    path = os.path.join(FIGURES_DIR, png_name)
    p = doc.add_paragraph(style='Фото')
    p.paragraph_format.first_line_indent = Cm(0)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if not os.path.exists(path):
        run = p.add_run(f"[Место для {png_name}]")
        run.font.italic = True
        run.font.size = Pt(12)
        return
    run = p.add_run()
    max_w = Inches((PAGE_WIDTH_CM - LEFT_CM - RIGHT_CM) / 2.54)
    run.add_picture(path, width=max_w)
    
    # Let figure caption inherit alignment (justified) and first line indent (1.25 cm) from style 'Ааа'
    cap = doc.add_paragraph(style='Ааа')
    formatted_caption = caption_text.replace(' - ', ' – ').replace(' — ', ' – ')
    r = cap.add_run(formatted_caption)
    r.font.name = "Times New Roman"
    r.font.size = Pt(14)
    r._element.rPr.rFonts.set(qn('w:eastAsia'), 'Times New Roman')
    
    # 1 empty spacer paragraph of style 'Ааа' after caption
    spacer = doc.add_paragraph(style='Ааа')
    spacer.paragraph_format.first_line_indent = Cm(0)



def add_styled_runs(paragraph, text, default_font_size=Pt(14), default_bold=False):
    parts = text.split('**')
    is_bold = default_bold
    for part in parts:
        if not part:
            is_bold = not is_bold
            continue
        run = paragraph.add_run(part)
        run.font.name = "Times New Roman"
        run.font.size = default_font_size
        run.font.bold = is_bold
        run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Times New Roman')
        is_bold = not is_bold


def add_body_para(doc, text, bold=False):
    p = doc.add_paragraph(style='Ааа')
    add_styled_runs(p, text.strip(), default_font_size=Pt(14), default_bold=bold)
    return p


def add_list_item(doc, text, numbered=False, num_text="", level=0):
    if numbered:
        p = doc.add_paragraph(style='Ааа')
        p.paragraph_format.first_line_indent = Cm(1.25)
        if level > 0:
            p.paragraph_format.left_indent = Cm(1.25 + level * 0.63)
        run_num = p.add_run(num_text + " ")
        run_num.font.name = "Times New Roman"
        run_num.font.size = Pt(14)
        add_styled_runs(p, text.strip(), default_font_size=Pt(14))
    else:
        p = doc.add_paragraph(style='Перечисление')
        if level > 0:
            p.paragraph_format.left_indent = Cm(level * 0.63)
        add_styled_runs(p, text.strip(), default_font_size=Pt(14))
    return p


def add_heading(doc, text, level):
    style_name = "Заг2"
    p = doc.add_paragraph(style=style_name)
    clean_text = text.replace('**', '').strip()
    if level == 1:
        clean_text = clean_text.upper()
    run = p.add_run(clean_text)
    run.font.name = "Times New Roman"
    run.font.size = Pt(14)
    run.font.bold = True
    run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Times New Roman')
    if level == 1:
        _add_page_break_before(p)
    return p


def _add_page_break_before(paragraph):
    pPr = paragraph._element.get_or_add_pPr()
    existing = pPr.find(qn('w:pageBreakBefore'))
    if existing is None:
        el = OxmlElement('w:pageBreakBefore')
        pPr.insert(0, el)


def add_native_toc(doc):
    p = doc.add_paragraph(style='Ааа')
    p.paragraph_format.first_line_indent = Cm(0)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("СОДЕРЖАНИЕ")
    run.font.name = "Times New Roman"
    run.font.size = Pt(14)
    run.font.bold = True
    run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Times New Roman')

    p2 = doc.add_paragraph(style='Ааа')
    p2.paragraph_format.first_line_indent = Cm(0)

    run1 = p2.add_run()
    fldChar1 = OxmlElement('w:fldChar')
    fldChar1.set(qn('w:fldCharType'), 'begin')
    run1._element.append(fldChar1)

    run2 = p2.add_run()
    instrText = OxmlElement('w:instrText')
    instrText.set(qn('xml:space'), 'preserve')
    instrText.text = ' TOC \\o "1-2" \\h \\z \\u '
    run2._element.append(instrText)

    run3 = p2.add_run()
    fldChar2 = OxmlElement('w:fldChar')
    fldChar2.set(qn('w:fldCharType'), 'separate')
    run3._element.append(fldChar2)

    run4 = p2.add_run("Обновите это поле: нажмите Ctrl+A, затем F9")
    run4.font.name = "Times New Roman"
    run4.font.size = Pt(14)
    run4.font.color.rgb = RGBColor(0x80, 0x80, 0x80)

    run5 = p2.add_run()
    fldChar3 = OxmlElement('w:fldChar')
    fldChar3.set(qn('w:fldCharType'), 'end')
    run5._element.append(fldChar3)

    _add_page_break_before(p2)
    p2_next = doc.add_paragraph(style='Ааа')
    p2_next.paragraph_format.first_line_indent = Cm(0)


def add_code_block(doc, code_text):
    for line in code_text.splitlines():
        p = doc.add_paragraph(style='Код')
        run = p.add_run(line)
        run.font.name = "Times New Roman"
        run.font.size = Pt(12)
        run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Times New Roman')


def add_table_caption(doc, text):
    style_name = 'Normal (Web)' if text.strip().startswith('Таблица 4.') else 'Ааа'
    if style_name not in doc.styles:
        style_name = 'Ааа'
    
    # 1 empty spacer paragraph before table caption if not a continuation
    if not text.strip().startswith('Продолжение'):
        spacer = doc.add_paragraph(style=style_name)
        spacer.paragraph_format.first_line_indent = Cm(0)
    
    # Let table caption inherit alignment (justified) and first line indent (1.25 cm) from style 'Ааа'
    p = doc.add_paragraph(style=style_name)
    formatted_text = text.strip().replace(' - ', ' – ').replace(' — ', ' – ')
    add_styled_runs(p, formatted_text, default_font_size=Pt(14))


def classify_heading(text):
    text = text.strip()
    if text == 'СОДЕРЖАНИЕ':
        return 'toc_marker'
    if re.match(r'^ВВЕДЕНИЕ$', text):
        return 'h1'
    if re.match(r'^ЗАКЛЮЧЕНИЕ$', text):
        return 'h1'
    if re.match(r'^СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ$', text):
        return 'h1'
    if re.match(r'^ПРИЛОЖЕНИЯ$', text):
        return 'h1'
    if re.match(r'^\d\s+[А-ЯЁ]', text) and text.isupper():
        return 'h1'
    if re.match(r'^\d+\.\d+\s+', text):
        return 'h2'
    if re.match(r'^[А-ЯЁ]\.\d+\s+', text):
        return 'app_sub'
    if re.match(r'^\*\*.*\*\*$', text):
        return 'bold_sub'
    return None


def parse_markdown(md_text):
    lines = md_text.splitlines()
    i = 0
    in_toc = False
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        if re.match(r'^-{3,}$', stripped):
            i += 1
            continue

        if stripped == '<!-- pagebreak -->' or stripped == '<pagebreak>':
            yield ('pagebreak', '', {})
            i += 1
            continue

        if stripped == 'СОДЕРЖАНИЕ':
            in_toc = True
            yield ('toc_start', 'СОДЕРЖАНИЕ', {})
            i += 1
            continue

        if in_toc:
            if not stripped:
                i += 1
                continue
            toc_m = re.match(r'^(.+?)\t(\d+)$', stripped)
            if toc_m:
                i += 1
                continue
            else:
                in_toc = False

        heading_type = classify_heading(stripped)
        if heading_type == 'toc_marker':
            yield ('toc_marker', stripped, {})
            i += 1
            continue
        if heading_type == 'h1':
            yield ('heading', stripped, {'level': 1})
            i += 1
            continue
        if heading_type == 'h2':
            yield ('heading', stripped, {'level': 2})
            i += 1
            continue
        if heading_type == 'bold_sub':
            yield ('bold_sub', stripped.replace('**', ''), {})
            i += 1
            continue
        if heading_type == 'app_sub':
            yield ('app_sub', stripped, {})
            i += 1
            continue

        if re.match(r'^#{1,3}\s+', stripped):
            m = re.match(r'^(#{1,3})\s+(.*)$', stripped)
            yield ('heading', m.group(2), {'level': min(len(m.group(1)), 2)})
            i += 1
            continue

        fig_m = re.match(r'^(Рисунок\s+\d+\.\d+.*)$', stripped)
        if fig_m:
            yield ('figure', fig_m.group(1), {})
            i += 1
            continue

        frag_m = re.match(r'^(Фрагмент:\s+.*)$', stripped)
        if frag_m:
            yield ('fragment_label', frag_m.group(1), {})
            i += 1
            continue

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

        if stripped.startswith('|') and '|' in stripped[1:]:
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_lines.append(lines[i].strip())
                i += 1
            yield ('table', '\n'.join(table_lines), {})
            continue

        para_lines = [line]
        i += 1
        while i < len(lines) and lines[i].strip():
            nxt = lines[i].strip()
            if classify_heading(nxt):
                break
            if nxt.startswith('|') and '|' in nxt[1:]:
                break
            if nxt.startswith('```'):
                break
            if re.match(r'^Рисунок\s+\d+\.\d+', nxt):
                break
            para_lines.append(lines[i])
            i += 1

        yield ('block', '\n'.join(para_lines), {})


def process_block(doc, text, in_sources=False):
    lines = text.splitlines()
    buf = []

    def flush():
        if not buf:
            return
        add_body_para(doc, ' '.join(buf))
        buf.clear()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush()
            continue

        if in_sources:
            flush()
            add_body_para(doc, stripped)
            continue

        if not in_sources:
            # 1. Indented bullet lists (e.g. nested lists with level=1)
            m_indent_bullet = re.match(r'^(\s+)[-–•]\s+(.*)$', line)
            if m_indent_bullet:
                flush()
                add_list_item(doc, m_indent_bullet.group(2), level=1)
                continue

            # 2. Indented numbered lists (converted to bullet items with level=1)
            m_indent_number = re.match(r'^(\s+)\d+[).]\s+(.*)$', line)
            if m_indent_number:
                flush()
                add_list_item(doc, m_indent_number.group(2), level=1)
                continue

            # 3. Top-level bullet lists (level=0)
            m_bullet = re.match(r'^[-–•]\s+(.*)$', stripped)
            if m_bullet:
                flush()
                add_list_item(doc, m_bullet.group(1), level=0)
                continue

            # 4. Top-level numbered lists (converted to bullet items with level=0)
            m_number = re.match(r'^\d+[).]\s+(.*)$', stripped)
            if m_number:
                flush()
                add_list_item(doc, m_number.group(1), level=0)
                continue


        buf.append(stripped)

    flush()


def add_table_from_markdown(doc, table_text):
    rows = [r.strip().strip('|') for r in table_text.split('\n') if r.strip()]
    if not rows:
        return
    data_rows = [r for r in rows
                 if not re.match(r'^\s*[-:]+\s*(\|\s*[-:]+\s*)*$', r)]
    if not data_rows:
        return
    cells = [c.strip() for c in data_rows[0].split('|')]
    table = doc.add_table(rows=len(data_rows), cols=len(cells))
    table.style = 'Normal Table'
    
    # Apply standard GOST thin borders (single size 4) like template
    tblPr = table._element.tblPr
    tblBorders = OxmlElement('w:tblBorders')
    for side in ['top', 'left', 'bottom', 'right', 'insideH', 'insideV']:
        b = OxmlElement(f'w:{side}')
        b.set(qn('w:val'), 'single')
        b.set(qn('w:sz'), '4')
        b.set(qn('w:space'), '0')
        b.set(qn('w:color'), 'auto')
        tblBorders.append(b)
    tblPr.append(tblBorders)

    is_col_numbers = False
    if data_rows:
        first_row_cells = [c.strip() for c in data_rows[0].split('|')]
        if all(re.match(r'^\d+$', cell) for cell in first_row_cells if cell):
            is_col_numbers = True

    for ri, row_text in enumerate(data_rows):
        cells_text = [c.strip() for c in row_text.split('|')]
        for ci, cell_text in enumerate(cells_text):
            if ci < len(cells):
                cell = table.rows[ri].cells[ci]
                cell.text = ""
                p = cell.paragraphs[0]
                p.style = doc.styles['Таблица']
                p.paragraph_format.first_line_indent = Cm(0)
                p.paragraph_format.space_before = Pt(0)
                p.paragraph_format.space_after = Pt(0)
                p.paragraph_format.line_spacing = 1.0
                if ri == 0 or len(cell_text) <= 3:
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                else:
                    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                is_bold = (ri == 0) and not is_col_numbers
                add_styled_runs(p, cell_text, default_font_size=Pt(12), default_bold=is_bold)



def build_docx():
    import sys
    sys.stdout.reconfigure(encoding='utf-8')

    print("Reading markdown...")
    with open(MD_PATH, 'r', encoding='utf-8') as f:
        md = f.read()
    
    # Remove control characters that are invalid in XML (like form-feed or vertical tabs)
    md = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', md)

    template_path = os.path.join(os.path.dirname(BASE), "ДИПЛОМ ФИНАЛ — копия.docx")
    print(f"Loading template from {template_path}...")
    doc = Document(template_path)
    
    print("Clearing template body...")
    for p in list(doc.paragraphs):
        p._element.getparent().remove(p._element)
    for t in list(doc.tables):
        t._element.getparent().remove(t._element)

    setup_styles(doc)

    toc_inserted = False

    print("Building DOCX...")
    blocks = list(parse_markdown(md))
    
    # Post-process blocks to identify table captions
    for idx in range(len(blocks)):
        if blocks[idx][0] == 'table':
            if idx > 0 and blocks[idx-1][0] == 'block':
                text_content = blocks[idx-1][1].strip()
                if text_content.startswith('Таблица') or text_content.startswith('Продолжение таблицы'):
                    blocks[idx-1] = ('table_caption', text_content, blocks[idx-1][2])

    in_sources = False
    for idx, (block_type, content, meta) in enumerate(blocks):
        trimmed_content = content.strip()
        if trimmed_content.startswith('Приложение') or trimmed_content.startswith('ПРИЛОЖЕНИЯ'):
            in_sources = False

        next_block = blocks[idx+1] if idx + 1 < len(blocks) else None
        prev_block = blocks[idx-1] if idx - 1 >= 0 else None

        if block_type == 'toc_start':
            if not toc_inserted:
                add_native_toc(doc)
                toc_inserted = True

        elif block_type == 'toc_marker':
            if not toc_inserted:
                add_native_toc(doc)
                toc_inserted = True

        elif block_type == 'pagebreak':
            p = doc.add_paragraph()
            _add_page_break_before(p)

        elif block_type == 'heading':
            level = meta['level']
            if content.strip() == 'СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ':
                in_sources = True
            else:
                in_sources = False
            
            # Spacer BEFORE H2 heading (if preceded by body block, code, list, etc.)
            if level == 2 and prev_block and prev_block[0] != 'heading':
                sp = doc.add_paragraph(style='Заг2')
                sp.paragraph_format.first_line_indent = Cm(0)
                
            add_heading(doc, content, level)
            
            # Spacer AFTER heading (if not immediately followed by another heading)
            if next_block and next_block[0] == 'heading':
                pass
            else:
                sp = doc.add_paragraph(style='Заг2')
                sp.paragraph_format.first_line_indent = Cm(0)

        elif block_type == 'bold_sub':
            in_sources = False
            add_body_para(doc, content, bold=True)

        elif block_type == 'app_sub':
            in_sources = False
            add_body_para(doc, content, bold=True)

        elif block_type == 'table_caption':
            add_table_caption(doc, content)

        elif block_type == 'block':
            process_block(doc, content, in_sources=in_sources)

        elif block_type == 'code':
            add_code_block(doc, content)

        elif block_type == 'fragment_label':
            p = doc.add_paragraph(style='Ааа')
            p.paragraph_format.first_line_indent = Cm(0)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run(content)
            r.font.name = "Times New Roman"
            r.font.size = Pt(12)
            r.font.italic = True
            r._element.rPr.rFonts.set(qn('w:eastAsia'), 'Times New Roman')

        elif block_type == 'figure':
            found = False
            for prefix, png in FIGURE_MAP.items():
                if content.startswith(prefix):
                    add_image(doc, png, content)
                    found = True
                    break
            if not found:
                p = doc.add_paragraph(style='Ааа')
                p.paragraph_format.first_line_indent = Cm(0)
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                r = p.add_run(f"[Место для {content}]")
                r.font.italic = True
                r.font.size = Pt(12)

        elif block_type == 'table':
            add_table_from_markdown(doc, content)
            
            # Check if next block is a continuation caption
            is_continuation = False
            if next_block and next_block[0] == 'table_caption':
                if next_block[1].strip().startswith('Продолжение'):
                    is_continuation = True
            
            if not is_continuation:
                last_p = doc.paragraphs[-1] if doc.paragraphs else None
                style_name = 'Ааа'
                if last_p and last_p.style.name == 'Normal (Web)':
                    style_name = 'Normal (Web)'
                spacer = doc.add_paragraph(style=style_name)
                spacer.paragraph_format.first_line_indent = Cm(0)

    save_path = OUT_PATH
    try:
        doc.save(save_path)
        print(f"Saved: {save_path}")
    except PermissionError:
        save_path = save_path.replace('.docx', '_v2.docx')
        doc.save(save_path)
        print(f"Original locked, saved as: {save_path}")

    import shutil
    release_path = os.path.join(
        os.path.dirname(BASE), "release", "text",
        "Диплом_ИИ_ассистент_1С_окончательный.docx"
    )
    desktop_path = r"C:\Users\kobza\Desktop\Диплом_ИИ_ассистент_1С_окончательный.docx"
    
    # Try copying to release
    try:
        shutil.copy2(save_path, release_path)
        print("Copied to release")
    except PermissionError:
        v2 = release_path.replace('.docx', '_v2.docx')
        shutil.copy2(save_path, v2)
        print(f"Original locked, saved as _v2.docx")
        
    # Try copying to Desktop
    try:
        shutil.copy2(save_path, desktop_path)
        print(f"Copied to Desktop: {desktop_path}")
    except PermissionError:
        desktop_v2 = desktop_path.replace('.docx', '_v2.docx')
        shutil.copy2(save_path, desktop_v2)
        print(f"Desktop locked, saved as {desktop_v2}")


if __name__ == '__main__':
    build_docx()
