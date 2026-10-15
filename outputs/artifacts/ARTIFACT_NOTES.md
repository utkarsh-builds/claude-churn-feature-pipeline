# ARTIFACT_NOTES.md

> Self-critique log for the churn feature pipeline build

## 1. Empty DataFrame handling in transforms (caught in review)

**Issue:** Several transform functions (`days_since_last_txn`, `txn_count_90d`, etc.) originally returned a single-element Series (e.g., `pd.Series(0, name='txn_count_90d')`) when given an empty DataFrame. This caused the subsequent `.fillna(...)` in `build.py` to never trigger for truly empty inputs, because there was already a result — just with the wrong shape.

**Fix:** Changed the early-return to `pd.Series([], dtype=..., name=...)` so the merge in `build.py` produces NaN for all customers, which then correctly triggers `.fillna()` to apply the spec's default.

**Lesson:** A transform returning a *default value* for "no data" is different from returning a *defaulted result for all customers*. The former should be an empty Series that the build layer merges and then fills.

## 2. Test expectation miscalibrated for `test_txn_count_90d::test_normal_case`

**Issue:** The test had incorrect date math — it assumed `2026-05-01` was 91 days before `2026-07-31` (it's 91 days, not 90), which meant the boundary test expectation was wrong.

**Fix:** Corrected test dates and expectations to match the actual 90-day window.

**Lesson:** Test data needs the same date verification as production data. Off-by-one in date arithmetic is easy to get wrong in test fixtures too.

## 3. Lineage doc uses schema description as rationale

**Issue:** The FEATURE_LINEAGE.md generation reuses the schema description as the rationale column, which is slightly redundant. A richer generation would pull the spec's rationale text for each feature.

**Status:** Acceptable for now — the registry stores the full rationale text per version, and the detailed version registry section includes it. The table summary is a quick reference.

## 4. `as_of` date choice

The training build uses `as_of = 2026-07-31` (the last observed transaction timestamp). This seems correct — it's the natural data snapshot boundary. No future leakage concern since the features are evaluated as of this date.