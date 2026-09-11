"""
persist_cases.py — run the LOCKED matcher over all reports and write the clustering
to Postgres. Idempotent: clears prior clustering and rebuilds, so it is safe to re-run.

Locked config (see docs/DAY2_DECISIONS.md, confirmed 9 Sep 2026):
    threshold T = 0.26, recency window W = 3 days, model all-MiniLM-L6-v2.

Writes: faults, cases (occurrence_seq, opened_at, reporter_count), reports.case_id and
reports.embedding (the 384-d vector persisted as REAL[]), faults.centroid_embedding.
Does NOT route (department_id stays NULL — routing is Day 3) and does NOT score.

Usage:  set CAMPUSPULSE_DB_PASSWORD=...  then  python persist_cases.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import psycopg2
from psycopg2.extras import execute_batch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from campuspulse_intel.matcher import Matcher, ReportInput  # noqa: E402

T_LOCKED = 0.26
W_LOCKED = 3.0
MODEL = "all-MiniLM-L6-v2"


def get_conn():
    pwd = os.environ.get("CAMPUSPULSE_DB_PASSWORD")
    if pwd is None:
        sys.exit("Set CAMPUSPULSE_DB_PASSWORD.")
    return psycopg2.connect(
        host=os.environ.get("CAMPUSPULSE_DB_HOST", "localhost"),
        port=int(os.environ.get("CAMPUSPULSE_DB_PORT", "5432")),
        dbname=os.environ.get("CAMPUSPULSE_DB_NAME", "campuspulse"),
        user=os.environ.get("CAMPUSPULSE_DB_USER", "postgres"),
        password=pwd,
    )


def main():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""SELECT id, raw_text, category_id, location_id, created_at
                   FROM reports ORDER BY created_at ASC, id ASC""")
    rows = cur.fetchall()
    reports = [{"id": r[0], "text": r[1], "category_id": r[2],
                "location_id": r[3], "dt": r[4], "ts": r[4].timestamp()} for r in rows]
    id_text = {r["id"]: r["text"] for r in reports}
    id_dt = {r["id"]: r["dt"] for r in reports}
    print(f"Loaded {len(reports)} reports. Embedding with {MODEL} ...")

    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL)
    vecs = model.encode([r["text"] for r in reports], normalize_embeddings=True,
                        convert_to_numpy=True, batch_size=64).astype(np.float32)
    emb = {reports[i]["id"]: vecs[i] for i in range(len(reports))}

    # Run the locked matcher.
    m = Matcher(threshold=T_LOCKED, window_days=W_LOCKED)
    for r in reports:
        m.process(ReportInput(r["id"], emb[r["id"]], r["location_id"], r["category_id"], r["ts"]))
    print(f"Matcher produced {len(m.cases)} cases across {len(m.faults)} faults.")

    # --- clear prior clustering (idempotent). DELETE not TRUNCATE: reports FKs cases,
    #     so we null reports.case_id first, then delete case-dependent rows, then cases,
    #     then faults, then reset identities for clean demo ids. ------------------------
    cur.execute("UPDATE reports SET case_id = NULL, embedding = NULL")
    # Break cases -> scoring_records FK BEFORE deleting scoring_records, else the delete
    # violates fk_cases_current_scoring_record.
    cur.execute("UPDATE cases SET current_scoring_record_id = NULL, priority_score = NULL")
    for tbl in ("scoring_components", "scoring_records", "case_status_events", "notifications"):
        cur.execute(f"DELETE FROM {tbl}")
    cur.execute("DELETE FROM cases")
    cur.execute("DELETE FROM faults")
    cur.execute("ALTER TABLE cases  ALTER COLUMN id RESTART WITH 1")
    cur.execute("ALTER TABLE faults ALTER COLUMN id RESTART WITH 1")

    # fault first_seen = earliest opened case of that fault
    fault_first_seen = {}
    for c in m.cases:
        cur_min = fault_first_seen.get(c.fault_id)
        if cur_min is None or c.opened_ts < cur_min:
            fault_first_seen[c.fault_id] = c.opened_ts

    # --- insert faults, map matcher id -> db id ---
    fault_db = {}
    for f in m.faults:
        cur.execute(
            """INSERT INTO faults (location_id, category_id, occurrence_count,
                                   first_seen_at, centroid_embedding)
               VALUES (%s, %s, %s, %s, %s) RETURNING id""",
            (f.location_id, f.category_id, f.occurrence_count,
             datetime.fromtimestamp(fault_first_seen[f.fault_id], tz=timezone.utc),
             f.centroid.tolist()),
        )
        fault_db[f.fault_id] = cur.fetchone()[0]

    # --- insert cases, map matcher id -> db id ---
    case_db = {}
    report_case = []   # (report_id, db_case_id) for the reports update
    for c in m.cases:
        seed_id = c.member_report_ids[0]
        title = (id_text[seed_id] or "")[:120]
        cur.execute(
            """INSERT INTO cases (fault_id, occurrence_seq, location_id, category_id,
                                  status, title, reporter_count, opened_at)
               VALUES (%s, %s, %s, %s, 'NEW', %s, %s, %s) RETURNING id""",
            (fault_db[c.fault_id], c.occurrence_seq, c.location_id, c.category_id,
             title, c.n, id_dt[seed_id]),
        )
        db_id = cur.fetchone()[0]
        case_db[c.case_id] = db_id
        for rid in c.member_report_ids:
            report_case.append((rid, db_id))

    # --- update reports: case_id + persisted embedding ---
    execute_batch(
        cur,
        "UPDATE reports SET case_id = %s, embedding = %s WHERE id = %s",
        [(case_db[m.assignment[rid]], emb[rid].tolist(), rid) for rid in m.assignment],
        page_size=200,
    )

    conn.commit()
    cur.close()
    conn.close()
    print(f"Persisted: {len(m.faults)} faults, {len(m.cases)} cases, "
          f"{len(m.assignment)} reports linked + embedded.")


if __name__ == "__main__":
    main()
