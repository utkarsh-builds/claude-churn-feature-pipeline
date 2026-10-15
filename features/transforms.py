"""Pure feature transform functions. Each is independent of I/O, takes data as DataFrames."""

import numpy as np
import pandas as pd


def days_since_last_txn(transactions_df, as_of):
    """Days since customer's last transaction. -1.0 if never transacted."""
    if not len(transactions_df):
        return pd.Series([], dtype=float, name='days_since_last_txn')

    last = transactions_df.groupby('customer_id')['txn_timestamp'].max()
    delta = pd.to_datetime(as_of) - last
    # Use total_seconds division to avoid pandas flooring behavior on negative timedeltas
    result = (delta.dt.total_seconds() / 86400.0).astype(float)
    return result


def txn_count_90d(transactions_df, as_of):
    """Transaction count in trailing 90 days. 0 if never transacted."""
    if not len(transactions_df):
        return pd.Series([], dtype=int, name='txn_count_90d')

    cutoff = pd.to_datetime(as_of) - pd.Timedelta(days=90)
    recent = transactions_df[transactions_df['txn_timestamp'] > cutoff]
    counts = recent.groupby('customer_id').size()
    return counts

    cutoff = pd.to_datetime(as_of) - pd.Timedelta(days=90)
    recent = transactions_df[transactions_df['txn_timestamp'] > cutoff]
    counts = recent.groupby('customer_id').size()
    return counts


def recent_net_spend_window(transactions_df, as_of, window_days=90):
    """Net spend (amount * (1 - is_returned)) in trailing window. 0.0 if never transacted."""
    if not len(transactions_df):
        return pd.Series([], dtype=float, name='recent_net_spend_window')

    cutoff = pd.to_datetime(as_of) - pd.Timedelta(days=window_days)
    recent = transactions_df[transactions_df['txn_timestamp'] > cutoff].copy()
    recent['net'] = recent['amount'] * (1 - recent['is_returned'])
    spend = recent.groupby('customer_id')['net'].sum()
    return spend


def avg_monthly_spend_6m(monthly_agg_df, as_of):
    """Average monthly spend over trailing 6 months. 0.0 if no data."""
    if not len(monthly_agg_df):
        return pd.Series([], dtype=float, name='avg_monthly_spend_6m')

    as_of_dt = pd.to_datetime(as_of)
    cutoff = as_of_dt - pd.DateOffset(months=6)
    recent = monthly_agg_df[monthly_agg_df['txn_month'] >= cutoff].copy()
    # Exclude months strictly after as_of (in case parquet has future data)
    recent = recent[recent['txn_month'] <= as_of_dt]
    avg = recent.groupby('customer_id')['total_amount'].mean()
    return avg


def active_months_12m(monthly_agg_df, as_of):
    """Count of distinct months in trailing 12 months with txn_count > 0. 0 if no data."""
    if not len(monthly_agg_df):
        return pd.Series([], dtype=int, name='active_months_12m')

    as_of_dt = pd.to_datetime(as_of)
    cutoff = as_of_dt - pd.DateOffset(months=12)
    recent = monthly_agg_df[monthly_agg_df['txn_month'] >= cutoff].copy()
    recent = recent[recent['txn_month'] <= as_of_dt]
    active = recent[recent['txn_count'] > 0]
    counts = active.groupby('customer_id')['txn_month'].nunique()
    return counts


def lifetime_return_rate(monthly_agg_df, min_txns_threshold=0):
    """SUM(return_count) / SUM(txn_count) across all history. 0.0 for customers with
    insufficient transaction volume (below min_txns_threshold)."""
    if not len(monthly_agg_df):
        return pd.Series([], dtype=float, name='lifetime_return_rate')

    totals = monthly_agg_df.groupby('customer_id')[['txn_count', 'return_count']].sum()
    # Apply threshold: customers with total txn_count < threshold get 0.0
    mask = totals['txn_count'] < min_txns_threshold
    rate = totals['return_count'] / totals['txn_count']
    rate[mask] = 0.0
    return rate


def tenure_days(customers_df, as_of):
    """Days since signup. All customers have a signup date."""
    as_of_dt = pd.to_datetime(as_of)
    tenure = (as_of_dt - customers_df['signup_date']).dt.days
    return tenure