"""Scheduled retraining with Prefect.

Steps: pull rep feedback from the API -> drift report -> if there is enough
new feedback OR drift was found, retrain with `dvc repro` (validate, train,
evaluate, register, export). register.py decides whether the new model
becomes a canary; promote.py finishes the rollout later.

  python flows/retrain_flow.py              # run once now
  python flows/retrain_flow.py --force      # retrain even without new data
  python flows/retrain_flow.py --serve      # weekly schedule (Mondays 02:00)
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import requests
import yaml
from prefect import flow, get_run_logger, task

ROOT = Path(__file__).resolve().parents[1]
PARAMS = yaml.safe_load((ROOT / "params.yaml").read_text())
FEEDBACK = ROOT / PARAMS["data"]["feedback"]


def run(*cmd: str) -> str:
    """Run a command in the project folder and fail the task if it fails."""
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed:\n{result.stdout}\n{result.stderr}")
    return result.stdout


@task(retries=2, retry_delay_seconds=30)
def pull_feedback(api_url: str) -> int:
    """Save all labelled leads from the API; return how many are new."""
    logger = get_run_logger()
    rows = requests.get(f"{api_url}/feedback/export", timeout=60).json()
    old = pd.read_csv(FEEDBACK)
    if not rows:
        logger.info("No rep feedback yet")
        return 0
    new = pd.DataFrame(rows)[old.columns]  # same column order as the training data
    new.to_csv(FEEDBACK, index=False, lineterminator="\n")
    added = len(new) - len(old)
    logger.info(f"{len(new)} labelled leads in total, {added} new")
    return added


@task
def check_drift(api_url: str) -> dict:
    run(sys.executable, "src/drift.py", "--api-url", api_url)
    result = json.loads((ROOT / "reports" / "drift" / "drift.json").read_text())
    get_run_logger().info(f"Drift: {result}")
    return result


@task
def retrain() -> dict:
    logger = get_run_logger()
    run(sys.executable, "-m", "dvc", "add", str(FEEDBACK.relative_to(ROOT)))  # version the new data
    logger.info(run(sys.executable, "-m", "dvc", "repro"))
    if run(sys.executable, "-m", "dvc", "remote", "list").strip():
        run(sys.executable, "-m", "dvc", "push")  # upload data + models to S3
    return json.loads((ROOT / "reports" / "registry.json").read_text())


@flow(name="leadiq-retrain")
def retrain_flow(api_url: str = "http://127.0.0.1:8000", force: bool = False) -> str:
    logger = get_run_logger()
    new_feedback = pull_feedback(api_url)
    drift = check_drift(api_url)

    enough_feedback = new_feedback >= PARAMS["retrain"]["min_new_feedback"]
    if not (force or enough_feedback or drift["drift_detected"]):
        msg = f"No retraining needed ({new_feedback} new labelled leads, no drift)"
        logger.info(msg)
        return msg

    registry = retrain()
    msg = f"Retrained: model v{registry['version']} {registry['decision']}"
    logger.info(msg)
    return msg


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--serve", action="store_true", help="run on a weekly schedule")
    args = parser.parse_args()

    if args.serve:
        retrain_flow.serve(name="weekly-retrain", cron="0 2 * * 1",
                           parameters={"api_url": args.api_url})
    else:
        print(retrain_flow(api_url=args.api_url, force=args.force))
