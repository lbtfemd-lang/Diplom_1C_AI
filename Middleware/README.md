# Инструкция по запуску Python Middleware

1.  Установите Python (если не установлен): [python.org](https://www.python.org/downloads/)
2.  Откройте терминал в папке `Middleware`.
3.  Создайте виртуальное окружение:
    ```bash
    python -m venv venv
    ```
4.  Активируйте окружение:
    *   Windows: `venv\Scripts\activate`
    *   Linux/Mac: `source venv/bin/activate`
5.  Установите зависимости:
    ```bash
    pip install -r requirements.txt
    ```
6.  Запустите сервер:
    ```bash
    uvicorn main:app --reload
    ```
    Сервер должен запуститься на `http://127.0.0.1:8000`.

7.  Для проверки откройте в браузере `http://127.0.0.1:8000/docs` - это интерактивная документация API.
