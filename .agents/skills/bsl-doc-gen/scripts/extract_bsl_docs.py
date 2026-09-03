#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_bsl_docs.py — Автоматическое извлечение описания процедур и функций из BSL-модулей 1С.
Базируется на алгоритмах AST/синтаксического парсинга bsl-parser / yard.
"""

import sys
import re
from pathlib import Path

# Гарантия корректной кодировки UTF-8 в Windows консоли
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

def parse_bsl_file(file_path):
    methods = []
    current_comments = []
    current_directive = ""
    
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            stripped = line.strip()
            
            # Директива компиляции
            if stripped.startswith("&"):
                current_directive = stripped
                continue
                
            # Комментарии
            if stripped.startswith("//"):
                current_comments.append(stripped[2:].strip())
                continue
                
            # Сигнатура метода
            m = re.match(r'^(Процедура|Функция)\s+([A-Za-zА-Яа-я0-9_]+)\s*\((.*?)\)(\s+Экспорт)?', stripped, re.IGNORECASE)
            if m:
                m_type = m.group(1)
                m_name = m.group(2)
                m_params = m.group(3).strip()
                m_export = bool(m.group(4))
                
                doc_desc = " ".join(current_comments) if current_comments else "Описание отсутствует"
                methods.append({
                    "name": m_name,
                    "type": m_type,
                    "directive": current_directive or "&НаСервере",
                    "params": m_params,
                    "export": m_export,
                    "doc": doc_desc
                })
                current_comments = []
                current_directive = ""
            else:
                if not stripped:
                    current_comments = []
                    
    return methods

def format_markdown(methods, filename):
    out = []
    out.append(f"# Спецификация модуля: `{filename}`\n")
    out.append(f"Всего обнаружено методов: {len(methods)} (Экспортных: {sum(1 for m in methods if m['export'])})\n")
    out.append("| Метод | Тип | Директива | Экспорт | Параметры | Назначение |")
    out.append("|---|---|---|---|---|---|")
    for m in methods:
        exp_str = "Да" if m['export'] else "Нет"
        params_str = f"`{m['params']}`" if m['params'] else "—"
        doc_str = m['doc'].replace("|", "/")
        out.append(f"| `{m['name']}` | {m['type']} | `{m['directive']}` | {exp_str} | {params_str} | {doc_str} |")
    return "\n".join(out)

def main():
    if len(sys.argv) < 2:
        target = Path("1c_extensions/1C_Shared_HTTP.bsl")
    else:
        target = Path(sys.argv[1])
        
    files = []
    if target.is_file():
        files.append(target)
    elif target.is_dir():
        files.extend(sorted(target.glob("*.bsl")))
        
    for f in files:
        methods = parse_bsl_file(f)
        md = format_markdown(methods, f.name)
        print(md)
        print("\n" + "="*80 + "\n")

if __name__ == "__main__":
    main()
