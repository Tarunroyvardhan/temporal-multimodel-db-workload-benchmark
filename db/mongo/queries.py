# 8 temporal queries for the MongoDB benchmark

# Q1: Trending items (30d)
def q1(db, cutoff_ts):
    """Top 10 items by interaction count in the last 30 days."""
    pipeline = [
        # Keep only interactions inside the time window
        {"$match": {"timestamp": {"$gte": cutoff_ts}}},
        # Count interactions per item
        {"$group": {"_id": "$item_id", "interaction_count": {"$sum": 1}}},
        {"$sort": {"interaction_count": -1}},
        {"$limit": 10},
        # Join to items collection to get title
        {"$lookup": {
            "from": "items", "localField": "_id",
            "foreignField": "item_id", "as": "item_doc"
        }},
        {"$unwind": "$item_doc"},
        {"$project": {
            "_id": 0, "item_id": "$_id",
            "title": "$item_doc.title", "interaction_count": 1
        }},
    ]
    return list(db.interactions.aggregate(pipeline))


# Q2: Weekly trending (7d)
def q2(db, cutoff_ts):
    """Top 10 items by interaction count in the last 7 days.
    Same pipeline as Q1 – called with a tighter cutoff_ts.
    """
    pipeline = [
        {"$match": {"timestamp": {"$gte": cutoff_ts}}},
        {"$group": {"_id": "$item_id", "interaction_count": {"$sum": 1}}},
        {"$sort": {"interaction_count": -1}},
        {"$limit": 10},
        {"$lookup": {
            "from": "items", "localField": "_id",
            "foreignField": "item_id", "as": "item_doc"
        }},
        {"$unwind": "$item_doc"},
        {"$project": {
            "_id": 0, "item_id": "$_id",
            "title": "$item_doc.title", "interaction_count": 1
        }},
    ]
    return list(db.interactions.aggregate(pipeline))


# Q3: User recent history (90d)
def q3(db, user_id, cutoff_ts):
    """Items user X interacted with in the last 90 days, newest first."""
    pipeline = [
        {"$match": {"user_id": user_id, "timestamp": {"$gte": cutoff_ts}}},
        {"$sort": {"timestamp": -1}},
        {"$limit": 10},
        {"$lookup": {
            "from": "items", "localField": "item_id",
            "foreignField": "item_id", "as": "item_doc"
        }},
        # preserveNullAndEmptyArrays keeps interactions whose item_id has no match
        {"$unwind": {"path": "$item_doc", "preserveNullAndEmptyArrays": True}},
        {"$project": {
            "_id": 0, "item_id": 1, "rating": 1, "timestamp": 1,
            "title": "$item_doc.title"
        }},
    ]
    return list(db.interactions.aggregate(pipeline))


# Q4: New items for user (30d, first-time) ─────────────────────────────────
def q4(db, user_id, window_start):
    """Items user X first EVER touched on or after window_start.

    Strategy: group all of user X's interactions by item_id and take
    the minimum timestamp per item.  If that minimum is >= window_start,
    the user never saw the item before the window – it is 'new'.
    """
    pipeline = [
        # Restrict to this user only
        {"$match": {"user_id": user_id}},
        # Earliest interaction per item (across all time)
        {"$group": {"_id": "$item_id", "first_seen_ts": {"$min": "$timestamp"}}},
        # Keep only items first touched inside the window
        {"$match": {"first_seen_ts": {"$gte": window_start}}},
        {"$limit": 10},
        {"$lookup": {
            "from": "items", "localField": "_id",
            "foreignField": "item_id", "as": "item_doc"
        }},
        {"$unwind": {"path": "$item_doc", "preserveNullAndEmptyArrays": True}},
        {"$project": {"_id": 0, "item_id": "$_id", "title": "$item_doc.title"}},
    ]
    return list(db.interactions.aggregate(pipeline))


# Q5: Item lifecycle – cold → hot
def q5(db, mid_month, early_thr, late_thr):
    """Items with few interactions early (months <= mid_month) but many late.

    $cond inside $sum acts like SQL's CASE WHEN: each document contributes
    1 to either early_count or late_count depending on its month value.
    """
    pipeline = [
        {"$group": {
            "_id": "$item_id",
            # Add 1 to early bucket if month is in early half
            "early_count": {"$sum": {"$cond": [{"$lte": ["$month", mid_month]}, 1, 0]}},
            # Add 1 to late bucket otherwise
            "late_count":  {"$sum": {"$cond": [{"$gt":  ["$month", mid_month]}, 1, 0]}},
        }},
        {"$match": {
            "early_count": {"$lt": early_thr},   # was cold
            "late_count":  {"$gte": late_thr},   # became warm/hot
        }},
        {"$sort": {"late_count": -1}},
        {"$limit": 10},
        {"$lookup": {
            "from": "items", "localField": "_id",
            "foreignField": "item_id", "as": "item_doc"
        }},
        {"$unwind": "$item_doc"},
        {"$project": {
            "_id": 0, "item_id": "$_id",
            "title": "$item_doc.title", "early_count": 1, "late_count": 1
        }},
    ]
    return list(db.interactions.aggregate(pipeline))


# Q6: User activity trend (per month) 
def q6(db, user_id):
    """Number of interactions user X had in each synthetic month (time series)."""
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": "$month", "interaction_count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
        # Rename _id → month in the output
        {"$project": {"_id": 0, "month": "$_id", "interaction_count": 1}},
    ]
    return list(db.interactions.aggregate(pipeline))


# Q7: Popularity rank change 
def q7(db, early_start, early_end, late_start, late_end):
    """Items that rose the most in popularity rank between two month windows.

    MongoDB lacks a native RANK() window function for aggregations (without
    $setWindowFields on very new versions), so ranking is done in Python
    after two separate aggregation calls – one per window.
    """
    # Count interactions per item in the early window
    early_counts = {
        r["_id"]: r["cnt"]
        for r in db.interactions.aggregate([
            {"$match": {"month": {"$gte": early_start, "$lte": early_end}}},
            {"$group": {"_id": "$item_id", "cnt": {"$sum": 1}}},
        ])
    }

    # Count interactions per item in the late window
    late_counts = {
        r["_id"]: r["cnt"]
        for r in db.interactions.aggregate([
            {"$match": {"month": {"$gte": late_start, "$lte": late_end}}},
            {"$group": {"_id": "$item_id", "cnt": {"$sum": 1}}},
        ])
    }

    # Assign rank: sort by count descending; rank 1 = most popular
    def rank_dict(counts):
        return {
            item_id: rank + 1
            for rank, (item_id, _) in enumerate(
                sorted(counts.items(), key=lambda x: -x[1])
            )
        }

    early_ranked = rank_dict(early_counts)
    late_ranked  = rank_dict(late_counts)

    # rank_improvement > 0 means the item climbed in the ranking
    improvements = [
        (item_id,
         early_ranked[item_id], late_ranked[item_id],
         early_ranked[item_id] - late_ranked[item_id])
        for item_id in set(early_ranked) & set(late_ranked)
    ]
    improvements.sort(key=lambda x: -x[3])
    top10 = improvements[:10]

    # Fetch titles for the top 10
    ids = [x[0] for x in top10]
    title_map = {
        d["item_id"]: d["title"]
        for d in db.items.find(
            {"item_id": {"$in": ids}},
            {"item_id": 1, "title": 1, "_id": 0},
        )
    }

    return [
        {
            "item_id": item_id,
            "title":   title_map.get(item_id, ""),
            "early_rank": er, "late_rank": lr, "rank_improvement": imp,
        }
        for item_id, er, lr, imp in top10
    ]


# Q8: Co-interaction window
def q8(db, cutoff_ts):
    """Items that attracted the most distinct users in the given time window.

    $addToSet collects unique user_ids per item (automatic deduplication).
    $size then converts that set to a count.
    """
    pipeline = [
        {"$match": {"timestamp": {"$gte": cutoff_ts}}},
        # Collect all unique user_ids per item into a set
        {"$group": {"_id": "$item_id", "user_set": {"$addToSet": "$user_id"}}},
        # Replace the set array with its length
        {"$addFields": {"unique_users": {"$size": "$user_set"}}},
        {"$sort": {"unique_users": -1}},
        {"$limit": 10},
        {"$lookup": {
            "from": "items", "localField": "_id",
            "foreignField": "item_id", "as": "item_doc"
        }},
        {"$unwind": "$item_doc"},
        {"$project": {
            "_id": 0, "item_id": "$_id",
            "title": "$item_doc.title", "unique_users": 1
        }},
    ]
    return list(db.interactions.aggregate(pipeline))
