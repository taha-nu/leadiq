"""Publish the served models so CI/CD can build the API image.

Packs models/serving/ (champion + canary exported from the MLflow registry)
into one file and uploads it to the GitHub release `model-latest`. The CD
pipeline downloads it and bakes it into the API image.

  python src/publish_model.py

Needs the GitHub CLI (`gh`) logged in.
"""
import json
import subprocess
import tarfile

from common import ROOT

TAG = "model-latest"
ARCHIVE = ROOT / "models" / "serving.tar.gz"


def gh(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], cwd=ROOT, capture_output=True, text=True, check=check)


def main() -> None:
    info = json.loads((ROOT / "models" / "serving" / "serving.json").read_text())
    with tarfile.open(ARCHIVE, "w:gz") as tar:
        tar.add(ROOT / "models" / "serving", arcname="serving")

    canary = f", canary v{info['canary']['version']}" if info["canary"] else ""
    notes = f"Served models: champion v{info['champion']['version']}{canary}"
    if gh("release", "view", TAG, check=False).returncode != 0:
        gh("release", "create", TAG, "--title", "Served models", "--notes", notes)
    else:
        gh("release", "edit", TAG, "--notes", notes)
    gh("release", "upload", TAG, str(ARCHIVE), "--clobber")
    print(f"Published {notes} to release '{TAG}'")


if __name__ == "__main__":
    main()
