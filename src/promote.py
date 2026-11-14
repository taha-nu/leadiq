"""Finish (or cancel) a canary rollout.

  python src/promote.py                 # canary -> champion, if it looks healthy
  python src/promote.py --rollback      # drop the canary, keep the champion

"Healthy" means the canary has scored at least `min_requests` live leads
(checked through the API) and, if reps gave feedback on its leads, it was
not worse than the champion on them. Afterwards models/serving/ is
re-exported and recorded in DVC; redeploy so the API serves the change.
"""
import argparse
import subprocess
import sys

import requests
from mlflow import MlflowClient

import export_model
from common import ROOT, load_params, setup_mlflow


def refresh_serving_models() -> None:
    export_model.main()
    # Record the new models/serving/ in dvc.lock so `dvc push` uploads it
    subprocess.run([sys.executable, "-m", "dvc", "commit", "-f", "export"], cwd=ROOT, check=True)


def live_stats(api_url: str, version: str) -> tuple[int, float | None]:
    """Number of leads the version scored, and its accuracy on rep feedback."""
    rows = requests.get(f"{api_url}/predictions", params={"limit": 100000}, timeout=30).json()
    mine = [r for r in rows if r["model_version"] == str(version)]
    labelled = [r for r in mine if r["converted"] is not None]
    if not labelled:
        return len(mine), None
    correct = sum((r["probability"] >= 0.5) == bool(r["converted"]) for r in labelled)
    return len(mine), correct / len(labelled)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rollback", action="store_true", help="remove the canary")
    parser.add_argument("--force", action="store_true", help="skip the live traffic check")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    params = load_params()
    setup_mlflow(params)
    name = params["mlflow"]["registered_model_name"]
    min_requests = params["canary"]["min_requests"]
    client = MlflowClient()

    try:
        canary = client.get_model_version_by_alias(name, "canary")
    except Exception:
        raise SystemExit("There is no canary model right now.")

    if args.rollback:
        client.delete_registered_model_alias(name, "canary")
        client.set_model_version_tag(name, canary.version, "decision", "canary rolled back")
        print(f"Rolled back canary v{canary.version}")
        refresh_serving_models()
        return

    if not args.force:
        champion = client.get_model_version_by_alias(name, "champion")
        n, canary_acc = live_stats(args.api_url, canary.version)
        _, champ_acc = live_stats(args.api_url, champion.version)
        print(f"Canary v{canary.version}: {n} live leads, feedback accuracy {canary_acc}")
        print(f"Champion v{champion.version}: feedback accuracy {champ_acc}")
        if n < min_requests:
            raise SystemExit(f"Not enough canary traffic yet ({n} < {min_requests}).")
        if canary_acc is not None and champ_acc is not None and canary_acc < champ_acc:
            raise SystemExit("Canary is doing worse than the champion; consider --rollback.")

    client.set_registered_model_alias(name, "champion", canary.version)
    client.delete_registered_model_alias(name, "canary")
    client.set_model_version_tag(name, canary.version, "decision", "promoted to champion after canary")
    print(f"Promoted v{canary.version} to champion")
    refresh_serving_models()


if __name__ == "__main__":
    main()
