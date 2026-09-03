#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_diploma.py — Скрипт автоматического аудита оформления глав диплома.
Проверяет:
1. Прямые кавычки ("" вместо «»)
2. Пунктуацию списков (маленькая буква в начале, ';' в конце кроме последнего с '.')
3. Ссылки на рисунки (должны быть в конце предложения)
4. Завершение разделов рисунком или таблицей
5. Наличие личных местоимений (я, мы, наш, мой)
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

def audit_markdown_file(file_path):
    violations = []
    
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    in_code_block = False
    list_items_buffer = [] # list of (line_num, text)
    
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        
        # Переключение режима блока кода
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
            
        # 1. Проверка прямых кавычек вне Markdown-ссылок
        clean_text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', stripped)
        clean_text = re.sub(r'`[^`]+`', '', clean_text)
        if '"' in clean_text:
            violations.append((i, "Кавычки", f"Обнаружены прямые кавычки '\"' вместо елочек «»: {stripped[:60]}..."))
            
        # 2. Проверка личных местоимений
        pronoun_match = re.search(r'\b(я|мы|наш|наша|наше|наши|нашего|нашей|наших|мой|моя|мое|мои|нами|мной)\b', clean_text, re.IGNORECASE)
        if pronoun_match:
            # Исключаем ложные срабатывания (например, если слово в составе термина)
            matched_word = pronoun_match.group(0)
            violations.append((i, "Академический стиль", f"Обнаружено личное местоимение '{matched_word}': {stripped[:60]}..."))

        # 3. Сбор элементов списков для проверки перечислений
        list_match = re.match(r'^[-*]\s+(.*)$', stripped)
        if list_match:
            list_items_buffer.append((i, list_match.group(1).strip()))
        else:
            if list_items_buffer:
                # Проверяем накопленный список
                total = len(list_items_buffer)
                for idx, (l_num, item_text) in enumerate(list_items_buffer):
                    # Проверка первой буквы
                    first_char = item_text[0] if item_text else ""
                    if first_char.isupper() and not item_text.startswith(('1С', 'HTTP', 'API', 'REST', 'JWT', 'LLM', 'RAG', 'JSON', 'SQL', 'Python', 'FastAPI')):
                        violations.append((l_num, "Список", f"Пункт списка начинается с заглавной буквы: {item_text[:40]}..."))
                    
                    # Проверка знака препинания в конце
                    is_last = (idx == total - 1)
                    if is_last:
                        if not item_text.endswith('.'):
                            violations.append((l_num, "Список", f"Последний пункт списка должен заканчиваться точкой (.): {item_text[-20:]}"))
                    else:
                        if not item_text.endswith(';'):
                            violations.append((l_num, "Список", f"Пункт списка должен заканчиваться точкой с запятой (;): {item_text[-20:]}"))
                list_items_buffer = []

        # 4. Проверка ссылок на рисунки
        # Если есть "(рисунок ...)" не в конце предложения
        fig_refs = re.finditer(r'\((?:рисунок|рисунке|рис\.)\s+\d+[\.\d]*\)', stripped, re.IGNORECASE)
        for m in fig_refs:
            end_pos = m.end()
            remainder = stripped[end_pos:].strip()
            if remainder and not remainder.startswith(('.', ';', ':', ',')):
                violations.append((i, "Ссылка на рисунок", f"Ссылка на рисунок должна быть в конце предложения: {stripped[:60]}..."))

    # 5. Проверка завершения файла/разделов рисунком или таблицей
    for j in range(len(lines) - 1, -1, -1):
        st = lines[j].strip()
        if not st:
            continue
        if st.startswith(('![', '|', 'Таблица', 'Рисунок')):
            violations.append((j + 1, "Завершение раздела", "Раздел заканчивается рисунком или таблицей, отсутствует завершающий текст."))
        break
        
    return violations

def main():
    if len(sys.argv) < 2:
        target_path = Path("text")
    else:
        target_path = Path(sys.argv[1])
        
    files_to_check = []
    if target_path.is_file():
        files_to_check.append(target_path)
    elif target_path.is_dir():
        files_to_check.extend(sorted(target_path.glob("*.md")))
        
    if not files_to_check:
        print(f"Не найдено файлов Markdown для проверки по пути: {target_path}")
        return
        
    total_violations = 0
    print(f"=== Запуск аудита текста диплома: {len(files_to_check)} файлов ===")
    
    for f in files_to_check:
        res = audit_markdown_file(f)
        if res:
            print(f"\n[!] Файл: {f.name} (Замечаний: {len(res)})")
            for line_no, cat, msg in res:
                print(f"  - Стр. {line_no:4d} | [{cat}] {msg}")
            total_violations += len(res)
        else:
            print(f"[OK] {f.name}: нарушений не обнаружено.")
            
    print(f"\nИтог: Проверено файлов: {len(files_to_check)}, Всего замечаний: {total_violations}")

if __name__ == "__main__":
    main()
