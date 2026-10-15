"""Single shared entry point: build_features(as_of, ...).
Both training and scoring call this — the only difference is which customer_ids are selected.
"""

import pandas as pd
import numpy as np

from features import ingest, transforms, schema, quality_checks


def build_features(as_of, source_paths=None, customer_ids=None):
    """Compute all candidate features for given customer_ids as of the as_of date.

    Parameters
    ----------
    as_of : str or datetime
        The point-in-time for computations (truncates data before this date).
    source_paths : dict, optional
        Override source paths, e.g. {'customers': 'path', 'transactions': 'path',
        'monthly_agg': 'path'}. Defaults to the standard data/ locations.
    customer_ids : array-like, optional
        If provided, filter output to these customers. If None, all 1,500.

    Returns
    -------
    pd.DataFrame
        Columns: customer_id + all 7 features, indexed by customer_id.
        No nulls — defaults applied per feature_spec.md.
    """
    if source_paths is None:
        source_paths = {}

    # -- Ingest --
    customers_df = ingest.load_customers(source_paths.get("customers"))
    transactions_df = ingest.load_transactions(source_paths.get("transactions"))
    monthly_agg_df = ingest.load_monthly_agg(source_paths.get("monthly_agg"))

    # Filter all data to strictly before or at as_of
    as_of_dt = pd.to_datetime(as_of)
    transactions_df = transactions_df[transactions_df["txn_timestamp"] <= as_of_dt].copy()
    monthly_agg_df = monthly_agg_df[monthly_agg_df["txn_month"] <= as_of_dt].copy()

    # Build a base set of all customer_ids (1-1500)
    all_ids = customers_df[["customer_id"]].copy()
    base_customers = customers_df.copy()

    # -- Apply transforms --

    # F1: days_since_last_txn
    dsl = transforms.days_since_last_txn(transactions_df, as_of)
    all_ids = all_ids.merge(dsl.to_frame("days_since_last_txn"), on="customer_id", how="left")
    all_ids["days_since_last_txn"] = all_ids["days_since_last_txn"].fillna(-1.0)

    # F2: txn_count_90d
    txn90 = transforms.txn_count_90d(transactions_df, as_of)
    all_ids = all_ids.merge(txn90.to_frame("txn_count_90d"), on="customer_id", how="left")
    all_ids["txn_count_90d"] = all_ids["txn_count_90d"].fillna(0).astype(int)

    # F3: recent_net_spend_window (v1 default = 90 days)
    rnsw = transforms.recent_net_spend_window(transactions_df, as_of, window_days=90)
    all_ids = all_ids.merge(rnsw.to_frame("recent_net_spend_window"), on="customer_id", how="left")
    all_ids["recent_net_spend_window"] = all_ids["recent_net_spend_window"].fillna(value=float("nan"))

    # F4: avg_monthly_spend_6m
    ams = transforms.avg_monthly_spend_6m(monthly_agg_df, as_of)
    all_ids = all_ids.merge(ams.to_frame("avg_monthly_spend_6m"), on="customer_id", how="left")
    all_ids["avg_monthly_spend_6m"] = all_ids["avg_monthly_spend_6m"].fillna(0.0)

    # F5: active_months_12m
    am12 = transforms.active_months_12m(monthly_agg_df, as_of)
    all_ids = all_ids.merge(am12.to_frame("active_months_12m"), on="customer_id", how="left")
    all_ids["active_months_12m"] = all_ids["active_months_12m"].fillna(0).astype(int)

    # F6: lifetime_return_rate (v1 default threshold = 0)
    lrr = transforms.lifetime_return_rate(monthly_agg_df, min_txns_threshold=0)
    all_ids = all_ids.merge(lrr.to_frame("lifetime_return_rate"), on="customer_id", how="left")
    all_ids["lifetime_return_rate"] = all_ids["lifetime_return_rate"].fillna(0.0)

    # F7: tenure_days
    base_customers["tenure_days"] = transforms.tenure_days(base_customers, as_of)
    all_ids = all_ids.merge(base_customers[["customer_id", "tenure_days"]], on="customer_id", how="left")
    # All customers have signup_date, so no fillna needed

    # -- Filter to requested customer_ids --
    if customer_ids is not None:
        ids_set = set(customer_ids)
        all_ids = all_ids[all_ids["customer_id"].isin(ids_set)].copy()

    # Guarantee non-null for all feature columns (belt-and-suspenders)
    for col in all_ids.columns:
        if col != "customer_id" and all_ids[col].dtype in (np.float64, np.float32):
            all_ids[col] = all_ids[col].fillna(0.0)
        elif col != "customer_id" and all_ids[col].dtype in (np.int64, np.int32):
            all_ids[col] = all_ids[col].fillna(0).astype(int)

    return all_ids.reset_index(drop=True)


def build_feature_for_versioning(transactions_df, monthly_agg_df, customers_df, as_of, feature_name, **params):
    """Compute a single versioned feature (with specific parameters).
    Used by versioning exercise for non-default parameter combinations.
    """
    as_of_dt = pd.to_datetime(as_of)

    # Filter data to as_of
    transactions_df = transactions_df[transactions_df["txn_timestamp"] <= as_of_dt].copy()
    monthly_agg_df = monthly_agg_df[monthly_agg_df["txn_month"] <= as_of_dt].copy()

    all_ids = customers_df[["customer_id"]].copy()

    if feature_name == "recent_net_spend_window":
        window_days = params.get("window_days", 90)
        ser = transforms.recent_net_spend_window(transactions_df, as_of, window_days=window_days)
        all_ids = all_ids.merge(ser.to_frame(feature_name), on="customer_id", how="left")
        all_ids[feature_name] = all_ids[feature_name].fillna(0.0)

    elif feature_name == "lifetime_return_rate":
        min_txns = params.get("min_txns_threshold", 0)
        ser = transforms.lifetime_return_rate(monthly_agg_df, min_txns_threshold=min_txns)
        all_ids = all_ids.merge(ser.to_frame(feature_name), on="customer_id", how="left")
        all_ids[feature_name] = all_ids[feature_name].fillna(0.0)

    else:
        raise ValueError(f"Unknown versioned feature: {feature_name}")

    return all_ids[["customer_id", feature_name]]
