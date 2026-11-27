# LeadIQ: Explainable Lead Scoring with an End-to-End MLOps Pipeline

LeadIQ predicts which sales leads are likely to convert and sorts them into **Hot / Warm / Cold** bands, explains each score with SHAP, and suggests a follow-up action, so a sales team can focus on the leads that matter.

**Dataset:** [X Education Lead Scoring (Kaggle)](https://www.kaggle.com/datasets/amritachatterjee09/lead-scoring-dataset): 9,240 leads, 37 columns, target `Converted` (38.5% converted).

```
          training loop                                     serving loop
 leads.csv ─► validate ─► preprocess ─► train ─► evaluate ─► register ─► export ─► Docker ─► ECS (API + dashboard)
   (DVC)     (Pandera)                 (MLflow)            (registry)                          │
     ▲                                                                                        ▼
     └──────── Prefect retrain flow ◄── rep feedback + Evidently drift ◄──── Prometheus / Grafana / CloudWatch
```

## Cloud architecture

![LeadIQ cloud architecture](docs/architecture.png)

Generated from code: `python docs/architecture.py` (needs Graphviz and `pip install diagrams`).

## Results

| Model (best of each family) | CV ROC-AUC | CV F1 |
| --- | --- | --- |
| **XGBoost** (depth 3, 200 trees), selected | **0.908** | **0.782** |
| LightGBM (15 leaves, 200 trees) | 0.905 | 0.774 |
| Logistic Regression (C = 1.0) | 0.898 | 0.761 |

On the held-out test set (1,848 leads) the selected model scores **ROC-AUC 0.890, F1 0.766**. Leads it marks **Hot** converted **82%** of the time, versus **60%** for Warm and **13%** for Cold.

## Training pipeline (`dvc repro`)

| Stage | Script | What it does | Outputs |
| --- | --- | --- | --- |
| validate | `src/validate.py` | Pandera schema checks (types, allowed values, unique IDs, no negative counts). Stops the pipeline if the data is bad. | `reports/validation.json` |
| preprocess | `src/preprocess.py` | Treats the form default "Select" as missing, drops IDs, **leakage columns filled in by sales after contact** (`Tags`, `Lead Quality`, ...) and mostly-empty columns, caps outliers, imputes, groups rare categories, stratified 80/20 split. | `data/processed/train.csv`, `test.csv` |
| train | `src/train.py` | Adds rep-labelled leads from `data/feedback/feedback.csv`, trains 6 candidates (Logistic Regression, XGBoost, LightGBM × 2 settings) with 5-fold CV. Each is a nested MLflow run with params, metrics, confusion matrix and model. | `models/model.joblib`, `reports/train.json` |
| evaluate | `src/evaluate.py` | Test-set metrics, Hot/Warm/Cold conversion rates, ROC curve and SHAP importance, logged to MLflow. | `metrics/test_metrics.json`, `reports/plots/` |
| register | `src/register.py` | Registers `leadiq-classifier` with tags (model type, metrics, data hashes, git commit) and sets an alias (see below). | `reports/registry.json` |
| export | `src/export_model.py` | Copies the `champion` (and `canary`) model from the registry into the folder the API image is built from. | `models/serving/` |

All settings live in `params.yaml`; changing one and running `dvc repro` reruns only the affected stages.

**Model registry aliases**

| Alias | Meaning |
| --- | --- |
| `champion` | Serves normal traffic. The first model gets it automatically. |
| `canary` | A new version that beat the champion's test ROC-AUC. Gets a small share of live traffic (`CANARY_WEIGHT`, default 10%). |
| `challenger` | A new version that was not better. Kept for the record, never served. |

`python src/promote.py` makes the canary the champion once it has scored at least `canary.min_requests` live leads and is not doing worse than the champion on rep feedback. `--rollback` drops it instead.

## Serving

- **API** (`app/`, FastAPI): `POST /predict` returns probability, band, the top 3 SHAP reasons and a follow-up suggestion. Hot leads get a next action and an email opener from an LLM (Claude) when `ANTHROPIC_API_KEY` is set; otherwise a template is used. `POST /feedback` stores the rep's converted / lost outcome. `GET /metrics` exposes Prometheus metrics. Docs at `/docs`.
- **Dashboard** (`dashboard/app.py`, Streamlit): score a lead and record the outcome, plus lead pipeline quality over time (leads per band per day, average probability, real conversion rate by band, recent leads).

## Monitoring and retraining

- **Prometheus + Grafana** (`monitoring/`): request rate, p95 latency, error rate, leads by band, champion vs canary traffic, feedback rate. Alert rules: API down, error rate > 5%, p95 latency > 1 s, more than 80% Cold leads.
- **Evidently** (`src/drift.py`): compares live leads (and predicted probabilities) with the training data and writes `reports/drift/`.
- **Prefect** (`flows/retrain_flow.py`): pulls rep feedback from the API, runs the drift report, and if there are at least 50 new labelled leads or drift was found, versions the feedback with DVC and runs `dvc repro`. Scheduled weekly with `--serve`.
- **CloudWatch**: CPU and status-check alarms on the AWS server, with SNS email alerts.

## How to run

Requires Python 3.12 and Docker.

```bash
python -m venv .venv && .venv\Scripts\activate          # Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
dvc pull            # or download "Lead Scoring.csv" from Kaggle to data/raw/leads.csv
dvc repro           # full training pipeline
pytest -q           # unit tests
mlflow ui --backend-store-uri sqlite:///mlflow.db       # http://127.0.0.1:5000
```

Whole app on one machine:

```bash
docker compose up --build
# API http://localhost:8000/docs   Dashboard http://localhost:8501
# Prometheus http://localhost:9090  Grafana http://localhost:3000 (admin / admin)
python src/simulate_traffic.py --n 200       # send test leads (+ feedback) for a demo
python src/drift.py                          # drift report
python flows/retrain_flow.py                 # retraining flow, once
python src/promote.py                        # finish a canary rollout
```

Each machine keeps its own MLflow store (`mlflow.db`). After `dvc pull`, run `dvc repro -f` once to fill your local MLflow.

## Deployment

**CI/CD.** Every push to `main` runs CI: tests, Docker image build and Terraform checks. When CI passes, CD (`.github/workflows/cd.yml`):

1. Downloads the served models from the GitHub release `model-latest`.
2. Builds the API and dashboard images and pushes them to GitHub Container Registry (`ghcr.io/taha-nu/leadiq-api`, `leadiq-dashboard`).
3. Updates the Hugging Face Spaces.

The AWS server picks up the new images by itself within 2 minutes (`deploy/update.sh` runs from cron), so GitHub needs no AWS credentials.

**New model → production.** After `dvc repro` (and `src/promote.py` for a canary), run `python src/publish_model.py`, then re-run CD (Actions → CD → Run workflow).

**AWS (AWS Academy Sandbox).** The Sandbox allows EC2, S3, CloudWatch and SNS but not ECS/ECR, and it deletes everything when the lab session ends. Terraform in `infra/terraform` creates:

- an EC2 `t3.small` server (Amazon Linux 2023, pre-made `LabInstanceProfile`) that installs Docker and runs `docker-compose.prod.yml`: API, dashboard, Prometheus and Grafana
- a security group opening ports 8000, 8501 and 3000
- an S3 bucket used as the DVC remote
- CloudWatch alarms (CPU and status check) with SNS email alerts

Each lab session:

```bash
# 1. AWS Academy → Sandbox → Start Lab → AWS Details → AWS CLI: paste into ~/.aws/credentials
aws configure set region us-east-1
# 2. Create everything (the app answers about 5 minutes later)
cd infra/terraform && terraform init && terraform apply
# 3. Optional: version data in S3
dvc remote add -d -f storage $(terraform output -raw dvc_remote) && dvc push
```

`terraform output` prints the dashboard, API docs and Grafana links.

**Hugging Face Spaces (always online).** `deploy/hf_spaces.py` runs the same images as two Docker Spaces, `leadiq-api` and `leadiq-dashboard`. This needs a GitHub secret `HF_TOKEN` (a Hugging Face write token) and a variable `HF_USERNAME`.

## Screenshots

MLflow runs (6 candidates; the best is linked to the registered model):

![MLflow runs](docs/mlflow_runs.png)

Model registry (`leadiq-classifier`, version tags and aliases):

![MLflow registry](docs/mlflow_registry.png)

Top drivers of conversion (SHAP):

![SHAP importance](docs/shap_importance.png)

## Repository layout

```
├── src/                 # pipeline stages, drift report, canary promotion, traffic simulator
├── app/                 # FastAPI scoring API
├── dashboard/           # Streamlit dashboard
├── flows/               # Prefect retraining flow
├── docker/              # Dockerfiles; docker-compose.yml (local) and docker-compose.prod.yml (AWS) at the root
├── deploy/              # server auto-update script, Hugging Face Spaces deploy
├── monitoring/          # Prometheus config + alerts, Grafana dashboard
├── infra/terraform/     # AWS infrastructure (EC2, S3, CloudWatch, SNS)
├── tests/               # pytest (cleaning logic + API)
├── .github/workflows/   # CI (tests, image build, terraform checks) and CD (deploy)
├── dvc.yaml, dvc.lock, params.yaml
└── data/                # raw / processed / feedback data (DVC-tracked)
```
