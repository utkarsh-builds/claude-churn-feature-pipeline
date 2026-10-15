"""Score one or more customers using the shared feature pipeline.
This is the "scoring" path: calls build.py with specific customer_ids.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from features import build


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/score_customer.py <customer_id1> [customer_id2 ...]")
        print("   or: python scripts/score_customer.py --all")
        sys.exit(1)

    as_of = '2026-07-31'

    if sys.argv[1] == '--all':
        customer_ids = None  # all customers
        label = "all customers"
    else:
        customer_ids = [int(x) for x in sys.argv[1:]]
        label = f"customers {customer_ids}"

    print(f"Scoring features for {label} as of {as_of}...")
    features_df = build.build_features(as_of=as_of, customer_ids=customer_ids)

    print(f"\nGenerated features for {len(features_df)} customer(s):")
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 200)
    print(features_df.to_string(index=False))

    return features_df


if __name__ == '__main__':
    import pandas as pd
    main()