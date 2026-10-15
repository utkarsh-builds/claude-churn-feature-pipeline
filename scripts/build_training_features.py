"""Build all candidate features for all customers and register in the feature store.
Also runs the versioning exercise for spec-designated versioned features.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from datetime import datetime

from features import build, ingest, quality_checks
from feature_store import store


def main():
    # Use a fixed as_of date matching the data snapshot
    as_of = '2026-07-31'

    print("=" * 60)
    print("Building all candidate features (training mode)")
    print("=" * 60)

    # Build all 7 features with default parameters
    features_df = build.build_features(as_of=as_of)

    # Run quality checks on the full output
    print("\nRunning quality checks...")
    all_feature_cols = [c for c in features_df.columns if c != 'customer_id']
    default_cols = [
        ('days_since_last_txn', -1.0),
        ('txn_count_90d', 0),
        ('recent_net_spend_window', 0.0),
        ('avg_monthly_spend_6m', 0.0),
        ('active_months_12m', 0),
        ('lifetime_return_rate', 0.0),
        ('tenure_days', None),
    ]
    try:
        results = quality_checks.run_all_checks(
            features_df, all_feature_cols, default_cols, 1500
        )
        for r in results:
            print(f"  {r}")
    except quality_checks.QualityCheckError as e:
        print(f"  FAIL: {e}")
        print("Aborting — quality checks did not pass.")
        sys.exit(1)

    print("\nRegistering all 7 features in the feature store...")
    as_of_dt = pd.to_datetime(as_of)

    # Register each feature with its description, source, and rationale
    feature_metadata = {
        'days_since_last_txn': {
            'desc': 'Days since last transaction; -1.0 if never transacted',
            'source': 'data/transactions.db:transactions.txn_timestamp',
            'transform': 'as_of - max(txn_timestamp) per customer, clipped at as_of',
            'rationale': 'Customers who have stopped purchasing recently signal active disengagement.',
        },
        'txn_count_90d': {
            'desc': 'Transaction count in trailing 90 days',
            'source': 'data/transactions.db:transactions.txn_timestamp',
            'transform': 'COUNT(*) where txn_timestamp > as_of - 90d',
            'rationale': 'A drop in recent transaction frequency indicates waning interest.',
        },
        'recent_net_spend_window': {
            'desc': 'Net spend (amount * (1 - is_returned)) in trailing 90-day window (v1)',
            'source': 'data/transactions.db:transactions.amount,is_returned,txn_timestamp',
            'transform': 'SUM(amount * (1 - is_returned)) where txn_timestamp > as_of - window_days',
            'rationale': 'Decreasing net spend in recent months signals falling wallet share.',
        },
        'avg_monthly_spend_6m': {
            'desc': 'Average monthly spend over trailing 6 months from parquet aggregate',
            'source': 'data/transactions_monthly_agg.parquet:total_amount,txn_month',
            'transform': 'AVG(total_amount) over trailing 6 monthly rows per customer',
            'rationale': 'Historical spend baseline against which recent drops are measured.',
        },
        'active_months_12m': {
            'desc': 'Count of active months in trailing 12 months',
            'source': 'data/transactions_monthly_agg.parquet:txn_count,txn_month',
            'transform': 'Count distinct txn_month where txn_count > 0 in trailing 12 months',
            'rationale': 'Consistent monthly engagement identifies habitual users with higher switching costs.',
        },
        'lifetime_return_rate': {
            'desc': 'Lifetime return rate (SUM(return_count)/SUM(txn_count)) across all history (v1, threshold=0)',
            'source': 'data/transactions_monthly_agg.parquet:return_count,txn_count',
            'transform': 'SUM(return_count) / SUM(txn_count) across all historical months',
            'rationale': 'High return rates proxy product dissatisfaction that precedes churn.',
        },
        'tenure_days': {
            'desc': 'Days since signup date',
            'source': 'data/customers.csv:signup_date',
            'transform': 'as_of - signup_date',
            'rationale': 'Tenure normalizes behavioral counts — low counts are expected for new customers.',
        },
    }

    for feat_name in all_feature_cols:
        meta = feature_metadata[feat_name]
        feat_series = features_df[['customer_id', feat_name]].copy()
        feat_series['as_of_date'] = as_of_dt

        # Handle int columns — store as int64 in parquet
        if feat_name in ('txn_count_90d', 'active_months_12m', 'tenure_days'):
            feat_series[feat_name] = feat_series[feat_name].astype(int)
            feat_series[feat_name] = feat_series[feat_name].astype('int64')

        version = store.register_version(
            feature_name=feat_name,
            values_df=feat_series,
            description=meta['desc'],
            source_columns=meta['source'],
            transform_summary=meta['transform'],
            business_rationale=meta['rationale'],
            parameters={'window_days': 90} if feat_name == 'recent_net_spend_window'
                       else ({'min_txns_threshold': 0} if feat_name == 'lifetime_return_rate'
                             else {}),
        )
        print(f"  Registered {feat_name} (v{version})")

    # ---- Versioning Exercise ----
    print("\n" + "=" * 60)
    print("Versioning Exercise")
    print("=" * 60)

    # Load raw data for versioned feature computation
    customers_df = ingest.load_customers()
    transactions_df = ingest.load_transactions()
    monthly_agg_df = ingest.load_monthly_agg()

    # --- recent_net_spend_window v2: window_days = 60 ---
    print("\n--- recent_net_spend_window v2 (window_days=60) ---")
    rnsw_v2 = build.build_feature_for_versioning(
        transactions_df, monthly_agg_df, customers_df,
        as_of=as_of, feature_name='recent_net_spend_window', window_days=60
    )
    rnsw_v2['as_of_date'] = as_of_dt

    store.register_version(
        feature_name='recent_net_spend_window',
        values_df=rnsw_v2,
        description='Net spend in trailing 60-day window (v2, shorter window for faster churn signal)',
        source_columns='data/transactions.db:transactions.amount,is_returned,txn_timestamp',
        transform_summary='SUM(amount * (1 - is_returned)) where txn_timestamp > as_of - 60d',
        business_rationale='90 days was too lagging to capture immediate churn signals; 60-day window reacts faster to sudden drops in engagement.',
        parameters={'window_days': 60},
    )
    print("  Registered recent_net_spend_window v2 (60-day window)")

    # --- lifetime_return_rate v2: min_txns_threshold = 3 ---
    print("\n--- lifetime_return_rate v2 (min_txns_threshold=3) ---")
    lrr_v2 = build.build_feature_for_versioning(
        transactions_df, monthly_agg_df, customers_df,
        as_of=as_of, feature_name='lifetime_return_rate', min_txns_threshold=3
    )
    lrr_v2['as_of_date'] = as_of_dt

    store.register_version(
        feature_name='lifetime_return_rate',
        values_df=lrr_v2,
        description='Lifetime return rate with min 3 transaction threshold (v2)',
        source_columns='data/transactions_monthly_agg.parquet:return_count,txn_count',
        transform_summary='SUM(return_count)/SUM(txn_count) across all months; 0.0 if total txn_count < 3',
        business_rationale='v1 threshold=0 produced 100% return rate for customers with 1 txn and 1 return (false positives); v2 requires 3 transactions to stabilize the rate.',
        parameters={'min_txns_threshold': 3},
    )
    print("  Registered lifetime_return_rate v2 (min_txns_threshold=3)")

    print("\n" + "=" * 60)
    print("Training feature build complete.")
    print("=" * 60)

    # Print summary of all registered versions
    print("\nFeature Store Summary:")
    for feat_name in all_feature_cols + ['recent_net_spend_window', 'lifetime_return_rate']:
        versions_df = store.list_versions(feat_name)
        if len(versions_df) > 0:
            latest_v = versions_df[versions_df['is_latest'] == 1]['version'].values
            latest_str = str(latest_v[0]) if len(latest_v) else 'unknown'
            print(f"  {feat_name}: {len(versions_df)} version(s), latest=v{latest_str}")


if __name__ == '__main__':
    main()