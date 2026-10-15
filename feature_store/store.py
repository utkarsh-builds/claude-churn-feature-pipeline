"""Local feature store: SQLite metadata/version registry + parquet value snapshots."""

import os
import json
import sqlite3
from datetime import datetime, timezone

import pandas as pd
import numpy as np


_STORE_ROOT = os.path.dirname(os.path.abspath(__file__))
_REGISTRY_PATH = os.path.join(_STORE_ROOT, 'registry.db')
_VALUES_DIR = os.path.join(_STORE_ROOT, 'values')


def _ensure_values_dir():
    os.makedirs(_VALUES_DIR, exist_ok=True)


def _get_connection():
    conn = sqlite3.connect(_REGISTRY_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_registry():
    """Create the feature_registry table if it doesn't exist."""
    conn = _get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feature_registry (
            feature_name    TEXT NOT NULL,
            version         INTEGER NOT NULL,
            created_at      TEXT NOT NULL,
            description     TEXT NOT NULL,
            source_columns  TEXT NOT NULL,
            transform_summary TEXT NOT NULL,
            business_rationale TEXT NOT NULL,
            parameters      TEXT NOT NULL,
            parquet_path    TEXT NOT NULL,
            is_latest       INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (feature_name, version)
        )
    """)
    conn.commit()
    conn.close()


_init_registry()


def register_version(feature_name, values_df, description, source_columns,
                     transform_summary, business_rationale, parameters=None):
    """Register a new version of a feature.

    Writes parquet snapshot, inserts registry row, flips is_latest atomically.

    Parameters
    ----------
    values_df : pd.DataFrame
        Must have columns: customer_id, <feature_name>, as_of_date
    description : str
        Human-readable description.
    source_columns : str
        e.g. 'data/transactions.db:transactions.amount,txn_timestamp'
    transform_summary : str
        Short prose of computation.
    business_rationale : str
        Why this feature (or this version) exists.
    parameters : dict, optional
        Tunable parameters for this version (e.g. {"window_days": 90}).

    Returns
    -------
    int
        The new version number.
    """
    conn = _get_connection()
    try:
        # Determine next version number
        cursor = conn.execute(
            "SELECT COALESCE(MAX(version), 0) FROM feature_registry WHERE feature_name = ?",
            (feature_name,)
        )
        next_version = cursor.fetchone()[0] + 1

        # Build parquet path
        parquet_filename = f"{feature_name}__v{next_version}.parquet"
        parquet_path = os.path.join('feature_store', 'values', parquet_filename)
        abs_parquet_path = os.path.join(_STORE_ROOT, 'values', parquet_filename)

        _ensure_values_dir()

        # Ensure values_df has required columns
        out_df = values_df.copy()
        out_df.to_parquet(abs_parquet_path, index=False)

        # Build registry row
        now_iso = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        params_json = json.dumps(parameters if parameters else {})

        # Flip prior latest to 0, insert new row in same transaction
        conn.execute("BEGIN")
        conn.execute(
            "UPDATE feature_registry SET is_latest = 0 WHERE feature_name = ?",
            (feature_name,)
        )
        conn.execute("""
            INSERT INTO feature_registry
                (feature_name, version, created_at, description, source_columns,
                 transform_summary, business_rationale, parameters, parquet_path, is_latest)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (feature_name, next_version, now_iso, description, source_columns,
              transform_summary, business_rationale, params_json, parquet_path))
        conn.commit()

        return next_version
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_latest(feature_name):
    """Get the latest version's feature values.

    Returns (version, DataFrame) with columns [customer_id, feature_name, as_of_date].
    Returns (None, None) if feature not found.
    """
    conn = _get_connection()
    try:
        cursor = conn.execute(
            "SELECT version, parquet_path FROM feature_registry "
            "WHERE feature_name = ? AND is_latest = 1",
            (feature_name,)
        )
        row = cursor.fetchone()
        if row is None:
            return None, None

        version, rel_path = row
        abs_path = os.path.join(_STORE_ROOT, '..', rel_path)
        df = pd.read_parquet(abs_path)
        return version, df
    finally:
        conn.close()


def get_version(feature_name, version):
    """Get a specific version's feature values.

    Returns DataFrame with columns [customer_id, feature_name, as_of_date].
    Returns None if version not found.
    """
    conn = _get_connection()
    try:
        cursor = conn.execute(
            "SELECT parquet_path FROM feature_registry "
            "WHERE feature_name = ? AND version = ?",
            (feature_name, version)
        )
        row = cursor.fetchone()
        if row is None:
            return None

        rel_path = row[0]
        abs_path = os.path.join(_STORE_ROOT, '..', rel_path)
        return pd.read_parquet(abs_path)
    finally:
        conn.close()


def list_versions(feature_name):
    """List all registered versions of a feature with metadata.

    Returns DataFrame of registry rows, most recent first. Empty DataFrame if none.
    """
    conn = _get_connection()
    try:
        df = pd.read_sql(
            "SELECT feature_name, version, created_at, description, source_columns, "
            "       transform_summary, business_rationale, parameters, parquet_path, is_latest "
            "FROM feature_registry "
            "WHERE feature_name = ? "
            "ORDER BY version DESC",
            conn, params=(feature_name,)
        )
        return df
    finally:
        conn.close()


def get_registry_metadata(feature_name, version):
    """Get a single version's metadata row from the registry."""
    conn = _get_connection()
    try:
        cursor = conn.execute(
            "SELECT feature_name, version, created_at, description, source_columns, "
            "       transform_summary, business_rationale, parameters, parquet_path, is_latest "
            "FROM feature_registry "
            "WHERE feature_name = ? AND version = ?",
            (feature_name, version)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        cols = ['feature_name', 'version', 'created_at', 'description', 'source_columns',
                'transform_summary', 'business_rationale', 'parameters', 'parquet_path', 'is_latest']
        return dict(zip(cols, row))
    finally:
        conn.close()