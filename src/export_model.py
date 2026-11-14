"""Stage 6: export the models the API should serve.

Downloads the `champion` (and `canary`, if there is one) from the MLflow
registry into models/serving/. This folder is a DVC output, so it can be
pushed to S3 and pulled by the CD pipeline when building the API image.
"""
import shutil

import joblib
import mlflow.sklearn
from mlflow import MlflowClient

from common import ROOT, load_params, setup_mlflow, write_json

OUT = ROOT / "models" / "serving"


def export(client: MlflowClient, name: str, alias: str) -> dict | None:
    try:
        mv = client.get_model_version_by_alias(name, alias)
    except Exception:
        return None  # alias not set
    pipe = mlflow.sklearn.load_model(f"models:/{name}@{alias}")
    joblib.dump(pipe, OUT / f"{alias}.joblib")
    return {"version": mv.version, "file": f"{alias}.joblib", "model_type": mv.tags.get("model_type", "")}


def main() -> None:
    params = load_params()
    setup_mlflow(params)
    name = params["mlflow"]["registered_model_name"]
    client = MlflowClient()

    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)
    info = {"model_name": name, "champion": export(client, name, "champion"),
            "canary": export(client, name, "canary")}
    if info["champion"] is None:
        raise SystemExit("No champion model in the registry; run the pipeline first.")
    write_json(info, "models/serving/serving.json")
    canary = f", canary v{info['canary']['version']}" if info["canary"] else ""
    print(f"Exported champion v{info['champion']['version']}{canary} to models/serving/")


if __name__ == "__main__":
    main()
