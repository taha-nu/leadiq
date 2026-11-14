"""Unit tests for the cleaning logic (run with `pytest`)."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evaluate import score_band  # noqa: E402
from preprocess import clean  # noqa: E402

CFG = {"drop_columns": ["Prospect ID", "Tags"], "max_missing_ratio": 0.4,
       "rare_category_threshold": 0.2}


def sample() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Prospect ID": ["a", "b", "c", "d", "e"],
            "Tags": ["x"] * 5,
            "Lead Source": ["Google", "Google", "Select", "Direct", "Google"],
            "Do Not Email": ["Yes", "No", "No", "No", "Yes"],
            "TotalVisits": [1.0, None, 3.0, 4.0, 100.0],
            "Mostly Empty": [None, None, None, "x", None],
            "Converted": [1, 0, 0, 1, 0],
        }
    )


def test_drops_ids_leakage_and_empty_columns():
    out = clean(sample(), CFG, "Converted")
    assert "prospect_id" not in out.columns
    assert "tags" not in out.columns
    assert "mostly_empty" not in out.columns


def test_no_missing_values_after_cleaning():
    out = clean(sample(), CFG, "Converted")
    assert out.isna().sum().sum() == 0


def test_yes_no_becomes_binary():
    out = clean(sample(), CFG, "Converted")
    assert set(out["do_not_email"].unique()) <= {0, 1}


def test_select_placeholder_treated_as_missing():
    out = clean(sample(), CFG, "Converted")
    assert "Select" not in out["lead_source"].values


def test_score_bands():
    assert score_band(0.9, 0.7, 0.4) == "Hot"
    assert score_band(0.5, 0.7, 0.4) == "Warm"
    assert score_band(0.1, 0.7, 0.4) == "Cold"
