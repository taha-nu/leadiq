"""Data and prediction drift report with Evidently.

Compares the leads the live API has scored (current) with the training data
(reference). The `probability` column covers prediction drift: for the
reference it is what the champion model predicts on the training set.

  python src/drift.py --api-url http://127.0.0.1:8000

Writes reports/drift/drift_report.html and reports/drift/drift.json.
"""
import argparse
import json

import joblib
import pandas as pd
import requests
from evidently import Report
from evidently.presets import DataDriftPreset

from common import ROOT, load_params, write_json

MIN_ROWS = 30  # too few live leads gives meaningless drift results


def column_drifted(metric_name: str, value: float) -> bool:
    """Evidently picks the test per column, e.g.
    'ValueDrift(column=a,method=K-S p_value,threshold=0.05)'  -> drift if value < threshold
    'ValueDrift(column=a,method=Wasserstein distance (normed),threshold=0.1)' -> drift if value >= threshold
    """
    threshold = float(metric_name.split("threshold=")[1].rstrip(")"))
    return value < threshold if "p_value" in metric_name else value >= threshold


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    params = load_params()
    target = params["base"]["target"].lower()

    reference = pd.read_csv(ROOT / params["data"]["processed_dir"] / "train.csv").drop(columns=[target])
    champion = joblib.load(ROOT / "models" / "serving" / "champion.joblib")
    reference["probability"] = champion.predict_proba(reference)[:, 1]

    rows = requests.get(f"{args.api_url}/predictions", params={"limit": 5000}, timeout=30).json()
    if len(rows) < MIN_ROWS:
        result = {"status": "skipped", "reason": f"only {len(rows)} live leads (need {MIN_ROWS})",
                  "drift_detected": False}
        write_json(result, "reports/drift/drift.json")
        print(result["reason"])
        return

    current = pd.DataFrame([json.loads(r["features"]) for r in rows])
    current["probability"] = [r["probability"] for r in rows]
    current = current[reference.columns]

    share = params["retrain"]["drift_share"]
    snapshot = Report([DataDriftPreset(drift_share=share)]).run(current, reference)
    (ROOT / "reports" / "drift").mkdir(parents=True, exist_ok=True)
    snapshot.save_html(str(ROOT / "reports" / "drift" / "drift_report.html"))

    drifted_share, drifted_cols = 0.0, []
    for m in snapshot.dict()["metrics"]:
        name = m["metric_name"]
        if name.startswith("DriftedColumnsCount"):
            drifted_share = m["value"]["share"]
        elif name.startswith("ValueDrift") and column_drifted(name, m["value"]):
            drifted_cols.append(name.split("column=")[1].split(",")[0])

    result = {
        "status": "done",
        "live_rows": len(current),
        "drifted_share": round(drifted_share, 3),
        "drifted_columns": drifted_cols,
        "prediction_drift": "probability" in drifted_cols,
        "drift_detected": drifted_share >= share,
    }
    write_json(result, "reports/drift/drift.json")
    print(f"Drifted columns: {drifted_cols or 'none'} (share {drifted_share:.0%}); "
          f"drift detected: {result['drift_detected']}")


if __name__ == "__main__":
    main()
