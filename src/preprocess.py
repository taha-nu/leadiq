"""Stage 2: clean the raw data and split it into train / test sets."""
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from common import ROOT, load_params, write_json


def clean(df: pd.DataFrame, cfg: dict, target: str) -> pd.DataFrame:
    df = df.copy()
    # "Select" is the website form's default option, i.e. the lead left it blank
    df = df.replace("Select", np.nan)
    df = df.drop(columns=[c for c in cfg["drop_columns"] if c in df.columns])

    # Drop columns that are mostly empty
    missing = df.isna().mean()
    df = df.drop(columns=missing[missing > cfg["max_missing_ratio"]].index.tolist())

    # Yes/No flags -> 1/0
    for col in df.columns:
        values = set(df[col].dropna().unique())
        if values and values <= {"Yes", "No"}:
            df[col] = (df[col] == "Yes").astype(int)

    num_cols = [c for c in df.select_dtypes(include="number").columns if c != target]
    cat_cols = df.select_dtypes(exclude="number").columns.tolist()

    for col in num_cols:
        # Cap extreme outliers at the 99th percentile, then fill gaps with the median
        df[col] = df[col].clip(upper=df[col].quantile(0.99)).fillna(df[col].median())

    for col in cat_cols:
        df[col] = df[col].fillna("Unknown")
        share = df[col].value_counts(normalize=True)
        rare = share[share < cfg["rare_category_threshold"]].index
        df[col] = df[col].where(~df[col].isin(rare), "Other")

    # Make column names code-friendly
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    return df


def main() -> None:
    params = load_params()
    cfg = params["preprocess"]
    target = params["base"]["target"]

    raw = pd.read_csv(ROOT / params["data"]["raw"])
    df = clean(raw, cfg, target)
    target_col = target.lower()

    train, test = train_test_split(
        df,
        test_size=cfg["test_size"],
        stratify=df[target_col],
        random_state=params["base"]["random_state"],
    )
    out = ROOT / params["data"]["processed_dir"]
    out.mkdir(parents=True, exist_ok=True)
    # Always use "\n" line endings so the files (and their DVC hashes) are
    # identical on Windows, Linux and Mac
    train.to_csv(out / "train.csv", index=False, lineterminator="\n")
    test.to_csv(out / "test.csv", index=False, lineterminator="\n")

    write_json(
        {
            "rows_train": len(train),
            "rows_test": len(test),
            "features": [c for c in df.columns if c != target_col],
        },
        "reports/preprocess.json",
    )
    print(f"Processed: {len(train)} train rows, {len(test)} test rows, {df.shape[1] - 1} features")


if __name__ == "__main__":
    main()
