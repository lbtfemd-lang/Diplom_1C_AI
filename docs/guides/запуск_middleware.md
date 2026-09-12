# Запуск Middleware — пошаговая инструкция

## Шаг 1. Установить Python 3.12

```powershell
winget install Python.Python.3.12
```

Или скачать с https://python.org (галочка **Add to PATH**). Перезапустить терминал, проверить:

```powershell
python --version
```

Должно показать `Python 3.12.x`.

---

## Шаг 2. Создать виртуальное окружение

```powershell
cd D:\Share\Projects\diplom\Middleware
python -m venv .venv
```

> Если `.venv` уже существует от другого ПК — **удалить и пересоздать**:
> ```powershell
> Remove-Item -Recurse -Force .venv
> python -m venv .venv
> ```
> Иначе возможна ошибка `ModuleNotFoundError: No module named 'pydantic_core._pydantic_core'`
> (скомпилированные .pyd файлы несовместимы между ПК/версиями Python).

---

## Шаг 3. Установить зависимости

**Полный набор** (с ML-моделями для качественного RAG-поиска):
```powershell
.venv\Scripts\pip install -r requirements.txt
pip install sentence-transformers
```

> sentence-transformers + torch весят ~2-4 ГБ, установка 5-10 мин.

**Облегчённый набор** (без ML; текущая версия запускается, но RAG-кандидаты без embeddings не формируются):
```powershell
.venv\Scripts\pip install -r requirements-server.txt
```

> Если при установке pip падает с ошибкой кэша:
> ```powershell
> .venv\Scripts\pip install --no-cache-dir -r requirements.txt
> ```

---

## Шаг 4. Настроить .env

Файл `.env` уже есть в `Middleware/`. Проверить что заполнены ключи:

```
FIREWORKS_API_KEY=fw_ваш_ключ
JWT_SECRET=случайная_строка_32_символа
JWT_ALGORITHM=HS256
JWT_EXPIRE_HOURS=24
MIDDLEWARE_HOST=127.0.0.1
MIDDLEWARE_PORT=8000
```

- **FIREWORKS_API_KEY** — получить на https://fireworks.ai → Account → API Keys
- **OPENROUTER_API_KEY** — запасной провайдер (если FIREWORKS не задан)
- **MIDDLEWARE_HOST** — `127.0.0.1` локально, `0.0.0.0` для доступа с мобильного

---

## Шаг 5. Запустить сервер

**Вариант А** — bat-файл из корня проекта:
```
Двойной клик на start.bat в папке diplom\
```

**Вариант Б** — вручную:
```powershell
cd D:\Share\Projects\diplom\Middleware
.venv\Scripts\python main.py
```

**Вариант В** — через uvicorn (полезно для перезагрузки при разработке):
```powershell
cd D:\Share\Projects\diplom\Middleware
.venv\Scripts\python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

Должно появиться:
```
Using Fireworks AI (GLM 5.1)
LLM client initialized. Model: accounts/fireworks/models/glm-5p1
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete.
```

---

## Шаг 6. Проверить что сервер работает

В браузере: http://127.0.0.1:8000/ → должен вернуть:
```json
{"status":"ok","service":"1C AI Assistant Middleware"}
```

Интерактивная документация API: http://127.0.0.1:8000/docs

---

## Шаг 7. Запустить тесты (опционально)

```powershell
cd D:\Share\Projects\diplom\Middleware
.venv\Scripts\python -m pytest tests --tb=short -q -p no:cacheprovider
```

На актуальной версии должно показать: `46 passed`.

---

## Возможные проблемы и решения

| Проблема | Причина | Решение |
|----------|---------|---------|
| `ModuleNotFoundError: No module named 'pydantic_core._pydantic_core'` | .venv от другого ПК, .pyd файлы несовместимы | Удалить `.venv`, пересоздать, переустановить зависимости |
| `[Errno 10048]` при запуске | Порт 8000 занят предыдущим процессом | Закрыть предыдущий процесс: `Get-Process -Name python \| Stop-Process` |
| `pip install` падает с `Cache entry deserialization failed` | Повреждён кэш pip | `pip install --no-cache-dir -r requirements.txt` |
| sentence-transformers не ставится | Тяжёлая зависимость (torch) | Остальные функции работают, но текущий RAG без embeddings не возвращает кандидатов |
