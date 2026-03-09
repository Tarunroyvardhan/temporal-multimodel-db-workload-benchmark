import sys
from pathlib import Path

import pandas as pd
from neo4j import GraphDatabase

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import NEO4J_URI, NEO4J_AUTH, USERS_CSV, ITEMS_CSV, INTERACTIONS_CSV


def check_counts(session):
    """Compare Neo4j node/relationship counts to source CSV row counts."""
    print("Graph count verification:")

    expected = {
        "User nodes": len(pd.read_csv(USERS_CSV)),
        "Item nodes": len(pd.read_csv(ITEMS_CSV)),
        "INTERACTED rels": len(pd.read_csv(INTERACTIONS_CSV)),
    }
    actual = {
        "User nodes": session.run("MATCH (u:User) RETURN count(u) AS cnt").single()["cnt"],
        "Item nodes": session.run("MATCH (i:Item) RETURN count(i) AS cnt").single()["cnt"],
        "INTERACTED rels": session.run("MATCH ()-[r:INTERACTED]->() RETURN count(r) AS cnt").single()["cnt"],
    }

    all_ok = True
    print(f"\n  {'Entity':<20} {'Expected':>12} {'Actual':>12} {'Status':>10}")
    print(f"  {'-'*20} {'-'*12} {'-'*12} {'-'*10}")

    for entity in expected:
        exp, act = expected[entity], actual[entity]
        status = "Ok" if exp == act else "Not matched"
        if status != "Ok":
            all_ok = False
        print(f"  {entity:<20} {exp:>12,} {act:>12,} {status:>10}")

    print()
    if all_ok:
        print("  Graph matches source data.")
    else:
        print("  Re-run load_neo4j.py")

    return all_ok


def main():
    print("Neo4j – Count Test")

    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    try:
        with driver.session() as session:
            check_counts(session)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
