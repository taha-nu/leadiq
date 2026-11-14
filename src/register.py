"""Stage 5: register the best model in the MLflow Model Registry.

Every pipeline run creates a new version of `leadiq-classifier`, tagged with
its model type, metrics and data version. Aliases decide what is served:
- no champion yet       -> the new version becomes `champion`
- beats the champion    -> `canary` (gets a small share of live traffic;
                           src/promote.py makes it champion later)
- not better            -> `challenger` (kept for the record, not served)
"""
import mlflow
from mlflow import MlflowClient

from common import load_params, read_json, setup_mlflow, write_json


def main() -> None:
    params = load_params()
    setup_mlflow(params)
    name = params["mlflow"]["registered_model_name"]
    client = MlflowClient()

    best = read_json("reports/train.json")["best"]
    test_metrics = read_json("metrics/test_metrics.json")
    run = client.get_run(best["run_id"])

    mv = mlflow.register_model(f"runs:/{best['run_id']}/model", name)
    client.update_registered_model(
        name, description="LeadIQ lead conversion classifier (Hot / Warm / Cold lead scoring)."
    )
    tags = {
        "model_type": best["model_type"],
        "test_roc_auc": test_metrics["test_roc_auc"],
        "test_f1": test_metrics["test_f1"],
        "raw_data_md5": run.data.tags.get("raw_data_md5", ""),
        "train_data_md5": run.data.tags.get("train_data_md5", ""),
        "git_commit": run.data.tags.get("git_commit", ""),
    }
    for k, v in tags.items():
        client.set_model_version_tag(name, mv.version, k, str(v))

    # Promote only if better than the current champion
    try:
        champ = client.get_model_version_by_alias(name, "champion")
        champ_auc = float(champ.tags.get("test_roc_auc", 0))
    except Exception:
        champ, champ_auc = None, -1.0

    if champ is None:
        client.set_registered_model_alias(name, "champion", mv.version)
        decision = "first model, promoted to champion"
    elif test_metrics["test_roc_auc"] > champ_auc:
        # Better models are not trusted blindly: they go to canary first
        client.set_registered_model_alias(name, "canary", mv.version)
        decision = f"better than champion v{champ.version}, sent to canary"
    else:
        client.set_registered_model_alias(name, "challenger", mv.version)
        decision = f"kept as challenger (not better than champion v{champ.version})"

    client.set_model_version_tag(name, mv.version, "decision", decision)
    write_json(
        {"model_name": name, "version": int(mv.version), "decision": decision, **tags},
        "reports/registry.json",
    )
    print(f"Registered {name} v{mv.version}: {decision}")


if __name__ == "__main__":
    main()
