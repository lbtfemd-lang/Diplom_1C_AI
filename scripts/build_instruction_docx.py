"""Build official DOCX from ИНСТРУКЦИЯ_ПО_РАЗВЕРТЫВАНИЮ_И_ДЕМОНСТРАЦИИ.md"""
import os
import re
import docx
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls

def build_instruction_docx():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    md_path = os.path.join(root, "docs", "contest", "ИНСТРУКЦИЯ_ПО_РАЗВЕРТЫВАНИЮ_И_ДЕМОНСТРАЦИИ.md")
    out_path = os.path.join(root, "dist", "ИНСТРУКЦИЯ_ПО_РАЗВЕРТЫВАНИЮ_И_ДЕМОНСТРАЦИИ.docx")

    with open(md_path, "r", encoding="utf-8") as f:
        text = f.read()

    doc = docx.Document()

    # Page setup (A4 standard)
    section = doc.sections[0]
    section.top_margin = Inches(0.79)
    section.bottom_margin = Inches(0.79)
    section.left_margin = Inches(1.18)
    section.right_margin = Inches(0.59)

    # Base style
    style = doc.styles["Normal"]
    font = style.font
    font.name = "Times New Roman"
    font.size = Pt(12)
    font.color.rgb = RGBColor(0, 0, 0)
    style.paragraph_format.line_spacing = 1.15
    style.paragraph_format.space_after = Pt(4)

    def set_cell_border(cell):
        tcPr = cell._tc.get_or_add_tcPr()
        tcBorders = parse_xml(
            f'<w:tcBorders {nsdecls("w")}>\n'
            f'<w:top w:val="single" w:sz="4" w:space="0" w:color="CCCCCC"/>\n'
            f'<w:left w:val="single" w:sz="4" w:space="0" w:color="CCCCCC"/>\n'
            f'<w:bottom w:val="single" w:sz="4" w:space="0" w:color="CCCCCC"/>\n'
            f'<w:right w:val="single" w:sz="4" w:space="0" w:color="CCCCCC"/>\n'
            f'</w:tcBorders>'
        )
        tcPr.append(tcBorders)

    lines = text.splitlines()
    table_lines = []

    def flush_table(t_lines):
        if not t_lines:
            return
        rows_data = []
        for l in t_lines:
            if "|" in l and not re.match(r"^\s*\|?[-:\s|]+\|?\s*$", l):
                cells = [c.strip() for c in l.split("|")[1:-1]]
                if cells:
                    rows_data.append(cells)
        if not rows_data:
            return
        num_cols = max(len(r) for r in rows_data)
        table = doc.add_table(rows=len(rows_data), cols=num_cols)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        for r_idx, row in enumerate(rows_data):
            for c_idx, val in enumerate(row):
                if c_idx < num_cols:
                    cell = table.cell(r_idx, c_idx)
                    set_cell_border(cell)
                    clean_val = re.sub(r"\*\*(.*?)\*\*", r"\1", val)
                    clean_val = re.sub(r"`(.*?)`", r"\1", clean_val)
                    p = cell.paragraphs[0]
                    p.text = clean_val
                    p.style.font.name = "Times New Roman"
                    p.style.font.size = Pt(10)
                    if r_idx == 0:
                        shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="EBEBEB"/>')
                        cell._tc.get_or_add_tcPr().append(shading)
                        p.runs[0].bold = True
        doc.add_paragraph().paragraph_format.space_after = Pt(6)

    i = 0
    while i < len(lines):
        line = lines[i]
        strip_l = line.strip()

        if strip_l.startswith("|"):
            table_lines.append(strip_l)
            i += 1
            continue
        else:
            if table_lines:
                flush_table(table_lines)
                table_lines = []

        if not strip_l or strip_l == "---":
            i += 1
            continue

        if strip_l.startswith("# "):
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(strip_l[2:].strip())
            run.bold = True
            run.font.size = Pt(16)
            p.paragraph_format.space_after = Pt(12)
        elif strip_l.startswith("## "):
            p = doc.add_paragraph()
            run = p.add_run(strip_l[3:].strip())
            run.bold = True
            run.font.size = Pt(14)
            p.paragraph_format.space_before = Pt(12)
            p.paragraph_format.space_after = Pt(6)
        elif strip_l.startswith("### "):
            p = doc.add_paragraph()
            run = p.add_run(strip_l[4:].strip())
            run.bold = True
            run.font.size = Pt(12.5)
            p.paragraph_format.space_before = Pt(8)
            p.paragraph_format.space_after = Pt(4)
        elif re.match(r"^\d+\.\s", strip_l):
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.25)
            clean = re.sub(r"\*\*(.*?)\*\*", r"\1", strip_l)
            clean = re.sub(r"`(.*?)`", r"\1", clean)
            p.add_run(clean)
        elif strip_l.startswith("* "):
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.25)
            clean = re.sub(r"\*\*(.*?)\*\*", r"\1", strip_l[2:])
            clean = re.sub(r"`(.*?)`", r"\1", clean)
            p.add_run("• " + clean)
        else:
            p = doc.add_paragraph()
            clean = re.sub(r"\*\*(.*?)\*\*", r"\1", strip_l)
            clean = re.sub(r"`(.*?)`", r"\1", clean)
            p.add_run(clean)
        i += 1

    if table_lines:
        flush_table(table_lines)

    doc.save(out_path)
    print(f"Generated DOCX: {out_path} ({os.path.getsize(out_path)} bytes)")

if __name__ == "__main__":
    build_instruction_docx()
