import sys
from pathlib import Path

import pandas as pd
from pymongo import MongoClient

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import MONGO_URI, MONGO_DB, USERS_CSV, ITEMS_CSV, INTERACTIONS_CSV


def check_counts(db):
    print("Document count verification of MongoDB")
    expected = {
        "users": len(pd.read_csv(USERS_CSV)),
        "items": len(pd.read_csv(ITEMS_CSV)),
        "interactions": len(pd.read_csv(INTERACTIONS_CSV)),
    }
    actual = {
        "users": db.users.count_documents({}),
        "items": db.items.count_documents({}),
        "interactions": db.interactions.count_documents({}),
    }

    all_ok = True
    print(f"\n  {'Collection':<12} {'Expected':>12} {'Actual':>12} {'Status':>10}")
    for coll in ["users", "items", "interactions"]:
        exp, act = expected[coll], actual[coll]
        status = "OK" if exp == act else "MISMATCH"
        if status != "OK":
            all_ok = False
        print(f"  {coll:<12} {exp:>12,} {act:>12,} {status:>10}")

    print()
    if all_ok:
        print("  All collections matched.")
    else:
        print("  Run load_mongo.py again.")

    return all_ok


def main():
    print("MongoDB – Count Test")

    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client[MONGO_DB]

    try:
        check_counts(db)
    finally:
        client.close()


if __name__ == "__main__":
    main()
