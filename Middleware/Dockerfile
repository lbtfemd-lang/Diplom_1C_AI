FROM python:3.12-slim

WORKDIR /app

COPY requirements-server.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN echo "FIREWORKS_API_KEY=\nJWT_SECRET=\nTELEGRAM_BOT_TOKEN=\nOPENROUTER_API_KEY=\nJWT_ALGORITHM=HS256\nJWT_EXPIRE_HOURS=24" > .env

RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
