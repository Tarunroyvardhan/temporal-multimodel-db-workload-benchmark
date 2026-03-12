import sys
from pathlib import Path

import pandas as pd
import psycopg2

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import PG_CONN_DICT, USERS_CSV, ITEMS_CSV, INTERACTIONS_CSV



def scalar(conn, sql):
    """Return a single value from a query."""
    with conn.cursor() as cur:
        cur.execute(sql)
        row = cur.fetchone()
        return row[0] if row else None


def check_counts(conn):
    print("PostgreSQL – Row count verification")

    # Expected counts from the source CSVs
    expected = {
        "users": len(pd.read_csv(USERS_CSV)),
        "items": len(pd.read_csv(ITEMS_CSV)),
        "interactions": len(pd.read_csv(INTERACTIONS_CSV)),
    }
    print(f"\n  Expected row counts (from CSV files):") 
    for table in ["users", "items", "interactions"]:
        exp = expected[table]
        print(f"  {table}: {exp}")

    # Actual counts from PostgreSQL
    actual = {
        "users": scalar(conn, "SELECT COUNT(*) FROM users"),
        "items": scalar(conn, "SELECT COUNT(*) FROM items"),
        "interactions": scalar(conn, "SELECT COUNT(*) FROM interactions"),
    }

    print(f"\n  Actual row counts (from PostgreSQL):") 
    for table in ["users", "items", "interactions"]:
        act = actual[table]
        print(f"  {table}: {act}")

    all_ok = True
    print(f"\n  {'Table':<15} {'Expected':>12} {'Actual':>12} {'Status':>8}")
    print(f"  {'-'*15} {'-'*12} {'-'*12} {'-'*8}")
    for table in ["users", "items", "interactions"]:
        exp = expected[table]
        act = actual[table]
        ok  = "OK" if exp == act else "MISMATCH"
        if ok != "OK":
            all_ok = False
        print(f"  {table:<15} {exp:>12,} {act:>12,} {ok:>8}")

    print()
    if all_ok:
        print("  COUNT check – All tables match.")
    else:
        print("  COUNT check failed – re-run load_postgres.py")
    return all_ok


def main():
    conn = psycopg2.connect(**PG_CONN_DICT)
    try:
        check_counts(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
