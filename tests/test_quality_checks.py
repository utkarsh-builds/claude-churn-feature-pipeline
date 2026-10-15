"""Tests for quality checks: each check fires on bad input, passes on clean input."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pandas as pd
import numpy as np

from features.quality_checks import (
    check_no_unexpected_nulls,
    check_zero_activity_defaults_applied,
    check_value_bounds,
    check_row_count_matches,
    QualityCheckError,
)


class TestCheckNoUnexpectedNulls:
    def test_passes_on_clean(self):
        df = pd.DataFrame({'a': [1.0, 2.0], 'b': [3.0, 4.0]})
        result = check_no_unexpected_nulls(df, ['a', 'b'])
        assert 'PASS' in result

    def test_fires_on_nulls(self):
        df = pd.DataFrame({'a': [1.0, None], 'b': [3.0, 4.0]})
        with pytest.raises(QualityCheckError, match="Unexpected nulls"):
            check_no_unexpected_nulls(df, ['a', 'b'])


class TestCheckZeroActivityDefaultsApplied:
    def test_passes_when_no_nulls(self):
        df = pd.DataFrame({'days_since_last_txn': [-1.0, 15.0, 30.0]})
        result = check_zero_activity_defaults_applied(df, [('days_since_last_txn', -1.0)])
        assert 'PASS' in result

    def test_fires_when_nulls_exist(self):
        df = pd.DataFrame({'days_since_last_txn': [np.nan, 15.0, 30.0]})
        with pytest.raises(QualityCheckError, match="default -1.0 not applied"):
            check_zero_activity_defaults_applied(df, [('days_since_last_txn', -1.0)])


class TestCheckValueBounds:
    def test_passes_clean(self):
        df = pd.DataFrame({
            'recent_net_spend_window': [0.0, 100.0, 500.0],
            'lifetime_return_rate': [0.0, 0.5, 1.0],
        })
        assert 'PASS' in check_value_bounds(df)

    def test_fires_negative_spend(self):
        df = pd.DataFrame({
            'recent_net_spend_window': [-5.0, 100.0],
        })
        with pytest.raises(QualityCheckError, match="negative"):
            check_value_bounds(df)

    def test_fires_return_rate_above_1(self):
        df = pd.DataFrame({
            'recent_net_spend_window': [0.0],
            'lifetime_return_rate': [1.5],
        })
        with pytest.raises(QualityCheckError, match="> 1"):
            check_value_bounds(df)

    def test_passes_when_columns_missing(self):
        """Check should not error if the feature columns are absent from DataFrame."""
        df = pd.DataFrame({'some_other_col': [1.0]})
        # Should still pass because missing columns are skipped
        assert 'PASS' in check_value_bounds(df)


class TestCheckRowCountMatches:
    def test_passes_when_match(self):
        df = pd.DataFrame({'a': [1, 2, 3]})
        assert 'PASS' in check_row_count_matches(df, 3)

    def test_fires_on_mismatch(self):
        df = pd.DataFrame({'a': [1, 2, 3]})
        with pytest.raises(QualityCheckError, match="Row count mismatch"):
            check_row_count_matches(df, 5)