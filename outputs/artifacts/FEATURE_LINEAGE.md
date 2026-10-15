# FEATURE_LINEAGE.md

> Auto-generated from features/schema.py + feature_store/registry.db

## Feature Summary

| Feature | Source | Rationale | Versions | Latest Version |
|---|---|---|---|---|
| days_since_last_txn | transactions.db | Customers who have stopped purchasing recently signal active disengagement, distinct from low frequency because a historically high-frequency buyer can still abruptly stop. | 1 | v1 |
| txn_count_90d | transactions.db | A drop in recent transaction frequency indicates waning interest, distinct from low recency because a customer might have bought yesterday but only once in the last 90 days. | 1 | v1 |
| recent_net_spend_window | transactions.db | Decreasing net spend in recent months signals falling wallet share, distinct from low overall spend because it measures a decline against the customer's own baseline. | 2 | v2 |
| avg_monthly_spend_6m | transactions_monthly_agg.parquet | Historical spend baseline against which recent drops (in recent_net_spend_window) are measured; a 20% spend drop matters more for historically high-spend customers. | 1 | v1 |
| active_months_12m | transactions_monthly_agg.parquet | Customers with consistent monthly engagement are habitual users with higher switching costs, distinct from high spenders who might make one massive purchase a year. | 1 | v1 |
| lifetime_return_rate | transactions_monthly_agg.parquet | High return rates proxy product dissatisfaction that precedes churn, distinct from low spend because a customer can spend heavily while remaining perpetually dissatisfied. | 2 | v2 |
| tenure_days | customers.csv | Tenure normalizes behavioral counts -- low counts are expected for new customers but alarming for long-tenure customers. | 1 | v1 |

## Detailed Version Registry

### days_since_last_txn
**Source:** transactions.db
**Type:** float64
**Nullable:** False
**Rationale:** Customers who have stopped purchasing recently signal active disengagement, distinct from low frequency because a historically high-frequency buyer can still abruptly stop.

#### v1 (latest)
- **Created:** 2026-10-13T15:10:58.959567Z
- **Description:** Days since last transaction; -1.0 if never transacted
- **Transform:** as_of - max(txn_timestamp) per customer, clipped at as_of
- **Business Rationale:** Customers who have stopped purchasing recently signal active disengagement.
- **Parameters:** {}
- **Parquet Path:** feature_store\values\days_since_last_txn__v1.parquet

### txn_count_90d
**Source:** transactions.db
**Type:** int64
**Nullable:** False
**Rationale:** A drop in recent transaction frequency indicates waning interest, distinct from low recency because a customer might have bought yesterday but only once in the last 90 days.

#### v1 (latest)
- **Created:** 2026-10-13T15:10:59.015851Z
- **Description:** Transaction count in trailing 90 days
- **Transform:** COUNT(*) where txn_timestamp > as_of - 90d
- **Business Rationale:** A drop in recent transaction frequency indicates waning interest.
- **Parameters:** {}
- **Parquet Path:** feature_store\values\txn_count_90d__v1.parquet

### recent_net_spend_window
**Source:** transactions.db
**Type:** float64
**Nullable:** False
**Rationale:** Decreasing net spend in recent months signals falling wallet share, distinct from low overall spend because it measures a decline against the customer's own baseline.

#### v2 (latest)
- **Created:** 2026-10-13T15:10:59.429527Z
- **Description:** Net spend in trailing 60-day window (v2, shorter window for faster churn signal)
- **Transform:** SUM(amount * (1 - is_returned)) where txn_timestamp > as_of - 60d
- **Business Rationale:** 90 days was too lagging to capture immediate churn signals; 60-day window reacts faster to sudden drops in engagement.
- **Parameters:** {"window_days": 60}
- **Parquet Path:** feature_store\values\recent_net_spend_window__v2.parquet

#### v1 (archived)
- **Created:** 2026-10-13T15:10:59.062968Z
- **Description:** Net spend (amount * (1 - is_returned)) in trailing 90-day window (v1)
- **Transform:** SUM(amount * (1 - is_returned)) where txn_timestamp > as_of - window_days
- **Business Rationale:** Decreasing net spend in recent months signals falling wallet share.
- **Parameters:** {"window_days": 90}
- **Parquet Path:** feature_store\values\recent_net_spend_window__v1.parquet

### avg_monthly_spend_6m
**Source:** transactions_monthly_agg.parquet
**Type:** float64
**Nullable:** False
**Rationale:** Historical spend baseline against which recent drops (in recent_net_spend_window) are measured; a 20% spend drop matters more for historically high-spend customers.

#### v1 (latest)
- **Created:** 2026-10-13T15:10:59.115686Z
- **Description:** Average monthly spend over trailing 6 months from parquet aggregate
- **Transform:** AVG(total_amount) over trailing 6 monthly rows per customer
- **Business Rationale:** Historical spend baseline against which recent drops are measured.
- **Parameters:** {}
- **Parquet Path:** feature_store\values\avg_monthly_spend_6m__v1.parquet

### active_months_12m
**Source:** transactions_monthly_agg.parquet
**Type:** int64
**Nullable:** False
**Rationale:** Customers with consistent monthly engagement are habitual users with higher switching costs, distinct from high spenders who might make one massive purchase a year.

#### v1 (latest)
- **Created:** 2026-10-13T15:10:59.162047Z
- **Description:** Count of active months in trailing 12 months
- **Transform:** Count distinct txn_month where txn_count > 0 in trailing 12 months
- **Business Rationale:** Consistent monthly engagement identifies habitual users with higher switching costs.
- **Parameters:** {}
- **Parquet Path:** feature_store\values\active_months_12m__v1.parquet

### lifetime_return_rate
**Source:** transactions_monthly_agg.parquet
**Type:** float64
**Nullable:** False
**Rationale:** High return rates proxy product dissatisfaction that precedes churn, distinct from low spend because a customer can spend heavily while remaining perpetually dissatisfied.

#### v2 (latest)
- **Created:** 2026-10-13T15:10:59.482455Z
- **Description:** Lifetime return rate with min 3 transaction threshold (v2)
- **Transform:** SUM(return_count)/SUM(txn_count) across all months; 0.0 if total txn_count < 3
- **Business Rationale:** v1 threshold=0 produced 100% return rate for customers with 1 txn and 1 return (false positives); v2 requires 3 transactions to stabilize the rate.
- **Parameters:** {"min_txns_threshold": 3}
- **Parquet Path:** feature_store\values\lifetime_return_rate__v2.parquet

#### v1 (archived)
- **Created:** 2026-10-13T15:10:59.211709Z
- **Description:** Lifetime return rate (SUM(return_count)/SUM(txn_count)) across all history (v1, threshold=0)
- **Transform:** SUM(return_count) / SUM(txn_count) across all historical months
- **Business Rationale:** High return rates proxy product dissatisfaction that precedes churn.
- **Parameters:** {"min_txns_threshold": 0}
- **Parquet Path:** feature_store\values\lifetime_return_rate__v1.parquet

### tenure_days
**Source:** customers.csv
**Type:** int64
**Nullable:** False
**Rationale:** Tenure normalizes behavioral counts -- low counts are expected for new customers but alarming for long-tenure customers.

#### v1 (latest)
- **Created:** 2026-10-13T15:10:59.263556Z
- **Description:** Days since signup date
- **Transform:** as_of - signup_date
- **Business Rationale:** Tenure normalizes behavioral counts — low counts are expected for new customers.
- **Parameters:** {}
- **Parquet Path:** feature_store\values\tenure_days__v1.parquet
