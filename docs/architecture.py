"""Draws docs/architecture.png (cloud architecture diagram).

Needs Graphviz installed and `pip install diagrams`. Run from the repo root:
    python docs/architecture.py
"""
from diagrams import Cluster, Diagram, Edge
from diagrams.aws.compute import EC2
from diagrams.aws.integration import SimpleNotificationServiceSns
from diagrams.aws.management import CloudwatchAlarm
from diagrams.aws.security import IdentityAndAccessManagementIamRole
from diagrams.aws.storage import SimpleStorageServiceS3Bucket
from diagrams.generic.database import SQL
from diagrams.onprem.ci import GithubActions
from diagrams.onprem.client import Client, User, Users
from diagrams.onprem.container import Docker
from diagrams.onprem.mlops import Mlflow
from diagrams.onprem.monitoring import Grafana, Prometheus
from diagrams.onprem.vcs import Github
from diagrams.programming.framework import Fastapi
from diagrams.programming.language import Python

# Curved lines keep each edge label next to its arrow
graph_attr = {"fontsize": "22", "pad": "0.4", "nodesep": "0.7", "ranksep": "1.1", "labelloc": "t",
              "splines": "spline"}
node_attr = {"fontsize": "12"}

with Diagram("LeadIQ cloud architecture", filename="docs/architecture", show=False,
             direction="LR", graph_attr=graph_attr, node_attr=node_attr):
    developer = User("Developer")
    sales = Users("Sales reps\n(browser)")
    client = Client("API client")

    with Cluster("Dev machine"):
        pipeline = Python("DVC pipeline\nvalidate > preprocess > train\n> evaluate > register > export")
        mlflow = Mlflow("MLflow\nruns + model registry")
        prefect = Python("Prefect\nretrain flow")

    with Cluster("GitHub"):
        repo = Github("leadiq repo")
        release = Github("Release\nmodel-latest\n(served models)")
        ci = GithubActions("CI\npytest, docker build,\nterraform validate")
        cd = GithubActions("CD\nbuild + push images")
        ghcr = Docker("GHCR\nleadiq-api\nleadiq-dashboard")

    with Cluster("AWS Academy Sandbox (us-east-1), built with Terraform"):
        s3 = SimpleStorageServiceS3Bucket("S3\nDVC remote")
        role = IdentityAndAccessManagementIamRole("LabInstanceProfile")
        alarm = CloudwatchAlarm("CloudWatch alarms\nCPU + status check")
        sns = SimpleNotificationServiceSns("SNS\nemail alert")

        with Cluster("EC2 t3.small: docker compose"):
            ec2 = EC2("EC2 server\ncron: pull new\nimages every 2 min")
            api = Fastapi("Scoring API :8000\n/predict /feedback\n/metrics")
            dashboard = Python("Streamlit\ndashboard :8501")
            db = SQL("SQLite\npredictions +\nfeedback")
            prometheus = Prometheus("Prometheus\n+ alert rules")
            grafana = Grafana("Grafana :3000")

    with Cluster("Hugging Face Spaces (always online)"):
        hf_api = Fastapi("leadiq-api")
        hf_dash = Python("leadiq-dashboard")

    llm = Client("LLM API\n(follow-up text)")

    # Training and model publishing
    pipeline >> Edge(label="params, metrics,\nmodels") >> mlflow
    pipeline >> Edge(label="dvc push") >> s3
    pipeline >> Edge(label="publish_model.py") >> release
    prefect >> Edge(label="dvc repro") >> pipeline
    prefect >> Edge(label="GET /feedback/export", style="dashed") >> api

    # CI/CD
    developer >> Edge(label="git push") >> repo >> ci >> Edge(label="on success") >> cd
    release >> Edge(label="models") >> cd
    cd >> Edge(label="push images") >> ghcr
    ghcr >> Edge(label="docker pull") >> ec2
    cd >> Edge(label="update Spaces") >> hf_api
    cd >> hf_dash
    ghcr >> Edge(label="FROM image", style="dashed") >> hf_api

    # Serving on AWS
    role >> Edge(style="dashed") >> ec2
    sales >> dashboard >> Edge(label="api:8000") >> api
    client >> Edge(label="POST /predict") >> api
    api >> db
    api >> Edge(label="hot leads", style="dashed") >> llm
    prometheus >> Edge(label="scrape /metrics") >> api
    grafana >> prometheus
    ec2 >> Edge(label="metrics") >> alarm >> sns
    hf_dash >> hf_api
