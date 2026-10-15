"""Tests for the feature store: version registration, retrieval, and lifecycle."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pandas as pd
import numpy as np
from datetime import datetime

from feature_store import store


class TestFeatureStore:
    """Prove every versioned feature is stored and independently retrievable."""

    def setup_method(self):
        # Use a unique test feature name to avoid collisions
        self.test_feat = f'_test_feature_{id(self)}'
        self._cleanup_versions()

    def teardown_method(self):
        self._cleanup_versions()

    def _cleanup_versions(self):
        """Remove any test versions from prior runs."""
        conn = store._get_connection()
        try:
            conn.execute("DELETE FROM feature_registry WHERE feature_name = ?", (self.test_feat,))
            conn.commit()
        finally:
            conn.close()

    def _make_values(self, value_col=None, n=5):
        """Helper to create a standard values DataFrame."""
        if value_col is None:
            value_col = self.test_feat
        return pd.DataFrame({
            'customer_id': list(range(1, n + 1)),
            value_col: [float(i * 10) for i in range(n)],
            'as_of_date': pd.to_datetime(['2026-07-31'] * n),
        })

    def test_register_and_get_latest(self):
        """Register v1, then get_latest should return v1."""
        df_v1 = self._make_values()
        v1 = store.register_version(
            feature_name=self.test_feat,
            values_df=df_v1,
            description='v1 test',
            source_columns='test:col',
            transform_summary='test',
            business_rationale='testing',
            parameters={'p': 1},
        )
        assert v1 == 1

        latest_v, latest_df = store.get_latest(self.test_feat)
        assert latest_v == 1
        assert len(latest_df) == 5
        assert list(latest_df.columns) == ['customer_id', self.test_feat, 'as_of_date']

    def test_register_two_versions(self):
        """Register v1 and v2; get_latest returns v2, both independently retrievable."""
        df_v1 = self._make_values()
        v1 = store.register_version(
            feature_name=self.test_feat,
            values_df=df_v1,
            description='v1 test',
            source_columns='test:col',
            transform_summary='test v1',
            business_rationale='v1 rationale',
            parameters={'p': 1},
        )
        df_v2 = self._make_values(n=5)
        df_v2[self.test_feat] = [float(i * 20) for i in range(5)]
        v2 = store.register_version(
            feature_name=self.test_feat,
            values_df=df_v2,
            description='v2 test',
            source_columns='test:col',
            transform_summary='test v2',
            business_rationale='v2 rationale',
            parameters={'p': 2},
        )
        assert v2 == 2
        assert v2 > v1

        # get_latest returns v2
        latest_v, latest_df = store.get_latest(self.test_feat)
        assert latest_v == 2
        assert latest_df[self.test_feat].iloc[0] == pytest.approx(0.0)  # v2 value

        # get_version retrieves each independently
        df_v1_retrieved = store.get_version(self.test_feat, 1)
        assert df_v1_retrieved is not None
        assert df_v1_retrieved[self.test_feat].iloc[1] == pytest.approx(10.0)  # v1 value

        df_v2_retrieved = store.get_version(self.test_feat, 2)
        assert df_v2_retrieved is not None
        assert df_v2_retrieved[self.test_feat].iloc[1] == pytest.approx(20.0)  # v2 value

    def test_is_latest_consistency(self):
        """After registering v2, is_latest for v1 is 0 and for v2 is 1."""
        df_v1 = self._make_values()
        store.register_version(
            feature_name=self.test_feat, values_df=df_v1,
            description='v1', source_columns='x', transform_summary='x',
            business_rationale='x', parameters={},
        )
        df_v2 = self._make_values()
        store.register_version(
            feature_name=self.test_feat, values_df=df_v2,
            description='v2', source_columns='x', transform_summary='x',
            business_rationale='x', parameters={},
        )

        vlist = store.list_versions(self.test_feat)
        v1_row = vlist[vlist['version'] == 1].iloc[0]
        v2_row = vlist[vlist['version'] == 2].iloc[0]
        assert v1_row['is_latest'] == 0
        assert v2_row['is_latest'] == 1

    def test_list_versions_returns_distinct_paths(self):
        """Each version has a distinct parquet_path, all exist on disk."""
        df_v1 = self._make_values()
        store.register_version(
            feature_name=self.test_feat, values_df=df_v1,
            description='v1', source_columns='x', transform_summary='x',
            business_rationale='x', parameters={},
        )
        df_v2 = self._make_values()
        store.register_version(
            feature_name=self.test_feat, values_df=df_v2,
            description='v2', source_columns='x', transform_summary='x',
            business_rationale='x', parameters={},
        )

        vlist = store.list_versions(self.test_feat)
        assert len(vlist) == 2

        paths = vlist['parquet_path'].tolist()
        assert len(paths) == len(set(paths)), "parquet_path values must be unique"

        # Verify files exist
        store_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for p in paths:
            abs_path = os.path.join(store_root, p)
            assert os.path.exists(abs_path), f"Parquet file missing: {abs_path}"

    def test_get_version_nonexistent_returns_none(self):
        """Requesting a version that doesn't exist should return None."""
        df = self._make_values()
        store.register_version(
            feature_name=self.test_feat, values_df=df,
            description='v1', source_columns='x', transform_summary='x',
            business_rationale='x', parameters={},
        )
        assert store.get_version(self.test_feat, 99) is None
        assert store.get_version('nonexistent_feature', 1) is None