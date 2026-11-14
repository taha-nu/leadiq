"""Stage 3: train every candidate model and track each run in MLflow.

Each model/hyperparameter combination is a nested MLflow run that logs its
parameters, cross-validated metrics (on the train set only), a confusion
matrix and the fitted model. The best candidate is saved for evaluation.
"""
import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mlflow
import pandas as pd
from lightgbm import LGBMClassifier
from mlflow.models import infer_signature
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import ConfusionMatrixDisplay
from sklearn.model_selection import StratifiedKFold, cross_val_predict, cross_validate
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from skops.io import dumps as skops_dumps
from skops.io import get_untrusted_types
from xgboost import XGBClassifier

from common import ROOT, file_md5, git_commit, load_params, setup_mlflow, write_json

SCORING = ["roc_auc", "accuracy", "precision", "recall", "f1"]


def make_estimator(name: str, hp: dict, seed: int):
    if name == "logistic_regression":
        return LogisticRegression(random_state=seed, **hp)
    if name == "xgboost":
        return XGBClassifier(random_state=seed, eval_metric="logloss", n_jobs=-1, **hp)
    if name == "lightgbm":
        return LGBMClassifier(random_state=seed, verbose=-1, n_jobs=-1, **hp)
    raise ValueError(f"Unknown model: {name}")


def make_pipeline(estimator, X: pd.DataFrame) -> Pipeline:
    cat = X.select_dtypes(exclude="number").columns.tolist()
    num = X.select_dtypes(include="number").columns.tolist()
    prep = ColumnTransformer(
        [
            ("num", StandardScaler(), num),
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), cat),
        ]
    )
    return Pipeline([("prep", prep), ("model", estimator)])


def main() -> None:
    params = load_params()
    seed = params["base"]["random_state"]
    target = params["base"]["target"].lower()
    tcfg = params["train"]
    setup_mlflow(params)

    train_path = f"{params['data']['processed_dir']}/train.csv"
    train = pd.read_csv(ROOT / train_path)

    # Add leads that sales reps labelled through the app (feedback loop)
    feedback = pd.read_csv(ROOT / params["data"]["feedback"])
    if len(feedback):
        train = pd.concat([train, feedback[train.columns]], ignore_index=True)
    print(f"Training on {len(train)} rows ({len(feedback)} from rep feedback)")
    X, y = train.drop(columns=[target]), train[target]
    cv = StratifiedKFold(n_splits=tcfg["cv_folds"], shuffle=True, random_state=seed)
    metric = tcfg["selection_metric"]

    common_tags = {
        "train_data_md5": file_md5(train_path),
        "feedback_data_md5": file_md5(params["data"]["feedback"]),
        "feedback_rows": str(len(feedback)),
        "raw_data_md5": file_md5(params["data"]["raw"]),
        "git_commit": git_commit(),
    }
    results = []

    with mlflow.start_run(run_name="train-candidates") as parent:
        mlflow.set_tags({**common_tags, "stage": "train"})
        mlflow.log_params({"cv_folds": tcfg["cv_folds"], "selection_metric": metric})

        for model_name, grid in tcfg["models"].items():
            for i, hp in enumerate(grid):
                run_name = f"{model_name}-{i + 1}"
                with mlflow.start_run(run_name=run_name, nested=True) as run:
                    pipe = make_pipeline(make_estimator(model_name, hp, seed), X)
                    scores = cross_validate(pipe, X, y, cv=cv, scoring=SCORING)
                    cv_metrics = {f"cv_{m}": float(scores[f"test_{m}"].mean()) for m in SCORING}

                    mlflow.set_tags({**common_tags, "model_type": model_name})
                    mlflow.log_params({"model_type": model_name, **hp})
                    mlflow.log_metrics(cv_metrics)

                    # Confusion matrix from out-of-fold predictions
                    oof = cross_val_predict(pipe, X, y, cv=cv)
                    fig, ax = plt.subplots(figsize=(4, 4))
                    ConfusionMatrixDisplay.from_predictions(
                        y, oof, display_labels=["Not converted", "Converted"], ax=ax, colorbar=False
                    )
                    ax.set_title(run_name)
                    fig.tight_layout()
                    mlflow.log_figure(fig, "confusion_matrix.png")
                    plt.close(fig)

                    pipe.fit(X, y)
                    # MLflow saves models with skops (safer than pickle). We trust the
                    # XGBoost/LightGBM types of the model we just trained ourselves.
                    trusted = get_untrusted_types(data=skops_dumps(pipe))
                    mlflow.sklearn.log_model(
                        pipe,
                        name="model",
                        skops_trusted_types=trusted,
                        signature=infer_signature(X, pipe.predict_proba(X)[:, 1]),
                        input_example=X.head(3),
                    )
                    results.append(
                        {"run_id": run.info.run_id, "run_name": run_name, "model_type": model_name,
                         "params": hp, **cv_metrics, "pipe": pipe}
                    )
                    print(f"{run_name:<24} cv_{metric}={cv_metrics[f'cv_{metric}']:.4f}")

        best = max(results, key=lambda r: r[f"cv_{metric}"])
        mlflow.log_metric(f"best_cv_{metric}", best[f"cv_{metric}"])
        mlflow.set_tag("best_child_run", best["run_name"])

    (ROOT / "models").mkdir(exist_ok=True)
    joblib.dump(best["pipe"], ROOT / "models" / "model.joblib")
    leaderboard = sorted(
        [{k: v for k, v in r.items() if k != "pipe"} for r in results],
        key=lambda r: -r[f"cv_{metric}"],
    )
    write_json({"parent_run_id": parent.info.run_id, "best": leaderboard[0], "leaderboard": leaderboard},
               "reports/train.json")
    print(f"Best: {best['run_name']} (cv_{metric}={best[f'cv_{metric}']:.4f})")


if __name__ == "__main__":
    main()
