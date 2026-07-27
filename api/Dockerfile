FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY api/app.py api/workspace_manager.py ./
COPY tasks /app/tasks

EXPOSE 5000
# gunicorn instead of Flask's dev server -- the dev server is single-threaded
# and becomes a real bottleneck once more than a couple students are hitting
# /api/tasks and /api/tasks/<id>/check at once. 4 workers x 2 threads gives
# 8-way concurrency; bump WEB_CONCURRENCY via env if you deploy on a bigger box.
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:5000 --workers ${WEB_CONCURRENCY:-4} --threads 2 --timeout 60 app:app"]
