import sys
import time
from pathlib import Path

import pandas as pd
from pymongo import MongoClient, ASCENDING
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import MONGO_URI, MONGO_DB, USERS_CSV, ITEMS_CSV, INTERACTIONS_CSV

# Number of documents sent per insert_many call
BATCH_SIZE = 5_000

# Setup
def setup_collections(db):
    """Drop all three collections and recreate all indexes from scratch.
    Dropping is the MongoDB equivalent of PostgreSQL's DROP TABLE CASCADE.
    """
    db.users.drop()
    db.items.drop()
    db.interactions.drop()

    # users – unique lookup by user_id
    db.users.create_index([("user_id", ASCENDING)], unique=True, name="uq_users_user_id")

    # items – unique lookup by item_id, plus month-range compound index
    db.items.create_index([("item_id", ASCENDING)], unique=True, name="uq_items_item_id")
    db.items.create_index(
        [("first_seen_month", ASCENDING), ("last_seen_month", ASCENDING)],
        name="idx_items_month_range",
    )

    # interactions – all temporal query indexes (mirrors setup_indexes.js)
    db.interactions.create_index([("timestamp",  ASCENDING)], name="idx_interactions_timestamp")
    db.interactions.create_index([("month",      ASCENDING)], name="idx_interactions_month")
    db.interactions.create_index([("user_id",    ASCENDING), ("timestamp", ASCENDING)], name="idx_interactions_user_timestamp")
    db.interactions.create_index([("item_id",    ASCENDING), ("timestamp", ASCENDING)], name="idx_interactions_item_timestamp")
    db.interactions.create_index([("user_id",    ASCENDING), ("month",     ASCENDING)], name="idx_interactions_user_month")

    print("  Collections dropped and indexes created.")


# Helpers
def _nan_to_none(v):
    """Convert pandas NaN to Python None so MongoDB stores it as null."""
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


# Loaders
def load_users(db, df):
    """Insert all user documents in a single batch (6,040 docs – small)."""
    docs = [
        {
            "user_id":    int(row["user_id"]),
            "gender":     row["gender"],
            "age":        int(row["age"]),
            "occupation": int(row["occupation"]),
            "zip_code":   str(row["zip_code"]),
        }
        for row in df.to_dict("records")
    ]
    db.users.insert_many(docs, ordered=False)
    print(f"  Users: {len(docs):>8,} documents")


def load_items(db, df):
    """Insert all item documents in a single batch.
    first_seen_month / last_seen_month can be NaN for unrated movies → stored as null.
    """
    docs = []
    for row in df.to_dict("records"):
        fsm = _nan_to_none(row.get("first_seen_month"))
        lsm = _nan_to_none(row.get("last_seen_month"))
        docs.append({
            "item_id":          int(row["item_id"]),
            "title":            row["title"],
            "genres":           row["genres"],
            "first_seen_month": int(fsm) if fsm is not None else None,
            "last_seen_month":  int(lsm) if lsm is not None else None,
        })
    db.items.insert_many(docs, ordered=False)
    print(f"  Items: {len(docs):>8,} documents")


def load_interactions(db, df):
    """Insert interactions in batches of BATCH_SIZE documents.
    ordered=False allows MongoDB to continue inserting other batches if one
    document fails (mirrors PostgreSQL's ON CONFLICT DO NOTHING behaviour).
    """
    total = len(df)
    for start in tqdm(range(0, total, BATCH_SIZE), desc="  Interactions", unit="batch"):
        chunk = df.iloc[start : start + BATCH_SIZE]
        docs = [
            {
                "user_id":   int(r.user_id),
                "item_id":   int(r.item_id),
                "rating":    float(r.rating),
                "timestamp": int(r.timestamp),
                "month":     int(r.month),
            }
            for r in chunk.itertuples(index=False)
        ]
        db.interactions.insert_many(docs, ordered=False)
    print(f"  Interactions: {total:>8,} documents")


# Main
def main():
    t0 = time.perf_counter()
    print("MongoDB – Data Loader")

    # Read processed CSVs
    print("\nReading processed CSVs")
    users_df        = pd.read_csv(USERS_CSV, dtype={"zip_code": str})
    items_df        = pd.read_csv(ITEMS_CSV)
    interactions_df = pd.read_csv(INTERACTIONS_CSV)
    print(
        f"  {len(users_df):,} users, "
        f"{len(items_df):,} items, "
        f"{len(interactions_df):,} interactions"
    )

    # Connect to MongoDB
    print("\nConnecting to MongoDB")
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client[MONGO_DB]
    print(f"  Connected to {MONGO_DB}")

    # Drop collections and recreate indexes
    print("\nSetting up collections and indexes")
    setup_collections(db)

    # Insert data
    print("\nInserting data")
    load_users(db, users_df)
    load_items(db, items_df)
    load_interactions(db, interactions_df)

    client.close()
    elapsed = time.perf_counter() - t0
    print(f"\nCompleted: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
