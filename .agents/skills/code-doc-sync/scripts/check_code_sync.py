#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_code_sync.py — Сверка программного кода с текстом диплома.
Сканирует:
1. 1c_extensions/*.bsl (экспортные процедуры и функции, актуальность версий)
2. Middleware/app/ (FastAPI эндпоинты)
3. text/*.md (поиск устаревших ссылок и отсутствующих описаний)
"""

import sys
import os
import re
from pathlib import Path

# Гарантия корректной кодировки UTF-8 в Windows консоли
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parents[4] # D:\Share\Projects\diplom
EXT_DIR = ROOT / "1c_extensions"
MID_DIR = ROOT / "Middleware"
TEXT_DIR = ROOT / "text"

def extract_bsl_exports(bsl_file):
    exports = []
    if not bsl_file.exists():
        return exports
    with open(bsl_file, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = re.match(r'^(?:Функция|Процедура)\s+([A-Za-zА-Яа-я0-9_]+)\s*\(.*Экспорт', line.strip(), re.IGNORECASE)
            if m:
                exports.append(m.group(1))
    return exports

def extract_fastapi_endpoints():
    endpoints = []
    for py_file in MID_DIR.glob("**/*.py"):
        if ".venv" in str(py_file) or "tests" in str(py_file):
            continue
        with open(py_file, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                m = re.search(r'@(?:router|app)\.(get|post|put|delete|patch)\(["\']([^"\']+)["\']', line)
                if m:
                    endpoints.append((m.group(1).upper(), m.group(2)))
    return list(set(endpoints))

def audit_text_sync():
    print("=== Запуск сверки исходного кода с текстом диплома ===")
    
    # 1. Проверка актуальности версии BSL файла в тексте
    v6_file = EXT_DIR / "1C_Full_Code_v6.bsl"
    print(f"1. Проверка BSL исходников: {v6_file.name} (размер {v6_file.stat().st_size if v6_file.exists() else 0} байт)")
    
    obsolete_v5_refs = []
    for md in TEXT_DIR.glob("*.md"):
        with open(md, "r", encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                if "1C_Full_Code_v5.bsl" in line:
                    obsolete_v5_refs.append((md.name, i, line.strip()))
                    
    if obsolete_v5_refs:
        print(f"\n[!] Обнаружены устаревшие ссылки на '1C_Full_Code_v5.bsl':")
        for f_name, l_no, text in obsolete_v5_refs:
            print(f"  - {f_name}:{l_no} -> {text[:80]}")
    else:
        print("[OK] Ссылок на устаревшую версию v5 не обнаружено.")

    # 2. Проверка эндпоинтов
    endpoints = extract_fastapi_endpoints()
    print(f"\n2. Обнаружено FastAPI эндпоинтов в коде: {len(endpoints)}")
    for method, path in sorted(endpoints):
        print(f"  - {method:6s} {path}")
        
    # 3. Проверка упоминания ключевых эндпоинтов в тексте диплома
    ch3 = TEXT_DIR / "03_Глава3_Реализация_рерайт.md"
    if ch3.exists():
        ch3_text = ch3.read_text(encoding="utf-8")
        print(f"\n3. Сверка эндпоинтов с текстом {ch3.name}:")
        for method, path in sorted(endpoints):
            if path in ch3_text:
                print(f"  [+] {path} описан в Главе 3")
            else:
                print(f"  [-] {path} не упомянут явно в тексте Главы 3")

    # 4. Проверка ключевых экспортных процедур 1С
    bsl_exports = extract_bsl_exports(v6_file)
    print(f"\n4. Экспортных методов в {v6_file.name}: {len(bsl_exports)}")
    if bsl_exports:
        for exp in bsl_exports[:10]:
            print(f"  - {exp}")
        if len(bsl_exports) > 10:
            print(f"  ... и еще {len(bsl_exports)-10} методов.")

if __name__ == "__main__":
    audit_text_sync()
