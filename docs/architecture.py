"""Draws docs/architecture.png (cloud architecture diagram).

Needs Graphviz installed and `pip install diagrams`. Run from the repo root:
    python docs/architecture.py
"""
from diagrams import Cluster, Diagram, Edge
from diagrams.aws.compute import EC2ContainerRegistry, Fargate
from diagrams.aws.integration import SimpleNotificationServiceSns
from diagrams.aws.management import CloudwatchAlarm, CloudwatchLogs
from diagrams.aws.security import IdentityAndAccessManagementIamRole
from diagrams.aws.storage import SimpleStorageServiceS3Bucket
from diagrams.generic.database import SQL
from diagrams.onprem.ci import GithubActions
from diagrams.onprem.client import Client, User, Users
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

    with Cluster("GitHub"):
        repo = Github("leadiq repo")
        ci = GithubActions("CI\npytest, docker build,\nterraform validate")
        cd = GithubActions("CD\nbuild + push + deploy")

    with Cluster("Training + monitoring (docker compose / dev machine)"):
        pipeline = Python("DVC pipeline\nvalidate > preprocess > train\n> evaluate > register > export")
        mlflow = Mlflow("MLflow\nruns + model registry")
        prefect = Python("Prefect\nretrain flow")
        prometheus = Prometheus("Prometheus\n+ alert rules")
        grafana = Grafana("Grafana")

    with Cluster("AWS (us-east-1), built with Terraform"):
        s3 = SimpleStorageServiceS3Bucket("S3\nDVC remote\n(data + models)")
        ecr = EC2ContainerRegistry("ECR\nleadiq-api\nleadiq-dashboard")
        role = IdentityAndAccessManagementIamRole("IAM OIDC role\n(GitHub deploy)")

        with Cluster("ECS Fargate service (one task)"):
            fargate = Fargate("Fargate task")
            api = Fastapi("Scoring API :8000\n/predict /feedback\n/metrics")
            dashboard = Python("Streamlit\ndashboard :8501")
            db = SQL("SQLite\npredictions +\nfeedback")

        logs = CloudwatchLogs("CloudWatch Logs")
        alarm = CloudwatchAlarm("CloudWatch\nCPU alarm")
        sns = SimpleNotificationServiceSns("SNS\nemail alert")

    llm = Client("LLM API\n(follow-up text)")

    # CI/CD
    developer >> Edge(label="git push") >> repo >> ci >> Edge(label="on success") >> cd
    cd >> Edge(label="OIDC login") >> role
    cd >> Edge(label="dvc pull models") >> s3
    cd >> Edge(label="push images") >> ecr
    cd >> Edge(label="update service") >> fargate
    ecr >> Edge(label="pull images", style="dashed") >> fargate

    # Serving
    sales >> dashboard >> Edge(label="localhost:8000") >> api
    client >> Edge(label="POST /predict") >> api
    api >> db
    api >> Edge(label="hot leads", style="dashed") >> llm
    fargate >> Edge(label="logs") >> logs
    fargate >> Edge(label="CPU") >> alarm >> sns

    # Training loop
    pipeline >> Edge(label="params, metrics,\nmodels") >> mlflow
    pipeline >> Edge(label="dvc push") >> s3
    prefect >> Edge(label="GET /feedback/export") >> api
    prefect >> Edge(label="dvc repro") >> pipeline

    # Monitoring
    prometheus >> Edge(label="scrape /metrics", style="dashed") >> api
    grafana >> prometheus
