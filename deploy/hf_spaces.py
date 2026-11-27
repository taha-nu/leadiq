"""Create or update the two Hugging Face Spaces (always-online demo).

Each Space is a one-line Dockerfile that starts from our image in GitHub
Container Registry, pinned to the commit CD just built, so pushing it makes
Hugging Face rebuild with the new version.

  HF_TOKEN=... HF_USERNAME=... IMAGE_TAG=<git sha> python deploy/hf_spaces.py
"""
import os
import tempfile
from pathlib import Path

from huggingface_hub import HfApi

user = os.environ["HF_USERNAME"]
tag = os.environ["IMAGE_TAG"]
api = HfApi(token=os.environ["HF_TOKEN"])

API_SPACE = f"{user}/leadiq-api"
API_URL = f"https://{user.lower()}-leadiq-api.hf.space"

# Hugging Face runs containers as a non-root user, so writable paths go to /tmp
SPACES = {
    API_SPACE: {
        "title": "LeadIQ API",
        "port": 8000,
        "dockerfile": f"FROM ghcr.io/taha-nu/leadiq-api:{tag}\n"
                      "ENV APP_DB=/tmp/leadiq.db HOME=/tmp MPLCONFIGDIR=/tmp\n",
    },
    f"{user}/leadiq-dashboard": {
        "title": "LeadIQ Dashboard",
        "port": 8501,
        "dockerfile": f"FROM ghcr.io/taha-nu/leadiq-dashboard:{tag}\n"
                      f"ENV API_URL={API_URL} HOME=/tmp\n",
    },
}

for repo_id, s in SPACES.items():
    readme = (f"---\ntitle: {s['title']}\nemoji: 📈\ncolorFrom: blue\ncolorTo: green\n"
              f"sdk: docker\napp_port: {s['port']}\npinned: false\n---\n\n"
              "Live demo of LeadIQ, deployed automatically by GitHub Actions from "
              "https://github.com/taha-nu/leadiq\n")
    api.create_repo(repo_id, repo_type="space", space_sdk="docker", exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "Dockerfile").write_text(s["dockerfile"])
        (Path(tmp) / "README.md").write_text(readme, encoding="utf-8")
        api.upload_folder(folder_path=tmp, repo_id=repo_id, repo_type="space",
                          commit_message=f"Deploy {tag[:7]}")
    print(f"Updated https://huggingface.co/spaces/{repo_id}")
