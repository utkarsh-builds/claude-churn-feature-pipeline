# Churn Feature Pipeline

A versioned, lineage-documented feature engineering pipeline for the e-commerce customer churn dataset. Ingests from three heterogeneous sources (CSV, SQLite, Parquet), builds seven candidate features, registers them in a local feature store (SQLite + Parquet snapshots), runs automated quality checks, and exercises feature versioning with distribution comparison.

---

## Environment Setup

### Prerequisites

- Python 3.11+
- `pip` (Python package installer)

### 1. Create and activate a virtual environment

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Verify data sources

The pipeline expects three raw data files at the repository root:

| File | Format | Source |
|---|---|---|
| `data/customers.csv` | CSV (1,500 rows) | Customer profiles and churn labels |
| `data/transactions.db` | SQLite (11,742 rows) | Row-level transaction records |
| `data/transactions_monthly_agg.parquet` | Apache Parquet (8,086 rows) | Pre-aggregated monthly customer roll-ups |

These are provided separately — place them in the `data/` directory before running.

---

## Running the Pipeline

### Build all features (training mode)

Generates all seven candidate features for all 1,500 customers, runs data-quality checks, registers every feature in the feature store, and executes the versioning exercise (creating v2 of two versioned features with different parameter values):

```bash
python scripts/build_training_features.py
```

This script:
1. Loads all three raw sources via `features/ingest.py`
2. Computes all 7 features via `features/transforms.py`
3. Passes quality checks (`features/quality_checks.py`)
4. Registers each feature in `feature_store/registry.db` + parquet snapshots
5. Builds and registers v2 of `recent_net_spend_window` (90d → 60d window) and `lifetime_return_rate` (threshold 0 → 3)

### Score individual customers (scoring mode)

Computes features for one or more specific customer IDs, using the same shared code path as training:

```bash
# Score specific customers
python scripts/score_customer.py 7 42 101

# Score all customers
python scripts/score_customer.py --all
```

The scoring path calls the same `build_features(as_of=...)` function — the only difference is which `customer_ids` are selected at the end, guaranteeing train/score parity.

### Compare feature versions

Loads every registered version of each versioned feature from the feature store and produces a distribution comparison:

```bash
python scripts/compare_feature_versions.py
```

Generates `VERSION_COMPARISON.md` with per-feature statistics: number of customers with changed values, distribution shifts (mean, std, range), and an interpretation of whether a model would notice the change.

---

## Running the Test Suite

```bash
# Run all tests
pytest tests/ -v

# Run specific test files
pytest tests/test_transforms.py -v
pytest tests/test_parity.py -v
pytest tests/test_quality_checks.py -v
pytest tests/test_feature_store.py -v
```

The test suite covers:

| Test file | What it tests | Count |
|---|---|---|
| `test_transforms.py` | Each feature function in isolation: normal case, zero-activity, single-record, window boundaries | 23 tests |
| `test_parity.py` | Training path (all customers) vs. scoring path (filtered customer_ids) produce identical values | 3 tests |
| `test_quality_checks.py` | Each quality check fires on deliberately bad input and passes on clean input | 8 tests |
| `test_feature_store.py` | Version registration, independent retrieval, `is_latest` flag, parquet file persistence | 5 tests |

**Total: 43 tests**

---

## Feature Store

The local feature store consists of:

- **`feature_store/registry.db`** — SQLite database with a `feature_registry` table tracking every registered version of every feature, including metadata (source columns, transform summary, business rationale, parameters, and `is_latest` flag).
- **`feature_store/values/`** — One Parquet snapshot per (feature_name, version) combination. Each snapshot contains `customer_id`, the feature value column, and `as_of_date`.

### Versioned features

| Feature | Parameter | v1 value | v2 value | Rationale for change |
|---|---|---|---|---|
| `recent_net_spend_window` | `window_days` | 90 | 60 | Shorter window reacts faster to sudden drops in engagement |
| `lifetime_return_rate` | `min_txns_threshold` | 0 | 3 | v1 produced 100% return rate for customers with 1 transaction and 1 return (false positive); v2 requires 3+ transactions to stabilize |

---

## Generated Reports

After running the build, the repository root contains:

| File | Contents |
|---|---|
| `FEATURE_LINEAGE.md` | Per-feature, per-version documentation: source columns, transform logic, business rationale, and Parquet path |
| `VERSION_COMPARISON.md` | Distribution comparison between v1 and v2 of each versioned feature, with interpretation |
| `PARITY_CHECK.md` | Train/score parity verification results, including the mutation check |
| `ARTIFACT_NOTES.md` | Self-critique: what was reconsidered, what could be improved |
| `review_log.md` | Step 3 self-review findings and resolution |

---

## Project Layout

```
.
├── data/                           <- Raw data sources (provided, not edited)
│   ├── customers.csv
│   ├── transactions.db
│   └── transactions_monthly_agg.parquet
├── features/                       <- Feature module
│   ├── __init__.py
│   ├── ingest.py                   <- One loader per source (pure I/O)
│   ├── transforms.py               <- Pure feature functions
│   ├── build.py                    <- Single shared entry point: build_features(as_of, ...)
│   ├── schema.py                   <- Feature metadata (names, dtypes, sources)
│   └── quality_checks.py           <- Null, bound, and row-count checks
├── feature_store/                  <- Local feature store
│   ├── store.py                    <- Register/retrieve API
│   ├── registry.db                 <- SQLite version registry (generated)
│   └── values/                     <- Parquet snapshots per (feature, version)
├── scripts/                        <- Entry points
│   ├── build_training_features.py
│   ├── score_customer.py
│   └── compare_feature_versions.py
├── tests/                          <- Test suite
│   ├── test_transforms.py
│   ├── test_parity.py
│   ├── test_quality_checks.py
│   └── test_feature_store.py
├── data_dictionary.md              <- Verified ground-truth schema (from Stage 0 review)
├── feature_spec.md                 <- Confirmed feature specification
├── requirements.txt
├── pytest.ini
└── README.md
```

---

## Pipeline Design Principles

- **Single shared code path**: Both training and scoring call `features/build.py::build_features(as_of=...)`. The only difference is which `customer_ids` are selected at the end.
- **Explicit defaults**: All 81 zero-transaction customers receive explicit defaults (-1.0 for recency, 0/0.0 for counts and spend) — never a bare null or NaN.
- **Multi-source awareness**: Short trailing windows (90d, 60d) use the row-level SQLite source for day-level precision. Long baseline features (6m, 12m, lifetime) use the pre-aggregated Parquet for efficiency. The 10-customer discrepancy between DB and Parquet is accounted for in source selection.
- **Immutable versions**: Once registered, a feature version's Parquet file is never overwritten. A new version always creates a new file and registry row, with `is_latest` flipped atomically.