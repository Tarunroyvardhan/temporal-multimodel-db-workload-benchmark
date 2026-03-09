# Helper
def _rows(result):
    """Convert a neo4j Result to a plain list of dicts."""
    return [dict(record) for record in result]


# Q1: Trending items (30d) 
def q1(session, cutoff_ts):
    """Top 10 items by interaction count since cutoff_ts (≈ last 30 days).

    Traverses only INTERACTED edges with timestamp >= cutoff_ts, groups by
    Item node, and ranks by edge count descending.
    """
    result = session.run(
        """
        MATCH (u:User)-[r:INTERACTED]->(i:Item)
        WHERE r.timestamp >= $cutoff_ts
        WITH i, count(r) AS interaction_count
        ORDER BY interaction_count DESC
        LIMIT 10
        RETURN i.item_id AS item_id, i.title AS title, interaction_count
        """,
        cutoff_ts=cutoff_ts,
    )
    return _rows(result)


# Q2: Weekly trending (7d)
def q2(session, cutoff_ts):
    """Top 10 items by interaction count since cutoff_ts (≈ last 7 days).
    Same Cypher as Q1; only the cutoff timestamp differs.
    """
    result = session.run(
        """
        MATCH (u:User)-[r:INTERACTED]->(i:Item)
        WHERE r.timestamp >= $cutoff_ts
        WITH i, count(r) AS interaction_count
        ORDER BY interaction_count DESC
        LIMIT 10
        RETURN i.item_id AS item_id, i.title AS title, interaction_count
        """,
        cutoff_ts=cutoff_ts,
    )
    return _rows(result)


# Q3: User recent history (90d)
def q3(session, user_id, cutoff_ts):
    """Items user X interacted with since cutoff_ts, newest first (limit 10).

    Starts from the specific User node (uses the unique constraint index),
    then traverses outgoing INTERACTED edges inside the time window.
    """
    result = session.run(
        """
        MATCH (u:User {user_id: $user_id})-[r:INTERACTED]->(i:Item)
        WHERE r.timestamp >= $cutoff_ts
        RETURN i.item_id  AS item_id,
               i.title    AS title,
               r.rating   AS rating,
               r.timestamp AS timestamp
        ORDER BY r.timestamp DESC
        LIMIT 10
        """,
        user_id=user_id,
        cutoff_ts=cutoff_ts,
    )
    return _rows(result)


# Q4: New items for user (first-time in window)
def q4(session, user_id, window_start):
    """Items user X interacted with for the very first time on or after window_start.

    Strategy: traverse all of user X's INTERACTED edges, group by Item,
    find the minimum timestamp per item.  If that minimum >= window_start,
    the item is new for this user within the window.
    """
    result = session.run(
        """
        MATCH (u:User {user_id: $user_id})-[r:INTERACTED]->(i:Item)
        WITH i, min(r.timestamp) AS first_seen_ts
        WHERE first_seen_ts >= $window_start
        RETURN i.item_id AS item_id, i.title AS title
        LIMIT 10
        """,
        user_id=user_id,
        window_start=window_start,
    )
    return _rows(result)


# Q5: Item lifecycle – cold → hot
def q5(session, mid_month, early_thr, late_thr):
    """Items that had few interactions early (month <= mid_month) but many late.

    CASE WHEN inside sum() mirrors the SQL CASE pattern and MongoDB $cond.
    The WHERE clause after the WITH acts as a HAVING clause on the aggregates.
    """
    result = session.run(
        """
        MATCH (u:User)-[r:INTERACTED]->(i:Item)
        WITH i,
             sum(CASE WHEN r.month <= $mid_month THEN 1 ELSE 0 END) AS early_count,
             sum(CASE WHEN r.month >  $mid_month THEN 1 ELSE 0 END) AS late_count
        WHERE early_count < $early_thr AND late_count >= $late_thr
        RETURN i.item_id AS item_id,
               i.title   AS title,
               early_count,
               late_count
        ORDER BY late_count DESC
        LIMIT 10
        """,
        mid_month=mid_month,
        early_thr=early_thr,
        late_thr=late_thr,
    )
    return _rows(result)


# Q6: User activity trend (per month)
def q6(session, user_id):
    """Interaction count per synthetic month for user X (time-series view)."""
    result = session.run(
        """
        MATCH (u:User {user_id: $user_id})-[r:INTERACTED]->(i:Item)
        WITH r.month AS month, count(r) AS interaction_count
        ORDER BY month
        RETURN month, interaction_count
        """,
        user_id=user_id,
    )
    return _rows(result)


# Q7: Popularity rank change
def q7(session, early_start, early_end, late_start, late_end):
    """Items that rose the most in popularity rank between two month windows.

    Cypher has no native RANK() window function over arbitrary aggregates,
    so we run two separate queries and assign ranks in Python – the same
    approach used for MongoDB.
    """
    # Count interactions per item in the early window
    early_counts = {
        r["item_id"]: r["cnt"]
        for r in session.run(
            """
            MATCH ()-[r:INTERACTED]->(i:Item)
            WHERE r.month >= $start AND r.month <= $end
            WITH i, count(r) AS cnt
            RETURN i.item_id AS item_id, cnt
            """,
            start=early_start,
            end=early_end,
        )
    }

    # Count interactions per item in the late window
    late_counts = {
        r["item_id"]: r["cnt"]
        for r in session.run(
            """
            MATCH ()-[r:INTERACTED]->(i:Item)
            WHERE r.month >= $start AND r.month <= $end
            WITH i, count(r) AS cnt
            RETURN i.item_id AS item_id, cnt
            """,
            start=late_start,
            end=late_end,
        )
    }

    # Assign 1-based ranks (rank 1 = most interactions)
    def rank_dict(counts):
        return {
            item_id: rank + 1
            for rank, (item_id, _) in
            enumerate(sorted(counts.items(), key=lambda x: -x[1]))
        }

    early_ranked = rank_dict(early_counts)
    late_ranked  = rank_dict(late_counts)

    # Positive improvement = item moved up in the ranking
    improvements = [
        (item_id,
         early_ranked[item_id],
         late_ranked[item_id],
         early_ranked[item_id] - late_ranked[item_id])
        for item_id in set(early_ranked) & set(late_ranked)
    ]
    improvements.sort(key=lambda x: -x[3])
    top10 = improvements[:10]

    # Fetch titles for the top 10 item_ids
    ids = [x[0] for x in top10]
    title_map = {
        r["item_id"]: r["title"]
        for r in session.run(
            "MATCH (i:Item) WHERE i.item_id IN $ids "
            "RETURN i.item_id AS item_id, i.title AS title",
            ids=ids,
        )
    }

    return [
        {
            "item_id":          item_id,
            "title":            title_map.get(item_id, ""),
            "early_rank":       er,
            "late_rank":        lr,
            "rank_improvement": imp,
        }
        for item_id, er, lr, imp in top10
    ]


# Q8: Co-interaction window
def q8(session, cutoff_ts):
    """Items that attracted the most distinct users since cutoff_ts.

    count(DISTINCT u) counts unique User nodes that traversed to each Item,
    equivalent to SQL's COUNT(DISTINCT user_id) and MongoDB's $addToSet+$size.
    """
    result = session.run(
        """
        MATCH (u:User)-[r:INTERACTED]->(i:Item)
        WHERE r.timestamp >= $cutoff_ts
        WITH i, count(DISTINCT u) AS unique_users
        ORDER BY unique_users DESC
        LIMIT 10
        RETURN i.item_id AS item_id, i.title AS title, unique_users
        """,
        cutoff_ts=cutoff_ts,
    )
    return _rows(result)
