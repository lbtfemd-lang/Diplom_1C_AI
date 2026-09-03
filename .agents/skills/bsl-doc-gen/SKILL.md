---
name: bsl-doc-gen
description: Автоматическое извлечение документации, экспортных процедур, функций и параметров из BSL-модулей 1С в формат Markdown. Базируется на принципах bsl-parser и yard.
---

# /bsl-doc-gen — Автогенерация документации BSL

Навык выполняет синтаксический анализ модулей 1С (`.bsl`), извлекает директивы компиляции (`&НаКлиенте`, `&НаСервере`), экспортные процедуры, параметры и предваряющие комментарии, формируя структурированные таблицы Markdown для приложений к дипломной работе.

## Запуск

```powershell
# Извлечение описания процедур из модуля чата
python .agents/skills/bsl-doc-gen/scripts/extract_bsl_docs.py 1c_extensions/1C_Shared_HTTP.bsl

# Пакетная генерация для всех модулей в 1c_extensions
python .agents/skills/bsl-doc-gen/scripts/extract_bsl_docs.py 1c_extensions/
```
