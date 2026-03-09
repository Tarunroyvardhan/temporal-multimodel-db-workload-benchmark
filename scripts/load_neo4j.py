import sys
import time
from pathlib import Path

import pandas as pd
from neo4j import GraphDatabase
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import NEO4J_URI, NEO4J_AUTH, USERS_CSV, ITEMS_CSV, INTERACTIONS_CSV

BATCH_SIZE = 5_000


# Schema setup
def setup_schema(session):
    """Apply unique constraints and indexes.
    IF NOT EXISTS makes every statement safe to re-run.
    """
    # Unique constraints also implicitly create a lookup index on those properties
    session.run(
        "CREATE CONSTRAINT uq_user_id IF NOT EXISTS "
        "FOR (u:User) REQUIRE u.user_id IS UNIQUE"
    )
    session.run(
        "CREATE CONSTRAINT uq_item_id IF NOT EXISTS "
        "FOR (i:Item) REQUIRE i.item_id IS UNIQUE"
    )

    # Range indexes on relationship properties for temporal window queries
    session.run(
        "CREATE INDEX idx_interacted_timestamp IF NOT EXISTS "
        "FOR ()-[r:INTERACTED]-() ON (r.timestamp)"
    )
    session.run(
        "CREATE INDEX idx_interacted_month IF NOT EXISTS "
        "FOR ()-[r:INTERACTED]-() ON (r.month)"
    )

    # Node property indexes used in attribute-based lookups
    session.run(
        "CREATE INDEX idx_user_gender IF NOT EXISTS "
        "FOR (u:User) ON (u.gender)"
    )
    session.run(
        "CREATE INDEX idx_item_first_seen IF NOT EXISTS "
        "FOR (i:Item) ON (i.first_seen_month)"
    )

    print("  Constraints and indexes applied.")


# ─── Clear existing data ──────────────────────────────────────────────────────

def clear_graph(session):
    """Delete all relationships first, then all nodes.

    Relationships are removed in batches of 50,000 to avoid memory spikes.
    Once all relationships are gone, DETACH DELETE cleans up the nodes.
    """
    # Batch-delete INTERACTED relationships
    while True:
        result = session.run(
            "MATCH ()-[r:INTERACTED]->() "
            "WITH r LIMIT 50000 "
            "DELETE r "
            "RETURN count(*) AS cnt"
        )
        if result.single()["cnt"] == 0:
            break

    # Remove all remaining nodes (no relationships left, so DETACH is a no-op)
    session.run("MATCH (n) DETACH DELETE n")
    print("  Graph cleared.")


# Node loaders
def load_users(session, df):
    """MERGE all User nodes in one UNWIND batch."""
    batch = [
        {
            "user_id":int(row["user_id"]),
            "gender": row["gender"],
            "age": int(row["age"]),
            "occupation": int(row["occupation"]),
            "zip_code": str(row["zip_code"]),
        }
        for row in df.to_dict("records")
    ]
    session.run(
        """
        UNWIND $batch AS row
        MERGE (u:User {user_id: row.user_id})
        SET u.gender     = row.gender,
            u.age        = row.age,
            u.occupation = row.occupation,
            u.zip_code   = row.zip_code
        """,
        batch=batch,
    )
    print(f"  Users: {len(batch):>8,} nodes")


def load_items(session, df):
    """MERGE all Item nodes in one UNWIND batch.

    first_seen_month / last_seen_month may be NaN for items with no ratings;
    pd.notna() guards the int() cast so they are stored as null instead.
    """
    batch = []
    for row in df.to_dict("records"):
        fsm = row.get("first_seen_month")
        lsm = row.get("last_seen_month")
        batch.append({
            "item_id": int(row["item_id"]),
            "title": str(row["title"]),
            "genres": str(row["genres"]),
            "first_seen_month": int(fsm) if pd.notna(fsm) else None,
            "last_seen_month": int(lsm) if pd.notna(lsm) else None,
        })
    session.run(
        """
        UNWIND $batch AS row
        MERGE (i:Item {item_id: row.item_id})
        SET i.title            = row.title,
            i.genres           = row.genres,
            i.first_seen_month = row.first_seen_month,
            i.last_seen_month  = row.last_seen_month
        """,
        batch=batch,
    )
    print(f"  Items: {len(batch):>8,} nodes")


# Relationship loader
def load_interactions(session, df):
    """CREATE INTERACTED relationships in BATCH_SIZE chunks.

    We use CREATE because:
      - The graph was cleared before this step, so no duplicates exist.
      - MERGE on relationships must check existence first – far slower for 1M rows.

    UNWIND sends the whole batch to Neo4j in one network round-trip. The
    MATCH clauses use the unique-constraint indexes to look up each node
    efficiently before creating the relationship.
    """
    total = len(df)
    for start in tqdm(range(0, total, BATCH_SIZE), desc="  Interactions", unit="batch"):
        chunk = df.iloc[start : start + BATCH_SIZE]
        batch = [
            {
                "user_id": int(r.user_id),
                "item_id": int(r.item_id),
                "rating": float(r.rating),
                "timestamp": int(r.timestamp),
                "month": int(r.month),
            }
            for r in chunk.itertuples(index=False)
        ]
        session.run(
            """
            UNWIND $batch AS row
            MATCH (u:User {user_id: row.user_id})
            MATCH (i:Item {item_id: row.item_id})
            CREATE (u)-[:INTERACTED {
                rating:    row.rating,
                timestamp: row.timestamp,
                month:     row.month
            }]->(i)
            """,
            batch=batch,
        )
    print(f"  Relationships: {total:>8,} Interacted relationships")


# Main
def main():
    t0 = time.perf_counter()
    print("Neo4j Data Loader")

    # Read processed CSVs
    print("\nReading processed CSVs")
    users_df        = pd.read_csv(USERS_CSV, dtype={"zip_code": str})
    items_df        = pd.read_csv(ITEMS_CSV)
    interactions_df = pd.read_csv(INTERACTIONS_CSV)
    print(
        f"  {len(users_df):,} users  |  "
        f"{len(items_df):,} items  |  "
        f"{len(interactions_df):,} interactions"
    )

    # Connect to Neo4j
    print("\nConnecting to Neo4j")
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    driver.verify_connectivity()
    print(f"  Connected to {NEO4J_URI}")

    with driver.session() as session:
        # Apply schema and clear old data
        print("\nApplying schema and clearing existing data")
        setup_schema(session)
        clear_graph(session)

        # Insert data (order matters: nodes before relationships)
        print("\nInserting data")
        load_users(session, users_df)
        load_items(session, items_df)
        load_interactions(session, interactions_df)

    driver.close()
    elapsed = time.perf_counter() - t0
    print(f"\nLoad complete in:{elapsed:.1f}s")


if __name__ == "__main__":
    main()
