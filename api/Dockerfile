FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY api/ /app/api
COPY tasks/ /app/tasks

EXPOSE 5000
# Run uvicorn server for FastAPI
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port 5000 --workers ${WEB_CONCURRENCY:-4}"]
