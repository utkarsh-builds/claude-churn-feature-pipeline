"""Parity test: training path and scoring path produce identical features."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pandas as pd
import numpy as np

from features import build


class TestParity:
    """Prove that training-path (batch, many customers) and scoring-path
    (single customer, same as_of) produce identical feature values."""

    def test_single_customer_parity(self):
        """Features for customer 42 via batch path and single-customer path must match."""
        as_of = '2026-07-31'

        # "Training" path: build_features with customer_ids=None -> all 1500
        batch_df = build.build_features(as_of=as_of)
        batch_42 = batch_df[batch_df['customer_id'] == 42].iloc[0]

        # "Scoring" path: build_features with specific customer_ids
        score_df = build.build_features(as_of=as_of, customer_ids=[42])
        score_42 = score_df.iloc[0]

        # Compare all feature columns
        feat_cols = [c for c in batch_df.columns if c != 'customer_id']
        for col in feat_cols:
            assert batch_42[col] == score_42[col], (
                f"Mismatch on {col}: batch={batch_42[col]}, score={score_42[col]}"
            )

    def test_multiple_customer_parity(self):
        """Features for a set of customers via batch vs filtered path must match."""
        as_of = '2026-07-31'
        test_ids = [7, 42, 101, 777, 1500]

        batch_df = build.build_features(as_of=as_of)
        # Ensure the customer_ids parameter doesn't reorder or alter values
        score_df = build.build_features(as_of=as_of, customer_ids=test_ids)

        feat_cols = [c for c in batch_df.columns if c != 'customer_id']
        for cid in test_ids:
            batch_row = batch_df[batch_df['customer_id'] == cid].iloc[0]
            score_row = score_df[score_df['customer_id'] == cid].iloc[0]
            for col in feat_cols:
                assert batch_row[col] == score_row[col], (
                    f"Mismatch for customer {cid}, {col}: batch={batch_row[col]}, score={score_row[col]}"
                )

    def test_zero_activity_customer_parity(self):
        """Customers with no transactions should have consistent default values."""
        as_of = '2026-07-31'

        # Find a customer with zero transactions
        df = build.build_features(as_of=as_of)
        zero_activity = df[df['days_since_last_txn'] == -1.0]

        assert len(zero_activity) > 0, "Expected at least one zero-activity customer"

        # Check defaults
        for _, row in zero_activity.iterrows():
            assert row['days_since_last_txn'] == -1.0
            assert row['txn_count_90d'] == 0
            assert row['recent_net_spend_window'] == 0.0
            assert row['avg_monthly_spend_6m'] == 0.0
            assert row['active_months_12m'] == 0
            assert row['lifetime_return_rate'] == 0.0
            # tenure_days should be non-zero for these customers
            assert row['tenure_days'] >= 0

        # Verify via scoring path too
        score_df = build.build_features(as_of=as_of, customer_ids=zero_activity['customer_id'].tolist())
        for _, row in score_df.iterrows():
            assert row['days_since_last_txn'] == -1.0
            assert row['txn_count_90d'] == 0