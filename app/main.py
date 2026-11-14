"""LeadIQ scoring API.

Run locally:  uvicorn app.main:app --reload
Docs:         http://127.0.0.1:8000/docs
"""
import time
import uuid
from contextlib import asynccontextmanager

import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from prometheus_client import Counter, Histogram, make_asgi_app

from app import followup, storage
from app.model_service import CANARY_WEIGHT, ModelService, score_band
from app.schemas import Feedback, Lead, Prediction

# Prometheus metrics (scraped from /metrics)
REQUESTS = Counter("leadiq_requests_total", "HTTP requests", ["path", "status"])
LATENCY = Histogram("leadiq_request_latency_seconds", "Request latency", ["path"])
PREDICTIONS = Counter("leadiq_predictions_total", "Scored leads", ["variant", "band"])
FEEDBACK = Counter("leadiq_feedback_total", "Rep feedback", ["converted"])

models: ModelService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global models
    models = ModelService()  # load the champion (and canary) once at startup
    yield


app = FastAPI(title="LeadIQ", description="Explainable lead scoring", lifespan=lifespan)
app.mount("/metrics", make_asgi_app())


@app.middleware("http")
async def track_requests(request: Request, call_next):
    start = time.perf_counter()
    path = request.url.path
    try:
        response = await call_next(request)
        status = response.status_code
    except Exception:
        status = 500
        raise
    finally:
        if not path.startswith("/metrics"):
            LATENCY.labels(path).observe(time.perf_counter() - start)
            REQUESTS.labels(path, str(status)).inc()
    return response


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/model")
def model_info():
    return {
        "champion_version": models.champion.version,
        "canary_version": models.canary.version if models.canary else None,
        "canary_weight": CANARY_WEIGHT if models.canary else 0.0,
    }


@app.post("/predict", response_model=Prediction)
def predict(lead: Lead):
    features = lead.model_dump()
    df = pd.DataFrame([features])
    variant, model = models.pick()

    probability = model.predict(df)
    band = score_band(probability)
    reasons = model.explain(df)
    follow_up = followup.suggest(band, features, probability, reasons)

    pid = uuid.uuid4().hex[:12]
    storage.save_prediction(pid, model.version, variant, probability, band, features)
    PREDICTIONS.labels(variant, band).inc()
    return {
        "prediction_id": pid,
        "probability": round(probability, 4),
        "band": band,
        "reasons": reasons,
        "follow_up": follow_up,
        "model_version": model.version,
        "variant": variant,
    }


@app.post("/feedback")
def feedback(fb: Feedback):
    if not storage.save_feedback(fb.prediction_id, fb.converted):
        raise HTTPException(404, "Unknown prediction_id")
    FEEDBACK.labels(str(fb.converted).lower()).inc()
    return {"saved": True}


@app.get("/predictions")
def predictions(limit: int = 1000):
    """Recent scored leads with any feedback (used by the dashboard and drift report)."""
    return storage.recent_predictions(limit)


@app.get("/feedback/export")
def export_feedback():
    """Leads reps have labelled, in the training-data format (used for retraining)."""
    return storage.labelled_leads()
