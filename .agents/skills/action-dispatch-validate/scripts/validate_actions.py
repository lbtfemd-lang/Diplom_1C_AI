#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_actions.py — Тестирование и валидация схем действий диспетчера 1С и исправления поврежденного JSON.
Базируется на принципах instructor / json-repair.
"""

import sys
import json
import re

# Гарантия корректной кодировки UTF-8 в Windows консоли
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

VALID_ACTIONS = {"open_form", "create_document", "open_report", "create_task", "query_balance"}

def repair_json_string(malformed_json_str):
    """
    Упрощенный алгоритм восстановления поврежденного JSON от LLM (концепция json-repair).
    """
    cleaned = malformed_json_str.strip()
    # Убираем markdown fences если они есть
    if cleaned.startswith("```"):
        cleaned = re.sub(r'^```(?:json)?\n?', '', cleaned)
        cleaned = re.sub(r'\n?```$', '', cleaned)
    cleaned = cleaned.strip()
    
    # Исправляем незакрытые фигурные или квадратные скобки
    open_braces = cleaned.count('{') - cleaned.count('}')
    if open_braces > 0:
        cleaned += '}' * open_braces
        
    open_brackets = cleaned.count('[') - cleaned.count(']')
    if open_brackets > 0:
        cleaned += ']' * open_brackets
        
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None

def validate_action_schema(action_obj):
    if not isinstance(action_obj, dict):
        return False, "Команда должна быть JSON-объектом (dict)"
        
    action_type = action_obj.get("action")
    if not action_type:
        return False, "Отсутствует обязательное поле 'action'"
        
    if action_type not in VALID_ACTIONS:
        return False, f"Неизвестный тип действия: '{action_type}'. Допустимые: {VALID_ACTIONS}"
        
    parameters = action_obj.get("parameters", {})
    if not isinstance(parameters, dict):
        return False, "Поле 'parameters' должно быть словарем"
        
    return True, f"Действие '{action_type}' валидно"

def main():
    print("=== Запуск валидатора команд диспетчера 1С ===")
    
    test_cases = [
        # 1. Валидный JSON
        '{"action": "open_form", "parameters": {"metadata_name": "Документ.ЗаказПокупателя"}}',
        # 2. Невалидный/оборванный JSON (симуляция обрыва ответа LLM)
        '{"action": "create_task", "parameters": {"title": "Подготовить отчет по продажам", "priority": "high"',
        # 3. JSON в markdown блоке
        '```json\n{"action": "query_balance", "parameters": {"nomenklatura": "Кабель силовый"}}\n```',
        # 4. Некорректный тип действия
        '{"action": "delete_database", "parameters": {}}'
    ]
    
    for i, raw_str in enumerate(test_cases, 1):
        print(f"\nТест-кейс #{i}:")
        print(f"  Входная строка: {repr(raw_str)}")
        
        parsed = repair_json_string(raw_str)
        if parsed is None:
            print("  [FAIL] Не удалось распарсить или восстановить JSON.")
            continue
            
        print(f"  Восстановленный JSON: {parsed}")
        valid, msg = validate_action_schema(parsed)
        if valid:
            print(f"  [SUCCESS] {msg}")
        else:
            print(f"  [ERROR] {msg}")

if __name__ == "__main__":
    main()
