"""API tests. A tiny model is trained on fake leads, so no real data is needed."""
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from xgboost import XGBClassifier

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from app.schemas import Lead  # noqa: E402
from train import make_pipeline  # noqa: E402


def fake_leads(n: int = 300) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    df = pd.DataFrame([Lead(lead_origin="API").model_dump() for _ in range(n)])
    df["lead_origin"] = rng.choice(["API", "Landing Page Submission", "Lead Add Form"], n)
    df["lead_source"] = rng.choice(["Google", "Direct Traffic", "Reference"], n)
    df["total_time_spent_on_website"] = rng.integers(0, 2000, n)
    df["totalvisits"] = rng.integers(0, 15, n)
    return df


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Train a small XGBoost pipeline where time on site drives conversion
    X = fake_leads()
    y = (X["total_time_spent_on_website"] > 900).astype(int)
    pipe = make_pipeline(XGBClassifier(n_estimators=20, max_depth=2), X).fit(X, y)
    joblib.dump(pipe, tmp_path / "champion.joblib")
    (tmp_path / "serving.json").write_text(json.dumps(
        {"champion": {"version": "1", "file": "champion.joblib"}, "canary": None}))

    monkeypatch.setenv("SERVING_DIR", str(tmp_path))
    monkeypatch.setenv("APP_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")  # use the template follow-up

    from app.main import app
    with TestClient(app) as c:
        yield c


HOT_LEAD = {"lead_origin": "Lead Add Form", "lead_source": "Reference",
            "total_time_spent_on_website": 1800, "totalvisits": 5}


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_predict_returns_band_reasons_and_follow_up(client):
    r = client.post("/predict", json=HOT_LEAD)
    assert r.status_code == 200
    body = r.json()
    assert 0 <= body["probability"] <= 1
    assert body["band"] == "Hot"
    assert len(body["reasons"]) == 3
    assert body["reasons"][0]["feature"] == "total_time_spent_on_website"
    assert body["follow_up"]["source"] == "template"
    assert body["follow_up"]["email_opener"]  # Hot leads get an email opener
    assert body["variant"] == "champion"


def test_invalid_lead_is_rejected(client):
    r = client.post("/predict", json={"lead_origin": "API", "totalvisits": -3})
    assert r.status_code == 422


def test_feedback_becomes_training_data(client):
    pid = client.post("/predict", json=HOT_LEAD).json()["prediction_id"]
    assert client.post("/feedback", json={"prediction_id": pid, "converted": True}).status_code == 200
    rows = client.get("/feedback/export").json()
    assert len(rows) == 1 and rows[0]["converted"] == 1
    assert rows[0]["total_time_spent_on_website"] == 1800


def test_feedback_for_unknown_lead_is_404(client):
    r = client.post("/feedback", json={"prediction_id": "nope", "converted": False})
    assert r.status_code == 404


def test_metrics_endpoint(client):
    client.post("/predict", json=HOT_LEAD)
    text = client.get("/metrics/").text
    assert "leadiq_predictions_total" in text
    assert "leadiq_request_latency_seconds" in text
