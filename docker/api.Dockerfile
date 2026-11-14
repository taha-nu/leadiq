# Scoring API image: FastAPI + the exported champion/canary models
FROM python:3.12-slim

# XGBoost and LightGBM need the OpenMP runtime
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

COPY app/ app/
# Produced by the `export` stage (dvc repro, or dvc pull in CI/CD)
COPY models/serving/ models/serving/

ENV SERVING_DIR=/app/models/serving \
    APP_DB=/app/data/leadiq.db \
    PYTHONUNBUFFERED=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
