# Development-focused backend image for local docker-compose use.
# This mirrors the existing scripts/README workflow: install Python deps once,
# bind-mount the backend source, and run uvicorn with live reload enabled.

FROM python:3.10-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WATCHFILES_FORCE_POLLING=true

COPY requirements.txt ./requirements.txt

RUN python -m pip install --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

EXPOSE 8000

CMD ["sh", "-c", "if [ -f /app/.env ]; then uvicorn app.main:app --app-dir /app --reload --env-file /app/.env --host 0.0.0.0 --port 8000; else echo 'Warning: backend/.env not found. Using process environment only.'; uvicorn app.main:app --app-dir /app --reload --host 0.0.0.0 --port 8000; fi"]
