"""
score_cases.py — score every case and persist the breakdown (Part C).

Writes are APPEND-ONLY: each run inserts a NEW scoring_record per case plus its
scoring_components; it never mutates an existing record. cases.priority_score and
cases.current_scoring_record_id are updated to point at the latest. An audit_log
SCORE_COMPUTED row is written per case so the decision is on the cross-cutting trail.

--dry-run   compute and print, write nothing (use to prove determinism)
--as-of ISO fixed timestamp for the age input (default: now, UTC)

Usage:  set CAMPUSPULSE_DB_PASSWORD=...  then  python score_cases.py
"""

from __future__ import annotations

import os
import sys
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import Json

sys.path.insert(0, str(Path(__file__).resolve().parent))
from campuspulse_intel.scoring import score_case  # noqa: E402


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


def load_weights(cur):
    cur.execute("""SELECT id, w_severity, w_people, w_recurrence, w_age_sla,
                          w_location, norm_params
                   FROM scoring_weights WHERE active = TRUE
                   ORDER BY id DESC LIMIT 1""")
    row = cur.fetchone()
    if not row:
        sys.exit("No active scoring_weights row.")
    return row[0], {
        "w_severity": float(row[1]), "w_people": float(row[2]),
        "w_recurrence": float(row[3]), "w_age_sla": float(row[4]),
        "w_location": float(row[5]),
        "norm_params": row[6] if isinstance(row[6], dict) else json.loads(row[6]),
    }


def load_case_facts(cur):
    # SLA comes from the routed department if present, else the category's default
    # department (the expected owner) — routing is Day 3, but scoring needs an SLA now.
    cur.execute("""
        SELECT c.id, c.occurrence_seq, c.reporter_count, c.opened_at,
               cat.severity_weight, cat.safety_flag,
               loc.population, loc.criticality_weight,
               COALESCE(dep.sla_hours, ddep.sla_hours) AS sla_hours
        FROM cases c
        JOIN categories cat ON cat.id = c.category_id
        JOIN locations  loc ON loc.id = c.location_id
        LEFT JOIN departments dep  ON dep.id  = c.department_id
        LEFT JOIN departments ddep ON ddep.id = cat.default_department_id
        ORDER BY c.id
    """)
    facts = []
    for r in cur.fetchall():
        facts.append({
            "case_id": r[0], "occurrence_seq": r[1], "reporter_count": r[2],
            "opened_at": r[3], "severity_weight": r[4], "safety_flag": r[5],
            "population": r[6], "criticality_weight": r[7], "sla_hours": r[8],
        })
    return facts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--fresh", action="store_true",
                    help="clear prior scoring rows before writing (clean re-score)")
    ap.add_argument("--as-of", default=None, help="ISO timestamp for the age input")
    ap.add_argument("--template-version", default="score-v1")
    args = ap.parse_args()

    as_of = (datetime.fromisoformat(args.as_of) if args.as_of
             else datetime.now(timezone.utc))
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)

    conn = get_conn()
    cur = conn.cursor()
    weights_id, weights = load_weights(cur)
    facts = load_case_facts(cur)
    print(f"Scoring {len(facts)} cases  (weights v{weights_id}, as_of={as_of.isoformat()})"
          + ("  [DRY RUN]" if args.dry_run else ""))

    results = []
    for f in facts:
        res = score_case(f, weights, as_of)
        results.append((f["case_id"], res))

    if args.dry_run:
        top = sorted(results, key=lambda x: x[1].total_score, reverse=True)[:8]
        print("\nTop 8 by priority (dry run):")
        for cid, res in top:
            parts = " ".join(f"{c.input_name}={c.contribution:.1f}" for c in res.components)
            print(f"  case {cid:>3}  total={res.total_score:6.2f}  | {parts}")
        conn.rollback(); conn.close()
        return

    if args.fresh:
        # Clean re-score: drop prior scoring rows so we don't append duplicates.
        cur.execute("UPDATE cases SET priority_score = NULL, current_scoring_record_id = NULL")
        cur.execute("DELETE FROM scoring_components")
        cur.execute("DELETE FROM scoring_records")
        cur.execute("DELETE FROM audit_log WHERE action = 'SCORE_COMPUTED'")

    for case_id, res in results:
        cur.execute(
            """INSERT INTO scoring_records
                 (case_id, weights_version_id, total_score, explanation_template_version,
                  computed_at)
               VALUES (%s, %s, %s, %s, %s) RETURNING id""",
            (case_id, weights_id, res.total_score, args.template_version, as_of),
        )
        record_id = cur.fetchone()[0]
        for c in res.components:
            cur.execute(
                """INSERT INTO scoring_components
                     (scoring_record_id, input_name, raw_value, normalized_value,
                      weight, contribution)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (record_id, c.input_name, Json(c.raw_value), c.normalized_value,
                 c.weight, c.contribution),
            )
        cur.execute(
            "UPDATE cases SET priority_score = %s, current_scoring_record_id = %s WHERE id = %s",
            (res.total_score, record_id, case_id),
        )
        cur.execute(
            """INSERT INTO audit_log (actor_id, action, entity_type, entity_id, after_json, reason)
               VALUES (NULL, 'SCORE_COMPUTED', 'case', %s, %s, %s)""",
            (case_id, Json({"total_score": res.total_score, "scoring_record_id": record_id,
                            "weights_version_id": weights_id}),
             f"scored under weights v{weights_id}"),
        )

    conn.commit()
    cur.close()
    conn.close()
    print(f"Wrote {len(results)} scoring_records (+ components + audit). "
          f"cases.priority_score updated.")


if __name__ == "__main__":
    main()
