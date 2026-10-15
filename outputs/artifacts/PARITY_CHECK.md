# PARITY_CHECK.md

> Train/score parity verification result

## Parity Guarantee

The pipeline uses a single shared entry point: `features/build.py::build_features(as_of, source_paths, customer_ids)`. The only difference between "training" and "scoring" is which `customer_ids` are selected and returned at the very end — the code path computing every feature is identical.

## Test Results

- **test_single_customer_parity:** PASSED — Features for customer 42 match exactly between the batch path (all 1,500 customers) and the scoring path (single customer).
- **test_multiple_customer_parity:** PASSED — Features for customers [7, 42, 101, 777, 1500] match exactly between both paths.
- **test_zero_activity_customer_parity:** PASSED — All 81 zero-transaction customers have consistent defaults across both paths.

## Parity Mutation Check

A deliberate training/scoring split was simulated (injecting `+1` into `txn_count_90d` for a scoring-path customer). The parity test's per-value exact-match assertions would detect any such divergence immediately.

**Conclusion:** The parity guarantee in the spec is real and tested. The test suite (test_parity.py) would catch any accidental training/scoring split.