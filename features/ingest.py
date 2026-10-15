"""One loader function per source. Pure I/O — no feature logic."""

import sqlite3
import pandas as pd
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_customers(path=None):
    """Load customers.csv. Returns DataFrame with customer_id, signup_date parsed, and static cols."""
    if path is None:
        path = os.path.join(_PROJECT_ROOT, 'data', 'customers.csv')
    df = pd.read_csv(path)
    df['signup_date'] = pd.to_datetime(df['signup_date'])
    return df


def load_transactions(path=None):
    """Load transactions.db (SQLite, table 'transactions'). Returns DataFrame with parsed timestamps."""
    if path is None:
        path = os.path.join(_PROJECT_ROOT, 'data', 'transactions.db')
    conn = sqlite3.connect(path)
    df = pd.read_sql('SELECT * FROM transactions', conn)
    conn.close()
    df['txn_timestamp'] = pd.to_datetime(df['txn_timestamp'])
    return df


def load_monthly_agg(path=None):
    """Load transactions_monthly_agg.parquet. Returns DataFrame with txn_month as datetime."""
    if path is None:
        path = os.path.join(_PROJECT_ROOT, 'data', 'transactions_monthly_agg.parquet')
    df = pd.read_parquet(path)
    # txn_month is already datetime64[us] from parquet
    return df