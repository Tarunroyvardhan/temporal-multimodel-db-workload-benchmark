# Performance Analysis of Diverse Database Systems on Temporal Workloads

A benchmarking framework that evaluates **PostgreSQL**, **MongoDB**, and **Neo4j** on time-evolving recommendation workloads using the [MovieLens 1M](https://grouplens.org/datasets/movielens/1m/) dataset using temporal queries.

---

## Project Goal

Study how different database models behave when recommendation data grows over time and when queries are explicitly time-aware. Instead of a static snapshot, we simulate **12 monthly time steps**, appending data incrementally and measuring query performance at each step, using relational, document, and graph database.

---

## Tech Stack

| Layer | Choice |
|-------|--------|
| Language | Python 3.10+ |
| Relational DB | PostgreSQL 15 (via Docker) |
| Document DB | MongoDB 7 (via Docker) |
| Graph DB | Neo4j 5 (via Docker) |
| Orchestration | Docker Compose |
| Data | MovieLens 1M |
| Analysis | Pandas, Matplotlib, Seaborn |

---

## Repository Structure

```
├── data/
│   ├── raw/                  # Downloaded MovieLens files (not committed)
│   └── processed/            # Cleaned CSVs produced by prepare_data.py
├── db/
│   ├── postgres/             # schema.sql, queries.sql
│   ├── mongo/                # setup_indexes.js, queries.js
│   └── neo4j/                # schema.cypher, queries.cypher
├── scripts/
│   ├── prepare_data.py       # Preprocess MovieLens → interactions_12m.csv
│   ├── test_*_connection.py  # Verify DB connectivity
│   ├── load_postgres.py      # Bulk-load data into PostgreSQL
│   ├── load_mongo.py         # Bulk-load data into MongoDB
│   ├── load_neo4j.py         # Bulk-load data into Neo4j
│   ├── check_counts.py       # Cross-validate row counts across all DBs
│   ├── test_postgres.py      # Check if data loaded successfully
│   ├── test_mongo.py         # Check if data loaded successfully
│   ├── test_neo4j.py         # Check if data loaded successfully
│   ├── benchmark_temporal.py # Main benchmark driver (12 time steps × 3 DBs × 8 queries)
│   └── analyze_results.py    # Read CSV results → plots + summary
├── notebooks/                # Optional Jupyter notebooks for exploration
├── results/
│   └── benchmark_results.csv # Output of benchmark_temporal.py
├── plots/                    # Plots produced by analyze_results.py
├── docs/
│   ├── temporal_queries.md   # Query definitions and rationale
│   ├── schema_overview.md    # Schema design decisions
│   └── results_summary.md    # Findings per query
├── .env                      # Local connection strings (not committed)
├── .env.example              # Template for .env
├── config.py                 # Loads .env and exposes connection objects
├── docker-compose.yml        # Defines postgres, mongodb, neo4j services
├── requirements.txt          # Python dependencies
└── README.md
```

---

## Quick Start

### 1. Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- Python 3.10+
- MovieLens 1M dataset downloaded to `data/raw/`

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env and set passwords if desired
```

### 4. Start databases

```bash
docker-compose up -d
```

### 5. Test connections

```bash
python scripts/test_postgres_connection.py
python scripts/test_mongo_connection.py
python scripts/test_neo4j_connection.py
```

### 6. Prepare data

```bash
python scripts/prepare_data.py
```

### 7. Load data into all databases

```bash
python scripts/load_postgres.py
python scripts/load_mongo.py
python scripts/load_neo4j.py
```

### 8. Run benchmark

```bash
python scripts/benchmark_temporal.py
```

### 9. Analyse results

```bash
python scripts/analyze_results.py
# Plots saved to plots/, summary in docs/results_summary.md
```

---

## Temporal Query Suite (Q1–Q8)

| ID | Name | Description |
|----|------|-------------|
| Q1 | Trending items (30d) | Top 10 items by interaction count in last 30 days |
| Q2 | Weekly trending (7d) | Top 10 items by interaction count in last 7 days |
| Q3 | User recent history | All items user X interacted with in last 90 days |
| Q4 | New items for user | Items user X interacted with in last 30 days, first time ever |
| Q5 | Item lifecycle | Items with low early activity but high late activity (cold→hot) |
| Q6 | User activity trend | Interactions per month for user X (time series) |
| Q7 | Popularity change | Items whose rank improved most between two windows |
| Q8 | Co-interaction window | Users who interacted with the same item within a time window |

---

