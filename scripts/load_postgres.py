import sys
import time
from pathlib import Path

import pandas as pd
import psycopg2
import psycopg2.extras
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import PG_CONN_DICT, USERS_CSV, ITEMS_CSV, INTERACTIONS_CSV

# Path to the schema DDL file
SCHEMA_SQL = Path(__file__).parent.parent / "db" / "postgres" / "schema.sql"

# Number of rows sent to the DB per INSERT statement
BATCH_SIZE = 5_000


# Schema 
def apply_schema(conn):
    """Run schema.sql: drops and recreates all tables + indexes."""
    sql = SCHEMA_SQL.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    print("  Schema applied (tables + indexes created).")


# Loaders
def load_users(conn, df):
    """Bulk-insert all user rows. ON CONFLICT DO NOTHING = safe to re-run."""
    rows = [
        (int(r.user_id), r.gender, int(r.age), int(r.occupation), str(r.zip_code))
        for r in df.itertuples(index=False)
    ]
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            "INSERT INTO users (user_id, gender, age, occupation, zip_code) "
            "VALUES %s ON CONFLICT DO NOTHING",
            rows,
            page_size=BATCH_SIZE,
        )
    conn.commit()
    print(f"  Users: {len(rows):>8,} rows")


def load_items(conn, df):
    """Bulk-insert all item rows.
    Movies that were never rated have NaN months → stored as SQL NULL.
    """
    def _int_or_none(v):
        return None if pd.isna(v) else int(v)

    rows = [
        (
            int(r.item_id),
            r.title,
            r.genres,
            _int_or_none(r.first_seen_month),
            _int_or_none(r.last_seen_month),
        )
        for r in df.itertuples(index=False)
    ]
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            "INSERT INTO items (item_id, title, genres, first_seen_month, last_seen_month) "
            "VALUES %s ON CONFLICT DO NOTHING",
            rows,
            page_size=BATCH_SIZE,
        )
    conn.commit()
    print(f"  Items: {len(rows):>8,} rows")


def load_interactions(conn, df):
    """Bulk-insert interactions in batches of BATCH_SIZE rows.
    Each batch is committed separately so progress is not lost on failure.
    """
    # Build a plain list of tuples once (faster than per-row access)
    rows = list(
        df[["user_id", "item_id", "rating", "timestamp", "month"]]
        .itertuples(index=False, name=None)
    )

    with conn.cursor() as cur:
        for start in tqdm(range(0, len(rows), BATCH_SIZE), desc="  Interactions", unit="batch"):
            batch = rows[start : start + BATCH_SIZE]
            psycopg2.extras.execute_values(
                cur,
                "INSERT INTO interactions (user_id, item_id, rating, timestamp, month) VALUES %s",
                batch,
                page_size=BATCH_SIZE,
            )
            conn.commit()

    print(f"  Interactions: {len(rows):>8,} rows")


# Main
def main():
    t0 = time.perf_counter()
    print("PostgreSQL – Data Loader")

    # Read the three processed CSVs produced by prepare_data.py
    print("\nReading processed CSVs")
    users_df        = pd.read_csv(USERS_CSV, dtype={"zip_code": str})
    items_df        = pd.read_csv(ITEMS_CSV)
    interactions_df = pd.read_csv(INTERACTIONS_CSV)
    print(
        f"  {len(users_df):,} users  |  "
        f"{len(items_df):,} items  |  "
        f"{len(interactions_df):,} interactions"
    )

    # Open db connection
    print("\nConnecting to PostgreSQL")
    conn = psycopg2.connect(**PG_CONN_DICT)
    print(f"  Connected to {PG_CONN_DICT['host']}:{PG_CONN_DICT['port']} / {PG_CONN_DICT['dbname']}")

    try:
        # Apply schema (drops existing tables first)
        print("\nApplying schema")
        apply_schema(conn)

        # Insert data in foreign key safe order
        print("\nInserting data")
        load_users(conn, users_df)
        load_items(conn, items_df)
        load_interactions(conn, interactions_df)

    finally:
        conn.close()

    elapsed = time.perf_counter() - t0
    print(f"\nLoad complete in {elapsed:.1f}s")
    

if __name__ == "__main__":
    main()
