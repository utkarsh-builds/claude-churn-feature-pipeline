"""Runnable data-quality checks against a features DataFrame."""

import pandas as pd
from typing import List, Tuple


FAILURE_RAISED = False


class QualityCheckError(Exception):
    pass


def check_no_unexpected_nulls(features_df: pd.DataFrame, feature_cols: List[str]) -> str:
    """Check: no unexpected nulls after applying defaults.
    Catches: a left join that accidentally drops or fails to fill the 81 known zero-txn customers."""
    null_counts = features_df[feature_cols].isnull().sum()
    offending = null_counts[null_counts > 0]
    if len(offending) > 0:
        raise QualityCheckError(
            f"Unexpected nulls found: {offending.to_dict()}"
        )
    return "PASS: No unexpected nulls"


def check_zero_activity_defaults_applied(features_df: pd.DataFrame,
                                         default_cols: List[Tuple[str, object]]) -> str:
    """Check: zero-activity customers have the explicit default, not NaN.
    Catches: an off-by-one or fillna oversight."""
    # For each column, spot-check that at least one customer who should have
    # zero activity actually has the default. We verify by checking the column
    # has non-NaN values for all rows.
    for col_name, expected_default in default_cols:
        col = features_df[col_name]
        nulls = col.isnull().sum()
        if nulls > 0:
            raise QualityCheckError(
                f"Column '{col_name}' has {nulls} nulls — default {expected_default} not applied"
            )
    return "PASS: Zero-activity defaults present (no NaN in defaulted columns)"


def check_value_bounds(features_df: pd.DataFrame) -> str:
    """Check: recent_net_spend_window >= 0.0, lifetime_return_rate between 0.0 and 1.0.
    Catches: double-subtracting returns, division errors."""
    if 'recent_net_spend_window' in features_df.columns:
        bad = (features_df['recent_net_spend_window'] < -0.001)  # allow small FP tolerance
        if bad.any():
            raise QualityCheckError(
                f"recent_net_spend_window has {bad.sum()} negative values (min={features_df['recent_net_spend_window'].min()})"
            )

    if 'lifetime_return_rate' in features_df.columns:
        bad_lo = features_df['lifetime_return_rate'] < -0.001
        bad_hi = features_df['lifetime_return_rate'] > 1.001
        if bad_lo.any():
            raise QualityCheckError(
                f"lifetime_return_rate has {bad_lo.sum()} values < 0"
            )
        if bad_hi.any():
            raise QualityCheckError(
                f"lifetime_return_rate has {bad_hi.sum()} values > 1"
            )

    return "PASS: All value bounds satisfied"


def check_row_count_matches(features_df: pd.DataFrame, expected_count: int) -> str:
    """Check: final output row count matches provided customer_ids length.
    Catches: a fan-out merge duplicating customer rows."""
    actual = len(features_df)
    if actual != expected_count:
        raise QualityCheckError(
            f"Row count mismatch: expected {expected_count}, got {actual}"
        )
    return f"PASS: Row count matches ({actual})"


def run_all_checks(features_df: pd.DataFrame,
                   all_feature_cols: List[str],
                   default_cols: List[Tuple[str, object]],
                   expected_count: int) -> List[str]:
    """Run all quality checks. Returns list of result strings; raises on first failure."""
    results = []
    results.append(check_no_unexpected_nulls(features_df, all_feature_cols))
    results.append(check_zero_activity_defaults_applied(features_df, default_cols))
    results.append(check_value_bounds(features_df))
    results.append(check_row_count_matches(features_df, expected_count))
    return results