"""Send test-set leads to the API, like a sales team would during a demo.

  python src/simulate_traffic.py --n 100 --feedback 0.5

`--feedback` is the share of leads that also get a rep outcome (the true
label), which feeds the retraining loop. Leads come from the TRAINING split
on purpose: feedback becomes training data, and using test leads would leak
the test set into training and inflate the test scores.
"""
import argparse
import random

import pandas as pd
import requests

from common import ROOT, load_params


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--feedback", type=float, default=0.5)
    args = parser.parse_args()

    params = load_params()
    target = params["base"]["target"].lower()
    leads = pd.read_csv(ROOT / params["data"]["processed_dir"] / "train.csv").sample(args.n)

    bands = {"Hot": 0, "Warm": 0, "Cold": 0}
    for _, row in leads.iterrows():
        lead = row.drop(target).to_dict()
        r = requests.post(f"{args.api_url}/predict", json=lead, timeout=60)
        r.raise_for_status()
        result = r.json()
        bands[result["band"]] += 1
        if random.random() < args.feedback:
            requests.post(f"{args.api_url}/feedback", timeout=30,
                          json={"prediction_id": result["prediction_id"], "converted": bool(row[target])})
    print(f"Scored {args.n} leads: {bands}")


if __name__ == "__main__":
    main()
