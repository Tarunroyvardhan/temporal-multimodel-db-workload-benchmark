-- 8 temporal queries for the PostgreSQL benchmark

-- Q1: Trending items – top 10 items by interactions in the last 30 days
SELECT i.item_id, i.title, COUNT(*) AS interaction_count
FROM   interactions ia
JOIN   items i ON ia.item_id = i.item_id
WHERE  ia.timestamp >= 1043862590 -- max_ts - 30 days
GROUP  BY i.item_id, i.title
ORDER  BY interaction_count DESC
LIMIT  10;

-- Q2: Weekly trending – top 10 items in the last 7 days
SELECT i.item_id, i.title, COUNT(*) AS interaction_count
FROM   interactions ia
JOIN   items i ON ia.item_id = i.item_id
WHERE  ia.timestamp >= 1045849790 -- max_ts - 7 days
GROUP  BY i.item_id, i.title
ORDER  BY interaction_count DESC
LIMIT  10;

-- Q3: User recent history – all items a user interacted with in the last 90 days
SELECT i.item_id, i.title, ia.rating, ia.timestamp
FROM   interactions ia
JOIN   items i ON ia.item_id = i.item_id
WHERE  ia.user_id  = 1
  AND  ia.timestamp >= 1038678590 -- max_ts - 90 days
ORDER  BY ia.timestamp DESC;


-- Q4: New items for user – items a user saw for the very first time in last 30 days
SELECT DISTINCT i.item_id, i.title
FROM   interactions ia
JOIN   items i ON ia.item_id = i.item_id
WHERE  ia.user_id    = 1
  AND  ia.timestamp >= 1043862590 -- window start
  AND  ia.item_id NOT IN (
           SELECT item_id FROM interactions
           WHERE  user_id   = 1
             AND  timestamp < 1043862590 -- never seen before window
       )
LIMIT  10;

-- Q5: Item lifecycle – items that were "cold" early but "hot" late (cold→hot)
SELECT i.item_id, i.title,
       SUM(CASE WHEN ia.month <= 3 THEN 1 ELSE 0 END) AS early_count,
       SUM(CASE WHEN ia.month >  3 THEN 1 ELSE 0 END) AS late_count
FROM   interactions ia
JOIN   items i ON ia.item_id = i.item_id
GROUP  BY i.item_id, i.title
HAVING SUM(CASE WHEN ia.month <= 3 THEN 1 ELSE 0 END) < 100
   AND SUM(CASE WHEN ia.month >  3 THEN 1 ELSE 0 END) >= 1
ORDER  BY late_count DESC
LIMIT  10;

-- Q6: User activity trend – how many interactions a user had in each month
SELECT month, COUNT(*) AS interaction_count
FROM   interactions
WHERE  user_id = 1
GROUP  BY month
ORDER  BY month;

-- Q7: Popularity rank change – items whose rank improved the most between two windows
WITH early AS (
    SELECT item_id,
           COUNT(*) AS cnt,
           RANK() OVER (ORDER BY COUNT(*) DESC) AS rnk
    FROM   interactions
    WHERE  month BETWEEN 1 AND 2
    GROUP  BY item_id
),
late AS (
    SELECT item_id,
           COUNT(*) AS cnt,
           RANK() OVER (ORDER BY COUNT(*) DESC) AS rnk
    FROM   interactions
    WHERE  month BETWEEN 3 AND 4
    GROUP  BY item_id
)
SELECT i.item_id, i.title,
       e.rnk  AS early_rank,
       l.rnk  AS late_rank,
       (e.rnk - l.rnk) AS rank_improvement
FROM   early e
JOIN   late  l ON e.item_id = l.item_id
JOIN   items i ON e.item_id = i.item_id
ORDER  BY rank_improvement DESC
LIMIT  10;

-- Q8: Co-interaction window – items attracting the most unique users in a time window
SELECT i.item_id, i.title, COUNT(DISTINCT ia.user_id) AS unique_users
FROM   interactions ia
JOIN   items i ON ia.item_id = i.item_id
WHERE  ia.timestamp >= 1038678590 -- max_ts - 90 days
GROUP  BY i.item_id, i.title
ORDER  BY unique_users DESC
LIMIT  10;