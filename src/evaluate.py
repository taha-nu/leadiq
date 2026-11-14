"""Stage 4: evaluate the best model on the held-out test set.

Logs test metrics, a ROC curve and a SHAP feature-importance plot to the
best model's MLflow run, and writes metrics for `dvc metrics show`.
"""
import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mlflow
import numpy as np
import pandas as pd
import shap
from sklearn.metrics import (
    RocCurveDisplay,
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from common import ROOT, load_params, read_json, setup_mlflow, write_json


def score_band(p: float, hot: float, warm: float) -> str:
    return "Hot" if p >= hot else "Warm" if p >= warm else "Cold"


def shap_plot(pipe, X: pd.DataFrame, path) -> None:
    prep, model = pipe.named_steps["prep"], pipe.named_steps["model"]
    Xt = prep.transform(X.sample(min(500, len(X)), random_state=0))
    names = [n.split("__", 1)[1] for n in prep.get_feature_names_out()]
    if hasattr(model, "coef_"):
        explainer = shap.LinearExplainer(model, Xt)
    else:
        explainer = shap.TreeExplainer(model)
    values = explainer.shap_values(Xt)
    if isinstance(values, list):
        values = values[1]
    plt.figure()
    shap.summary_plot(values, Xt, feature_names=names, plot_type="bar", max_display=12, show=False)
    plt.title("Top drivers of lead conversion")
    plt.xlabel("Mean |SHAP value| (impact on prediction)")
    plt.savefig(path, dpi=120, bbox_inches="tight")
    plt.close()


def main() -> None:
    params = load_params()
    target = params["base"]["target"].lower()
    ecfg = params["evaluate"]
    setup_mlflow(params)

    test = pd.read_csv(ROOT / params["data"]["processed_dir"] / "test.csv")
    X, y = test.drop(columns=[target]), test[target]
    pipe = joblib.load(ROOT / "models" / "model.joblib")
    proba = pipe.predict_proba(X)[:, 1]
    pred = (proba >= 0.5).astype(int)

    bands = pd.Series([score_band(p, ecfg["hot_threshold"], ecfg["warm_threshold"]) for p in proba])
    band_rates = {
        f"conversion_rate_{b.lower()}": round(float(y.values[bands.values == b].mean()), 4)
        for b in ["Hot", "Warm", "Cold"] if (bands == b).any()
    }
    metrics = {
        "test_roc_auc": round(roc_auc_score(y, proba), 4),
        "test_accuracy": round(accuracy_score(y, pred), 4),
        "test_precision": round(precision_score(y, pred), 4),
        "test_recall": round(recall_score(y, pred), 4),
        "test_f1": round(f1_score(y, pred), 4),
        **band_rates,
    }

    plots = ROOT / "reports" / "plots"
    plots.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(5, 4))
    RocCurveDisplay.from_predictions(y, proba, ax=ax, name="Best model")
    ax.plot([0, 1], [0, 1], linestyle="--", color="grey")
    ax.set_title("ROC curve on test set")
    fig.tight_layout()
    fig.savefig(plots / "roc_curve.png", dpi=120)
    plt.close(fig)
    shap_plot(pipe, X, plots / "shap_importance.png")

    best_run = read_json("reports/train.json")["best"]["run_id"]
    with mlflow.start_run(run_id=best_run):
        mlflow.log_metrics(metrics)
        mlflow.log_artifact(str(plots / "roc_curve.png"))
        mlflow.log_artifact(str(plots / "shap_importance.png"))

    write_json(metrics, "metrics/test_metrics.json")
    print(", ".join(f"{k}={v}" for k, v in metrics.items()))


if __name__ == "__main__":
    main()
