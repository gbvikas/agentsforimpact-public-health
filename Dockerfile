# Agent + dashboard service for Cloud Run.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY agent/ agent/
COPY dashboard/ dashboard/
ENV PYTHONUNBUFFERED=1 MEMORY_STORE=/tmp/memory_store.json
CMD ["sh", "-c", "uvicorn dashboard.app:app --host 0.0.0.0 --port ${PORT:-8080}"]
