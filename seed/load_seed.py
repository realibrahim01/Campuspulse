"""
load_seed.py — idempotent seed loader for CampusPulse.

Rebuilds the demo data from campus_reports.json against the Flyway-managed schema.
Re-runnable from scratch: it TRUNCATEs every data table (RESTART IDENTITY CASCADE)
before loading, so running it twice yields the same DB, and we can rebuild the
database as many times as we need before the 11th with one command.

  * Schema is owned by Flyway (run `mvn flyway:migrate` first). This script only
    touches DATA, never DDL.
  * Ground truth (fault_key / occurrence_id / department_true) goes ONLY into
    report_provenance — never onto `reports` — so the running pipeline can't read the
    answer key it is measured against.
  * Reports are loaded RAW: no case_id, no embedding. Clustering and scoring are a
    later stage (the intelligence service), by design.

Usage:
  set CAMPUSPULSE_DB_PASSWORD=... (your local postgres password)
  python load_seed.py --json campus_reports.json
"""

import os
import sys
import json
import argparse

import psycopg2
from psycopg2.extras import execute_values

try:
    import bcrypt
except ImportError:
    sys.exit("Missing dependency: pip install bcrypt  (see seed/requirements.txt)")

# All seed users share one demo password so judges/teammates can log in as anyone.
DEMO_PASSWORD = "campus123"

# Data tables only — flyway_schema_history is intentionally excluded so we never
# disturb the migration record.
DATA_TABLES = [
    "audit_log", "notifications", "case_status_events",
    "scoring_components", "scoring_records", "scoring_weights",
    "routing_rules", "report_provenance", "reports",
    "cases", "faults", "categories", "locations", "users", "departments",
]


def connect():
    pwd = os.environ.get("CAMPUSPULSE_DB_PASSWORD")
    if pwd is None:
        sys.exit("Set CAMPUSPULSE_DB_PASSWORD to your local postgres password.")
    return psycopg2.connect(
        host=os.environ.get("CAMPUSPULSE_DB_HOST", "localhost"),
        port=int(os.environ.get("CAMPUSPULSE_DB_PORT", "5432")),
        dbname=os.environ.get("CAMPUSPULSE_DB_NAME", "campuspulse"),
        user=os.environ.get("CAMPUSPULSE_DB_USER", "postgres"),
        password=pwd,
    )


def load(conn, data):
    ref = data["reference"]
    cur = conn.cursor()

    # 1. Wipe data (idempotent rebuild). RESTART IDENTITY resets the id sequences so
    #    ids are stable across rebuilds; CASCADE handles FK order for us.
    cur.execute(f"TRUNCATE {', '.join(DATA_TABLES)} RESTART IDENTITY CASCADE;")

    # 2. Departments -> {name: id}
    dept_id = {}
    for d in ref["departments"]:
        cur.execute(
            "INSERT INTO departments (name, sla_hours) VALUES (%s, %s) RETURNING id",
            (d["name"], d["sla_hours"]),
        )
        dept_id[d["name"]] = cur.fetchone()[0]

    # 3. Categories -> {key: id} (resolve default_department name to id)
    cat_id = {}
    for c in ref["categories"]:
        cur.execute(
            """INSERT INTO categories
                 (key, label, severity_weight, safety_flag, default_department_id)
               VALUES (%s, %s, %s, %s, %s) RETURNING id""",
            (c["key"], c["label"], c["severity_weight"], c["safety_flag"],
             dept_id[c["default_department"]]),
        )
        cat_id[c["key"]] = cur.fetchone()[0]

    # 4. Locations -> {name: id}
    loc_id = {}
    for l in ref["locations"]:
        cur.execute(
            """INSERT INTO locations (name, type, population, criticality_weight)
               VALUES (%s, %s, %s, %s) RETURNING id""",
            (l["name"], l["type"], l["population"], l["criticality_weight"]),
        )
        loc_id[l["name"]] = cur.fetchone()[0]

    # 5. Users -> {email: id}. Hash the shared demo password ONCE (bcrypt is slow);
    #    Spring Security's BCryptPasswordEncoder verifies this $2b$ hash fine.
    pw_hash = bcrypt.hashpw(DEMO_PASSWORD.encode(), bcrypt.gensalt()).decode()
    user_id = {}
    for s in ref["students"]:
        cur.execute(
            "INSERT INTO users (email, password_hash, role, display_name) "
            "VALUES (%s, %s, 'STUDENT', %s) RETURNING id",
            (s["email"], pw_hash, s["display_name"]),
        )
        user_id[s["email"]] = cur.fetchone()[0]
    for u in ref["department_users"]:
        cur.execute(
            "INSERT INTO users (email, password_hash, role, department_id, display_name) "
            "VALUES (%s, %s, 'DEPARTMENT', %s, %s) RETURNING id",
            (u["email"], pw_hash, dept_id[u["department"]], u["display_name"]),
        )
        user_id[u["email"]] = cur.fetchone()[0]
    for a in ref["admins"]:
        cur.execute(
            "INSERT INTO users (email, password_hash, role, display_name) "
            "VALUES (%s, %s, 'ADMIN', %s) RETURNING id",
            (a["email"], pw_hash, a["display_name"]),
        )
        user_id[a["email"]] = cur.fetchone()[0]

    # 6. Scoring weights (single active version).
    w = ref["scoring_weights"]
    cur.execute(
        """INSERT INTO scoring_weights
             (version_label, active, w_severity, w_people, w_recurrence,
              w_age_sla, w_location, norm_params)
           VALUES (%s, TRUE, %s, %s, %s, %s, %s, %s)""",
        (w["version_label"], w["w_severity"], w["w_people"], w["w_recurrence"],
         w["w_age_sla"], w["w_location"], json.dumps(w["norm_params"])),
    )

    # 7. Routing rules (explicit rules + a per-category catch-all so everything routes).
    for r in ref["routing_rules"]:
        cur.execute(
            """INSERT INTO routing_rules
                 (rule_order, match_category_id, match_location_type, match_keyword,
                  target_department_id, active)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (r["rule_order"],
             cat_id[r["match_category"]] if r["match_category"] else None,
             r["match_location_type"], r["match_keyword"],
             dept_id[r["target_department"]], r["active"]),
        )
    for c in ref["categories"]:
        cur.execute(
            """INSERT INTO routing_rules
                 (rule_order, match_category_id, target_department_id, active)
               VALUES (1000, %s, %s, TRUE)""",
            (cat_id[c["key"]], dept_id[c["default_department"]]),
        )

    # 8. Reports (RAW). Batch-insert, RETURNING ids in input order so we can attach
    #    provenance rows to the right report.
    report_rows = [
        (user_id[r["reporter_email"]], r["text"], cat_id[r["category_key"]],
         loc_id[r["location_name"]], r["created_at"])
        for r in data["reports"]
    ]
    ids = execute_values(
        cur,
        "INSERT INTO reports (reporter_id, raw_text, category_id, location_id, created_at) "
        "VALUES %s RETURNING id",
        report_rows, fetch=True,
    )
    report_ids = [row[0] for row in ids]

    # 9. Provenance + ground truth (separate table, never joined by the pipeline).
    meta = data["meta"]
    prov_rows = [
        (rid, meta["source"] if "source" in meta else meta["generator"],
         meta["seed_batch"], r["fault_key"], r["occurrence_id"], r["department_true"])
        for rid, r in zip(report_ids, data["reports"])
    ]
    execute_values(
        cur,
        "INSERT INTO report_provenance "
        "(report_id, source, seed_batch, gt_fault_key, gt_occurrence_id, gt_department) "
        "VALUES %s",
        prov_rows,
    )

    conn.commit()
    cur.close()
    return {
        "departments": len(dept_id), "categories": len(cat_id),
        "locations": len(loc_id), "users": len(user_id),
        "reports": len(report_ids),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="campus_reports.json")
    args = ap.parse_args()

    with open(args.json, encoding="utf-8") as fh:
        data = json.load(fh)

    conn = connect()
    try:
        counts = load(conn, data)
    finally:
        conn.close()

    print("Seed load complete (idempotent rebuild):")
    for k, v in counts.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
