"""Loads the served models, routes canary traffic and explains each score."""
import json
import os
import random
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import shap

# Share of requests sent to the canary model (only used if a canary exists)
CANARY_WEIGHT = float(os.getenv("CANARY_WEIGHT", "0.1"))
HOT = float(os.getenv("HOT_THRESHOLD", "0.7"))
WARM = float(os.getenv("WARM_THRESHOLD", "0.4"))


def score_band(p: float) -> str:
    return "Hot" if p >= HOT else "Warm" if p >= WARM else "Cold"


class ServedModel:
    """One model pipeline (preprocessing + classifier) plus its SHAP explainer."""

    def __init__(self, path: Path, version: str):
        self.pipe = joblib.load(path)
        self.version = str(version)
        self.prep = self.pipe.named_steps["prep"]
        self.model = self.pipe.named_steps["model"]
        # Names after one-hot encoding, e.g. "cat__lead_source_Google"
        self.feature_names = list(self.prep.get_feature_names_out())
        self.is_tree = not hasattr(self.model, "coef_")
        self.explainer = shap.TreeExplainer(self.model) if self.is_tree else None

    def predict(self, df: pd.DataFrame) -> float:
        return float(self.pipe.predict_proba(df)[0, 1])

    def explain(self, df: pd.DataFrame, top_k: int = 3) -> list[dict]:
        """Top reasons behind one score, grouped back to the original columns."""
        x = self.prep.transform(df)
        if self.is_tree:
            values = self.explainer.shap_values(x)
            if isinstance(values, list):  # some LightGBM versions return [class0, class1]
                values = values[1]
            values = np.asarray(values)
            if values.ndim == 3:  # (rows, features, classes)
                values = values[..., 1]
            contrib = values[0]
        else:
            # Logistic regression: contribution = coefficient x scaled value
            contrib = self.model.coef_[0] * x[0]

        # Add up the one-hot pieces of each column (lead_source_Google -> lead_source)
        totals: dict[str, float] = {}
        for name, value in zip(self.feature_names, contrib):
            col = original_column(name, df.columns)
            totals[col] = totals.get(col, 0.0) + float(value)

        top = sorted(totals.items(), key=lambda kv: abs(kv[1]), reverse=True)[:top_k]
        return [
            {
                "feature": col,
                "value": str(df.iloc[0][col]),
                "effect": "increases" if impact > 0 else "decreases",
                "impact": round(impact, 4),
            }
            for col, impact in top
        ]


def original_column(encoded: str, columns) -> str:
    name = encoded.split("__", 1)[1]  # drop the "num__" / "cat__" prefix
    if name in columns:
        return name
    # One-hot name is "<column>_<category>": find the column it starts with
    matches = [c for c in columns if name.startswith(c + "_")]
    return max(matches, key=len) if matches else name


class ModelService:
    """Champion model for normal traffic, optional canary for a small share."""

    def __init__(self):
        serving_dir = Path(os.getenv("SERVING_DIR", "models/serving"))
        info = json.loads((serving_dir / "serving.json").read_text())
        self.champion = ServedModel(serving_dir / info["champion"]["file"], info["champion"]["version"])
        self.canary = None
        if info.get("canary"):
            self.canary = ServedModel(serving_dir / info["canary"]["file"], info["canary"]["version"])

    def pick(self) -> tuple[str, ServedModel]:
        if self.canary is not None and random.random() < CANARY_WEIGHT:
            return "canary", self.canary
        return "champion", self.champion
