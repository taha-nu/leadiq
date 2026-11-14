"""Stage 1: validate the raw lead data with Pandera before anything else runs.

Fails the pipeline (non-zero exit) if the data breaks the schema.
"""
import sys

import pandas as pd
import pandera.pandas as pa

from common import ROOT, file_md5, load_params, write_json

SCHEMA = pa.DataFrameSchema(
    {
        "Prospect ID": pa.Column(str, unique=True),
        "Lead Origin": pa.Column(str, nullable=False),
        "Lead Source": pa.Column(str, nullable=True),
        "Do Not Email": pa.Column(str, pa.Check.isin(["Yes", "No"])),
        "Converted": pa.Column(int, pa.Check.isin([0, 1])),
        "TotalVisits": pa.Column(float, pa.Check.ge(0), nullable=True),
        "Total Time Spent on Website": pa.Column(int, pa.Check.ge(0)),
        "Page Views Per Visit": pa.Column(float, pa.Check.ge(0), nullable=True),
        "Last Activity": pa.Column(str, nullable=True),
        "What is your current occupation": pa.Column(str, nullable=True),
    },
    checks=[pa.Check(lambda df: len(df) >= 1000, error="too few rows")],
    strict=False,
    coerce=False,
)


def main() -> None:
    params = load_params()
    raw_path = params["data"]["raw"]
    df = pd.read_csv(ROOT / raw_path)

    report = {
        "rows": int(len(df)),
        "columns": int(df.shape[1]),
        "duplicate_rows": int(df.duplicated().sum()),
        "conversion_rate": round(float(df[params["base"]["target"]].mean()), 4),
        "raw_md5": file_md5(raw_path),
    }
    try:
        SCHEMA.validate(df, lazy=True)
        report["status"] = "passed"
    except pa.errors.SchemaErrors as e:
        report["status"] = "failed"
        report["errors"] = e.failure_cases.astype(str).head(50).to_dict("records")

    write_json(report, "reports/validation.json")
    print(f"Validation {report['status']}: {report['rows']} rows, {report['columns']} columns")
    if report["status"] != "passed":
        sys.exit(1)


if __name__ == "__main__":
    main()
