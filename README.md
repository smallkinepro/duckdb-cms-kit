# duckdb-cms-kit

Public CMS open data → Parquet → dbt (DuckDB) starter kit.

One-week spike deliverable: load **CMS Hospital General Information**
([`xubh-q36u`](https://data.cms.gov/provider-data/dataset/xubh-q36u)) from the
official Provider Data Catalog, write bronze Parquet + provenance, and run a
minimal dbt project (staging + hospital counts by state).

**Framing:** general analytics / public-demo only. Facility-level CMS open data.
No PHI. On-demand refresh only (no cron).

## Data owner

**Centers for Medicare & Medicaid Services (CMS)** publishes this dataset via the
[Provider Data Catalog](https://data.cms.gov/provider-data/). This kit downloads
the official CSV distribution resolved from the CMS metastore API — not an HTML
scrape. CMS remains the data owner; this repo only demonstrates local analytics.

## Quick start

```bash
git clone https://github.com/davidshimamoto/duckdb-cms-kit.git
cd duckdb-cms-kit

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 1) Ingest official CMS CSV → data/bronze/cms_hgi.parquet + provenance/
python scripts/ingest_cms_hgi.py

# 2) Configure local DuckDB profile (gitignored)
cp dbt_project/profiles.yml.example dbt_project/profiles.yml
export DBT_PROFILES_DIR="$(pwd)/dbt_project"

# 3) Build
cd dbt_project
dbt deps   # no packages required today; safe no-op if packages.yml empty
dbt build --target dev
```

## What you get

| Artifact | Description |
|----------|-------------|
| `data/bronze/cms_hgi.parquet` | Facility-grain Hospital General Information |
| `provenance/cms_hgi_*.json` | `pulled_at`, `source_url`, `sha256`, `row_count` |
| `stg_cms_hospital_general_information` | Clean snake_case staging (facility_id PK) |
| `mart_hospital_counts_by_state` | Hospital counts by state |

Query locally:

```bash
duckdb data/kit.duckdb -c "select state, hospital_count from marts.mart_hospital_counts_by_state order by hospital_count desc limit 10"
```

## Public-data ingest gate

Before treating a load as done, confirm:

1. **Public by design** — official CMS PDC dataset `xubh-q36u`
2. **No PHI** — facility-level attributes only
3. **Official endpoint** — metastore / datastore CSV (not HTML scrape)
4. **Provenance** — `pulled_at`, URL, sha256, `row_count` written under `provenance/`
5. **No secrets** — nothing sensitive in logs or commits

## Layout

```
scripts/ingest_cms_hgi.py   # metastore resolve → CSV → Parquet + provenance
data/bronze/                # gitignored Parquet (regenerate via ingest)
provenance/                 # JSON provenance (committed after a successful pull)
dbt_project/                # local DuckDB only (see profiles.yml.example)
```

## Disclaimer

This is an educational / demo starter for public CMS open data analytics. It is
**not** a clinical product, coding assistant, or quality-improvement tool.
Dataset contents and schemas are controlled by CMS and may change without notice.
Always cite CMS as the data owner when republishing derived aggregates.

## License

MIT — see [`LICENSE`](./LICENSE). CMS open data remains subject to CMS terms of use.
