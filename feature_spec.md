# feature_spec.md — Churn Feature Pipeline

<<LEARNER: fill in the SKELETON section below yourself, against skill.md's Domain Context
section and Stage 0's generated data_dictionary.md/feature proposal — correct that proposal,
don't restate it. Do this before opening Claude Code for the build stage. See the EXAMPLE
section below (and Helper Guide.docx) for what a filled-in answer looks like — the example
uses return_rate_90d, which is NOT one of this dataset's real candidate features, so it can't
be copied in as your own answer. Delete the EXAMPLE section and every bracketed prompt in the
SKELETON before you submit.>>

---

## SKELETON

## Candidate features

### Feature 1:
- **Feature**: `days_since_last_txn`
- **Source**: `data/transactions.db`
- **Computation**: `as_of - max(txn_timestamp)`
- **Zero-activity default**: `-1.0` (sentinel value)
- **If multiple sources could supply this, which and why?**: `transactions.db`, because exact recency requires row-level precision that the month-boundary Parquet aggregate cannot provide.
- **Rationale**: This predicts churn because customers who have stopped purchasing recently are signaling active disengagement, distinct from just low frequency because a historically high-frequency buyer can still abruptly stop.

### Feature 2:
- **Feature**: `txn_count_90d`
- **Source**: `data/transactions.db`
- **Computation**: `COUNT(*)` where `txn_timestamp > as_of - 90d`
- **Zero-activity default**: `0`
- **If multiple sources could supply this, which and why?**: `transactions.db`, because rolling 90-day windows require exact timestamps rather than calendar month aggregations.
- **Rationale**: This predicts churn because a sudden drop in transaction frequency indicates waning interest, distinct from just low recency because a customer might have bought yesterday but only once in the last 90 days.

### Feature 3:
- **Feature**: `recent_net_spend_window`
- **Source**: `data/transactions.db`
- **Computation**: `SUM(amount * (1 - is_returned))` where `txn_timestamp` falls within the trailing window.
- **Zero-activity default**: `0.0`
- **If multiple sources could supply this, which and why?**: `transactions.db`, because non-calendar-aligned windows require exact timestamps, and 10 active customers are missing from the Parquet aggregate.
- **Rationale**: This predicts churn because a sudden drop in net spend signals falling wallet share, distinct from low overall spend because it measures a decline against the customer's own baseline.

### Feature 4:
- **Feature**: `avg_monthly_spend_6m`
- **Source**: `data/transactions_monthly_agg.parquet`
- **Computation**: Average of `total_amount` over the trailing 6 months (the 6 latest `txn_month` rows per customer) prior to `as_of`.
- **Zero-activity default**: `0.0`
- **If multiple sources could supply this, which and why?**: `transactions_monthly_agg.parquet`, because pre-computed monthly spend roll-ups across historical months are far more efficient to process than scanning raw database rows.
- **Rationale**: This predicts churn by providing the historical baseline against which recent net spend drops (in `recent_net_spend_window`) are measured; a 20% spend drop matters significantly more for historically high-spend customers than for consistently low-spend ones.

### Feature 5:
- **Feature**: `active_months_12m`
- **Source**: `data/transactions_monthly_agg.parquet`
- **Computation**: Count of distinct `txn_month` rows in the trailing 12 months (relative to `as_of`) where `txn_count > 0`.
- **Zero-activity default**: `0`
- **If multiple sources could supply this, which and why?**: `transactions_monthly_agg.parquet`, because evaluating 12 months of history is much faster and more reliable via pre-computed monthly aggregates than scanning raw rows.
- **Rationale**: This predicts churn because customers with consistent monthly engagement are habitual users with higher switching costs, distinct from high spenders who might just make one massive purchase a year.

### Feature 6:
- **Feature**: `lifetime_return_rate`
- **Source**: `data/transactions_monthly_agg.parquet`
- **Computation**: `SUM(return_count) / SUM(txn_count)` across all available historical months.
- **Zero-activity default**: `0.0`
- **If multiple sources could supply this, which and why?**: `transactions_monthly_agg.parquet`, because lifetime aggregations are perfectly suited to the pre-aggregated ETL source.
- **Rationale**: This predicts churn because customers who return a high percentage of items are experiencing product dissatisfaction, distinct from just low spend because a customer can spend heavily while remaining perpetually dissatisfied.

### Feature 7:
- **Feature**: `tenure_days`
- **Source**: `data/customers.csv`
- **Computation**: `as_of - signup_date`
- **Zero-activity default**: `0`
- **If multiple sources could supply this, which and why?**: Only available in `customers.csv`.
- **Rationale**: This predicts churn because newer customers naturally have lower loyalty and higher flight risk, distinct from just low transaction counts which must be normalized against how long they've actually been on the platform.

### Deliberate Omissions
- **`acquisition_channel` & `region`**: Intentionally omitted from this feature set. These are static profile categoricals from `customers.csv` that carry high cardinality risk without providing actionable behavioral churn signals. The pipeline focuses strictly on dynamic transactional activity and engagement patterns.

## Train/score parity design

- **Shared function/code path**: `build_features(as_of, source_paths, customer_ids)`
- **Only allowed training/scoring difference**: Filtering which `customer_ids` are evaluated and returned at the very end of the pipeline.
- **How as_of is threaded (not hardcoded)**: Passed as an explicit `datetime` parameter to the main build function and threaded through to every transform function to strictly truncate data before calculation.

## Feature store, versioning & lineage

- **Features versioned**: `recent_net_spend_window`, `lifetime_return_rate`
- **Feature** / **Parameter** / **Value per version** / **Reason each version differs**: 
  - `recent_net_spend_window` / `window_days` / v1 = 90, v2 = 60 / 90 days was too lagging to capture immediate churn signals; a 60-day window reacts faster to sudden drops in engagement.
  - `lifetime_return_rate` / `min_txns_threshold` / v1 = 0, v2 = 3 / v1 resulted in a 100% return rate for customers with exactly 1 transaction and 1 return (creating false positives); v2 requires a baseline of 3 transactions to stabilize the rate mathematically.
- **What forces a version bump vs. not**: A material change in underlying computation, source data, or tunable parameters that alters output values for at least some customers, not just renaming a column or refactoring code.
- **What a lineage entry must let someone reconstruct**: The exact source file/columns used, the transformation logic applied, the business reason for the feature/version, and the exact `parquet_path` to the cached values.

## Multi-source judgment calls

- **Feature**: `recent_net_spend_window` and `txn_count_90d` — **Source chosen**: `transactions.db` — **Why**: Short trailing 90-day windows require day-level precision, which the ETL-lagged monthly aggregate (which is also missing 10 customers) cannot guarantee.
- **Feature**: `avg_monthly_spend_6m`, `active_months_12m`, and `lifetime_return_rate` — **Source chosen**: `transactions_monthly_agg.parquet` — **Why**: Long-term baseline features align perfectly with calendar month boundaries, making the Parquet file the most efficient and type-safe source.

## Data-quality checks

- **Check**: No unexpected nulls after applying defaults — **Catches**: A left join that accidentally drops or fails to fill the 81 known zero-transaction customers — **On failure**: Raise exception / non-zero exit.
- **Check**: The `0.0` default is explicitly present for zero-transaction customers — **Catches**: An off-by-one error or `.fillna()` oversight in the transformation step — **On failure**: Raise exception / non-zero exit.
- **Check**: `recent_net_spend_window` $\ge 0.0$ and `lifetime_return_rate` is between $0.0$ and $1.0$ — **Catches**: Logic errors where positive return amounts are incorrectly subtracted twice, or transaction division logic fails — **On failure**: Raise exception / non-zero exit.
- **Check**: Final output row count exactly matches the unique length of provided `customer_ids` — **Catches**: A fan-out bug during table merges that duplicates customer rows — **On failure**: Raise exception / non-zero exit.