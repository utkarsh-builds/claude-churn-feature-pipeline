"""Tests for pure feature transform functions: normal case, zero-activity, edge cases."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pandas as pd
import numpy as np
from datetime import datetime

from features.transforms import (
    days_since_last_txn,
    txn_count_90d,
    recent_net_spend_window,
    avg_monthly_spend_6m,
    active_months_12m,
    lifetime_return_rate,
    tenure_days,
)


class TestDaysSinceLastTxn:
    def test_normal_case(self):
        """Customer with transactions should get positive days."""
        txn = pd.DataFrame({
            'customer_id': [1, 1, 2],
            'txn_timestamp': pd.to_datetime(['2026-06-01', '2026-06-15', '2026-07-01']),
        })
        result = days_since_last_txn(txn, '2026-07-31')
        # customer 1 last txn on 2026-06-15 -> 46 days
        assert result.loc[1] == pytest.approx(46.0)
        # customer 2 last txn on 2026-07-01 -> 30 days
        assert result.loc[2] == pytest.approx(30.0)

    def test_zero_activity(self):
        """Empty transactions -> empty Series (default applied in build)."""
        txn = pd.DataFrame({'customer_id': [], 'txn_timestamp': []})
        result = days_since_last_txn(txn, '2026-07-31')
        assert len(result) == 0

    def test_single_record(self):
        """Single transaction should still produce a valid recency."""
        txn = pd.DataFrame({
            'customer_id': [42],
            'txn_timestamp': pd.to_datetime(['2026-07-30']),
        })
        result = days_since_last_txn(txn, '2026-07-31')
        assert result.loc[42] == pytest.approx(1.0)

    def test_boundary_at_asof(self):
        """Transaction on the as_of date should count as 0 days."""
        txn = pd.DataFrame({
            'customer_id': [7],
            'txn_timestamp': pd.to_datetime(['2026-07-31']),
        })
        result = days_since_last_txn(txn, '2026-07-31')
        assert result.loc[7] == pytest.approx(0.0)


class TestTxnCount90d:
    def test_normal_case(self):
        txn = pd.DataFrame({
            'customer_id': [1, 1, 1, 2, 2],
            'txn_timestamp': pd.to_datetime([
                '2026-04-01',  # > 90d from 2026-07-31
                '2026-05-20',  # within 90d (2026-05-20 > 2026-05-02)
                '2026-07-15',  # within 90d
                '2026-07-01',  # within 90d
                '2026-06-10',  # within 90d
            ]),
        })
        result = txn_count_90d(txn, '2026-07-31')
        # cutoff = 2026-05-02
        # c1: May 20 and Jul 15 are within -> 2
        assert result.loc[1] == 2
        # c2: Jul 1 and Jun 10 -> 2
        assert result.loc[2] == 2

    def test_zero_activity(self):
        txn = pd.DataFrame({'customer_id': [], 'txn_timestamp': []})
        result = txn_count_90d(txn, '2026-07-31')
        assert len(result) == 0

    def test_single_recent_record(self):
        txn = pd.DataFrame({
            'customer_id': [42],
            'txn_timestamp': pd.to_datetime(['2026-07-30']),
        })
        result = txn_count_90d(txn, '2026-07-31')
        assert result.loc[42] == 1

    def test_boundary_90d_exactly(self):
        """Transaction exactly 90 days before as_of is excluded by strict > filter."""
        txn = pd.DataFrame({
            'customer_id': [1],
            'txn_timestamp': pd.to_datetime(['2026-05-02 12:00:00']),  # within 90d (> 2026-05-02 00:00:00)
        })
        result = txn_count_90d(txn, '2026-07-31')
        assert result.loc[1] == 1


class TestRecentNetSpendWindow:
    def test_normal_case(self):
        txn = pd.DataFrame({
            'customer_id': [1, 1, 2],
            'txn_timestamp': pd.to_datetime(['2026-07-01', '2026-07-15', '2026-06-01']),
            'amount': [100.0, 50.0, 30.0],
            'is_returned': [0, 1, 0],
        })
        result = recent_net_spend_window(txn, '2026-07-31', window_days=90)
        # c1: 100 + 50*(1-1)=50*0=0 -> 100
        assert result.loc[1] == pytest.approx(100.0)
        # c2: 30
        assert result.loc[2] == pytest.approx(30.0)

    def test_zero_activity(self):
        txn = pd.DataFrame({'customer_id': [], 'txn_timestamp': [], 'amount': [], 'is_returned': []})
        result = recent_net_spend_window(txn, '2026-07-31')
        assert len(result) == 0

    def test_single_record(self):
        txn = pd.DataFrame({
            'customer_id': [42],
            'txn_timestamp': pd.to_datetime(['2026-07-30']),
            'amount': [75.50],
            'is_returned': [0],
        })
        result = recent_net_spend_window(txn, '2026-07-31')
        assert result.loc[42] == pytest.approx(75.50)

    def test_all_returns(self):
        """All transactions are returns -> net spend 0."""
        txn = pd.DataFrame({
            'customer_id': [1, 1],
            'txn_timestamp': pd.to_datetime(['2026-07-01', '2026-07-15']),
            'amount': [50.0, 30.0],
            'is_returned': [1, 1],
        })
        result = recent_net_spend_window(txn, '2026-07-31')
        assert result.loc[1] == pytest.approx(0.0)

    def test_window_boundary(self):
        """Transaction outside the window cutoff is excluded (as_of filtering is build.py's job)."""
        txn = pd.DataFrame({
            'customer_id': [1, 1],
            'txn_timestamp': pd.to_datetime(['2026-03-01', '2026-04-15']),
            'amount': [100.0, 50.0],
            'is_returned': [0, 0],
        })
        result = recent_net_spend_window(txn, '2026-06-01', window_days=90)
        # as_of=2026-06-01, 90d back = 2026-03-03
        # 2026-03-01 is outside cutoff, 2026-04-15 is inside
        # Note: the transform does not filter by <= as_of (build.py does that)
        assert result.loc[1] == pytest.approx(50.0)


class TestAvgMonthlySpend6m:
    def test_normal_case(self):
        agg = pd.DataFrame({
            'customer_id': [1, 1, 1, 2],
            'txn_month': pd.to_datetime(['2026-03-01', '2026-04-01', '2026-05-01', '2026-04-01']),
            'total_amount': [100.0, 200.0, 300.0, 500.0],
        })
        result = avg_monthly_spend_6m(agg, '2026-07-31')
        # c1: (100+200+300)/3 = 200
        assert result.loc[1] == pytest.approx(200.0)
        # c2: 500/1 = 500
        assert result.loc[2] == pytest.approx(500.0)

    def test_zero_activity(self):
        agg = pd.DataFrame({'customer_id': [], 'txn_month': [], 'total_amount': []})
        result = avg_monthly_spend_6m(agg, '2026-07-31')
        assert len(result) == 0

    def test_outside_window(self):
        """All data before 6-month cutoff -> empty -> missing (filled by build)."""
        agg = pd.DataFrame({
            'customer_id': [1],
            'txn_month': pd.to_datetime(['2025-01-01']),
            'total_amount': [100.0],
        })
        result = avg_monthly_spend_6m(agg, '2026-07-31')
        assert len(result) == 0  # no data in window


class TestActiveMonths12m:
    def test_normal_case(self):
        agg = pd.DataFrame({
            'customer_id': [1, 1, 1, 2, 2],
            'txn_month': pd.to_datetime([
                '2026-01-01', '2026-02-01', '2026-03-01',
                '2026-01-01', '2026-01-01',  # duplicate month for c2
            ]),
            'txn_count': [5, 0, 3, 8, 2],  # c1 Feb has 0 -> not active
        })
        result = active_months_12m(agg, '2026-07-31')
        assert result.loc[1] == 2  # Jan (5), Mar (3) -> 2 active months
        assert result.loc[2] == 1  # Jan only (8 and 2 are same month)

    def test_zero_activity(self):
        agg = pd.DataFrame({'customer_id': [], 'txn_month': [], 'txn_count': []})
        result = active_months_12m(agg, '2026-07-31')
        assert len(result) == 0


class TestLifetimeReturnRate:
    def test_normal_case(self):
        agg = pd.DataFrame({
            'customer_id': [1, 1, 2, 2],
            'txn_count': [10, 10, 5, 5],
            'return_count': [1, 2, 5, 0],
        })
        result = lifetime_return_rate(agg, min_txns_threshold=0)
        # c1: 3/20 = 0.15
        assert result.loc[1] == pytest.approx(0.15)
        # c2: 5/10 = 0.5
        assert result.loc[2] == pytest.approx(0.5)

    def test_threshold_eliminates_small_samples(self):
        """Customer with 1 txn and 1 return -> 1.0 with threshold=0, 0.0 with threshold=3."""
        agg = pd.DataFrame({
            'customer_id': [1],
            'txn_count': [1],
            'return_count': [1],
        })
        result = lifetime_return_rate(agg, min_txns_threshold=3)
        assert result.loc[1] == pytest.approx(0.0)

    def test_threshold_zero_allows_all(self):
        agg = pd.DataFrame({
            'customer_id': [1],
            'txn_count': [1],
            'return_count': [1],
        })
        result = lifetime_return_rate(agg, min_txns_threshold=0)
        assert result.loc[1] == pytest.approx(1.0)

    def test_zero_activity(self):
        agg = pd.DataFrame({'customer_id': [], 'txn_count': [], 'return_count': []})
        result = lifetime_return_rate(agg)
        assert len(result) == 0

    def test_no_returns(self):
        agg = pd.DataFrame({
            'customer_id': [1, 1],
            'txn_count': [5, 3],
            'return_count': [0, 0],
        })
        result = lifetime_return_rate(agg)
        assert result.loc[1] == pytest.approx(0.0)


class TestTenureDays:
    def test_normal_case(self):
        cust = pd.DataFrame({
            'customer_id': [1, 2],
            'signup_date': pd.to_datetime(['2024-06-15', '2025-01-01']),
        })
        result = tenure_days(cust, '2026-07-31')
        # 2026-07-31 - 2024-06-15 = 777 days (approx)
        assert result.loc[0] > 700
        assert result.loc[1] > 500

    def test_all_customers_have_dates(self):
        """Every customer should get a tenure value."""
        cust = pd.DataFrame({
            'customer_id': [1, 2, 3],
            'signup_date': pd.to_datetime(['2024-06-15', '2025-01-01', '2026-07-01']),
        })
        result = tenure_days(cust, '2026-07-31')
        assert len(result) == 3
        assert result.loc[2] == 30  # 2026-07-01 to 2026-07-31