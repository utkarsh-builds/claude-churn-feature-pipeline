"""Output feature schema as versioned metadata."""

from dataclasses import dataclass, field
from typing import List


@dataclass
class FeatureSpec:
    name: str
    dtype: str
    nullable: bool
    source: str
    description: str


ALL_FEATURES: List[FeatureSpec] = [
    FeatureSpec('days_since_last_txn', 'float64', False,
                'transactions.db', 'Days since last transaction; -1.0 if never transacted'),
    FeatureSpec('txn_count_90d', 'int64', False,
                'transactions.db', 'Transaction count in trailing 90 days'),
    FeatureSpec('recent_net_spend_window', 'float64', False,
                'transactions.db', 'Net spend in trailing window (window_days parameterized)'),
    FeatureSpec('avg_monthly_spend_6m', 'float64', False,
                'transactions_monthly_agg.parquet', 'Avg monthly spend over trailing 6 months'),
    FeatureSpec('active_months_12m', 'int64', False,
                'transactions_monthly_agg.parquet', 'Count of active months in trailing 12 months'),
    FeatureSpec('lifetime_return_rate', 'float64', False,
                'transactions_monthly_agg.parquet', 'Lifetime return rate (sum return_count / sum txn_count)'),
    FeatureSpec('tenure_days', 'int64', False,
                'customers.csv', 'Days since signup date'),
]

FEATURE_SET_VERSION = '1.0.0'