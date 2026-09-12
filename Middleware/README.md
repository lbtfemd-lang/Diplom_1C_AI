# Middleware — интеллектуальный ассистент 1С

FastAPI-сервис обеспечивает JWT-авторизацию, вызов LLM, RAG-поиск по метаданным 1С и хранение канбан-задач в SQLite.

## Локальный запуск

Для безопасного показа используйте из корня `run_demo.bat` или `run_demo.bat --check`. Скрипт требует готовых зависимостей, использует временную БД, случайный JWT-секрет и только локальные правила. Рабочий `.env` не читается, внешние соединения запрещены. После завершения демо-данные удаляются.

`METADATA_DATA_DIR` задаёт отдельный каталог метаданных; `METADATA_ML_ENABLED=false` отключает загрузку ML-модели. Изолированные тесты и демо задают оба параметра до импорта сервисов.

```powershell
cd Middleware
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.venv\Scripts\python.exe main.py
```

Сервис запускается на `http://127.0.0.1:8000`, если это указано в `.env`. Проверки: `/`, `/health`, `/docs`.

Запуск из каталога `Middleware` важен: пути файлов RAG в текущей реализации относительны рабочему каталогу.

## Настройки

| Переменная | Обязательность | Назначение |
|---|---|---|
| `FIREWORKS_API_KEY` | один из двух ключей | Fireworks AI, приоритетный провайдер |
| `OPENROUTER_API_KEY` | один из двух ключей | резервный провайдер |
| `JWT_SECRET` | обязательно вне одноразового стенда | постоянная подпись JWT |
| `JWT_ALGORITHM` | нет | по умолчанию `HS256` |
| `JWT_EXPIRE_HOURS` | нет | по умолчанию `24` |
| `MIDDLEWARE_HOST` | нет | адрес прослушивания |
| `MIDDLEWARE_PORT` | нет | порт, обычно `8000` |
| `LOG_LEVEL` | нет | уровень журналирования |
| `CORS_ORIGINS` | нет | origins через запятую |
| `RATE_LIMIT_ENABLED` | нет | включает ограничения запросов |

Если `JWT_SECRET` не задан, при каждом запуске генерируется новый, и все ранее выданные токены перестают действовать.

## Зависимости и RAG

`requirements.txt` содержит среду разработки и тестов. `requirements-server.txt` используется Docker-образом и не устанавливает `sentence-transformers`/PyTorch.

Без `sentence-transformers` остальные функции сервиса продолжают работать. Однако в текущем коде лексический fallback вызывается только при уже загруженном массиве embeddings; если файла `metadata_embeddings.npy` нет, RAG возвращает пустой список. Это известный дефект облегчённого профиля.

Для полноценного семантического поиска:

```powershell
.venv\Scripts\python.exe -m pip install sentence-transformers
```

Модель `paraphrase-multilingual-MiniLM-L12-v2` будет загружена при первом запуске.

## Тесты

```powershell
.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider
```

На 30 августа 2026 года: `46 passed`. В `pytest.ini` есть устаревшая опция `cache_dir`, а `_run_tests.ps1` создаёт каталог, который может попасть в сбор pytest; до исправления используйте команду выше с явным каталогом `tests`.

## Структура

```text
main.py
app/
├── models/
│   ├── api_models.py
│   ├── auth_models.py
│   └── kanban_models.py
└── services/
    ├── auth_service.py
    ├── kanban_service.py
    ├── llm_service.py
    └── metadata_service.py
tests/
├── test_auth.py
├── test_chat.py
├── test_kanban.py
├── test_llm_post_processing.py
└── test_1c_integration.py
```

Полный контракт маршрутов: [`../docs/API.md`](../docs/API.md). Архитектура и потоки: [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md).

## Изолированный запуск тестов

Из корня репозитория:

```powershell
.\Middleware\.venv\Scripts\python.exe -m pytest Middleware\tests -q -p no:cacheprovider
```

Pytest отключает загрузку `.env` до импорта сервисов, использует временную базу при инициализации и перенаправляет запись метаданных во временные файлы. Реальные HTTP- и почтовые транспорты заблокированы; доступны внутрипроцессные ASGI-запросы и явно заданные заглушки провайдеров. Эти проверки не подтверждают работу живой базы 1С или облачных интеграций.

Отдельный `tests/stress_test_suite.py` также использует временную БД, отключает `.env`, реальные HTTP-вызовы и SMTP/IMAP. Он измеряет локальный режим `offline_rules` через ASGITransport; доставка сообщений подменена. Его отчёт нельзя выдавать за производительность облачной модели, сети или 1С. Запуск из корня: `.\Middleware\.venv\Scripts\python.exe Middleware/tests/stress_test_suite.py`.

## Docker

Из корня проекта:

```powershell
docker compose up --build
```

Контейнер слушает порт `8080`, наружу он публикуется как `${MIDDLEWARE_PORT:-8000}`. Текущий volume подключён к `/app/data`, однако код пишет SQLite и RAG-файлы в `/app`; до исправления путей volume не обеспечивает их сохранность после пересоздания контейнера.

## Безопасность стенда

При пустой базе сервис автоматически создаёт демонстрационные учётные записи, включая `admin/admin` и сервисную запись 1С. Они нужны для локальной демонстрации и недопустимы в открытом или производственном контуре. Перед публикацией смените пароли, задайте сильный `JWT_SECRET`, ограничьте CORS и используйте HTTPS/reverse proxy.
