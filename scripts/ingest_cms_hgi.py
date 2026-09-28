#!/usr/bin/env python3
"""Ingest CMS Hospital General Information (xubh-q36u) → bronze Parquet + provenance.

Resolves the official CSV download URL from the CMS Provider Data Catalog
metastore, snapshots the CSV, computes sha256 + row count, writes provenance
JSON, and emits Parquet under data/bronze/cms_hgi.parquet.

Usage (from repo root):
  python scripts/ingest_cms_hgi.py

Public facility-level CMS open data only — no PHI, no HTML scrape, no secrets.
Data owner: Centers for Medicare & Medicaid Services (CMS).
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import httpx

DATASET_ID = "xubh-q36u"
TITLE = "Hospital General Information"
PAGE_URL = f"https://data.cms.gov/provider-data/dataset/{DATASET_ID}"
LICENSE_NOTE = (
    "CMS Provider Data Catalog open data — facility-level public aggregates; "
    "no PHI. CMS is the data owner."
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = REPO_ROOT / "data" / "snapshots"
BRONZE_DIR = REPO_ROOT / "data" / "bronze"
PROVENANCE_DIR = REPO_ROOT / "provenance"
BRONZE_NAME = "cms_hgi.parquet"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger("ingest_cms_hgi")


def metastore_url(dataset_id: str) -> str:
    return (
        "https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items/"
        f"{dataset_id}?show-reference-ids"
    )


def resolve_csv_url(client: httpx.Client, dataset_id: str) -> tuple[str, str]:
    """Return (download_url, resolution_path). Prefer metastore distribution CSV."""
    url = metastore_url(dataset_id)
    resp = client.get(url, timeout=60.0)
    resp.raise_for_status()
    payload = resp.json()
    distributions = payload.get("distribution") or []
    for dist in distributions:
        data = dist.get("data") or dist
        download = data.get("downloadURL") or data.get("downloadUrl")
        fmt = (data.get("format") or "").lower()
        if download and (fmt in ("", "csv") or download.lower().endswith(".csv")):
            log.info("Resolved CSV via metastore (%s): %s", dataset_id, download)
            return download, "metastore"
    for dist in distributions:
        data = dist.get("data") or dist
        download = data.get("downloadURL") or data.get("downloadUrl")
        if download:
            log.info(
                "Resolved URL via metastore (non-CSV format tag) (%s): %s",
                dataset_id,
                download,
            )
            return download, "metastore"
    # Fallback: official SODA / datastore query CSV download
    fallback = (
        "https://data.cms.gov/provider-data/api/1/datastore/query/"
        f"{dataset_id}/0/download?format=csv"
    )
    log.info("Metastore had no distribution; falling back to datastore CSV: %s", fallback)
    return fallback, "datastore_query"


def download(client: httpx.Client, url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with client.stream("GET", url, timeout=300.0, follow_redirects=True) as resp:
        resp.raise_for_status()
        with dest.open("wb") as fh:
            for chunk in resp.iter_bytes(chunk_size=1024 * 256):
                fh.write(chunk)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def csv_to_parquet(csv_path: Path, parquet_path: Path) -> int:
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    try:
        csv_s = csv_path.resolve().as_posix().replace("'", "''")
        pq_s = parquet_path.resolve().as_posix().replace("'", "''")
        con.execute(
            f"""
            COPY (
              SELECT * FROM read_csv_auto('{csv_s}', header=true, all_varchar=true)
            ) TO '{pq_s}' (FORMAT PARQUET, COMPRESSION ZSTD)
            """
        )
        row_count = con.execute(
            f"SELECT count(*) FROM read_parquet('{pq_s}')"
        ).fetchone()[0]
        return int(row_count)
    finally:
        con.close()


def write_provenance(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    bronze_path = BRONZE_DIR / BRONZE_NAME
    pulled_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    date_stamp = datetime.now(timezone.utc).strftime("%Y%m%d")

    with httpx.Client(
        headers={"User-Agent": "duckdb-cms-kit/1.0 (OSS educational starter)"}
    ) as client:
        source_url, resolution = resolve_csv_url(client, DATASET_ID)
        snapshot_path = SNAPSHOT_DIR / f"cms_hgi_{date_stamp}.csv"
        log.info("Downloading %s (%s) → %s", TITLE, DATASET_ID, snapshot_path.name)
        download(client, source_url, snapshot_path)

    content_hash = sha256_file(snapshot_path)
    log.info("SHA-256: %s", content_hash)
    row_count = csv_to_parquet(snapshot_path, bronze_path)
    log.info("Wrote bronze Parquet (%s rows) → %s", row_count, bronze_path.name)

    provenance = {
        "pulled_at": pulled_at,
        "source_url": source_url,
        "page_url": PAGE_URL,
        "dataset_id": DATASET_ID,
        "title": TITLE,
        "resolution_path": resolution,
        "sha256": content_hash,
        "row_count": row_count,
        "snapshot_path": str(snapshot_path.relative_to(REPO_ROOT)),
        "bronze_path": str(bronze_path.relative_to(REPO_ROOT)),
        "license_note": LICENSE_NOTE,
        "data_owner": "Centers for Medicare & Medicaid Services (CMS)",
        "gate": {
            "public_by_design": True,
            "phi": False,
            "grain": "facility",
            "official_api_csv": True,
            "html_scrape": False,
        },
    }

    prov_dated = PROVENANCE_DIR / f"cms_hgi_{date_stamp}.json"
    write_provenance(prov_dated, provenance)
    write_provenance(PROVENANCE_DIR / "cms_hgi_latest.json", provenance)
    log.info("Provenance → %s", prov_dated.name)

    print(
        json.dumps(
            {
                "ok": True,
                "dataset_id": DATASET_ID,
                "row_count": row_count,
                "sha256": content_hash,
                "source_url": source_url,
                "bronze_path": str(bronze_path.relative_to(REPO_ROOT)),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
