"""Shared helpers: parameters, paths, MLflow setup."""
import hashlib
import json
import subprocess
from pathlib import Path

import mlflow
import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_params(path: str = "params.yaml") -> dict:
    with open(ROOT / path) as f:
        return yaml.safe_load(f)


def file_md5(path: str) -> str:
    h = hashlib.md5()
    with open(ROOT / path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return "uncommitted"


def setup_mlflow(params: dict) -> None:
    cfg = params["mlflow"]
    uri = cfg["tracking_uri"]
    if uri.startswith("sqlite:///") and not uri.startswith("sqlite:////"):
        uri = f"sqlite:///{ROOT / uri.removeprefix('sqlite:///')}"
    mlflow.set_tracking_uri(uri)
    mlflow.set_experiment(cfg["experiment_name"])


def write_json(obj: dict, path: str) -> None:
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2))


def read_json(path: str) -> dict:
    return json.loads((ROOT / path).read_text())
