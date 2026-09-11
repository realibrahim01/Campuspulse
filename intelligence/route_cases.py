"""
route_cases.py — assign each case to a responsible department (Day 3).

Deterministic rule engine over the seeded `routing_rules`, evaluated in `rule_order`:
a rule matches when its category (if set), location type (if set) and keyword (if set,
found in the case title) all match. The first matching rule wins; a per-category
catch-all at rule_order 1000 guarantees every case routes. Sets cases.department_id and
cases.sla_due_at (opened_at + department SLA), and logs ROUTE_ASSIGNED to audit_log.

No ML classification (out of scope) — routing is transparent, configurable rules, exactly
what the "configurable per institution" limitation promises.

Then it MEASURES routing accuracy against gt_department from report_provenance (read only
here, never used to route). Idempotent: re-running re-routes and replaces ROUTE_ASSIGNED
audit rows.

Usage:  set CAMPUSPULSE_DB_PASSWORD=...  then  python route_cases.py
"""

from __future__ import annotations

import os
import sys
from datetime import timedelta

import psycopg2
from psycopg2.extras import Json


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


def match(rule, category_id, loc_type, title_lower):
    _order, m_cat, m_loc_type, m_kw, _target = rule
    if m_cat is not None and m_cat != category_id:
        return False
    if m_loc_type is not None and m_loc_type != loc_type:
        return False
    if m_kw is not None and m_kw.lower() not in title_lower:
        return False
    return True


def main():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""SELECT rule_order, match_category_id, match_location_type,
                          match_keyword, target_department_id
                   FROM routing_rules WHERE active ORDER BY rule_order""")
    rules = cur.fetchall()
    cur.execute("SELECT id, sla_hours FROM departments")
    sla = dict(cur.fetchall())

    cur.execute("""SELECT c.id, c.category_id, c.title, c.opened_at, loc.type
                   FROM cases c JOIN locations loc ON loc.id = c.location_id
                   ORDER BY c.id""")
    cases = cur.fetchall()

    # Idempotent re-route: clear prior automatic assignments from the audit trail
    # (manual ROUTE_OVERRIDE rows are preserved).
    cur.execute("DELETE FROM audit_log WHERE action = 'ROUTE_ASSIGNED'")

    routed = 0
    for case_id, category_id, title, opened_at, loc_type in cases:
        title_lower = (title or "").lower()
        target = None
        matched_order = None
        for rule in rules:
            if match(rule, category_id, loc_type, title_lower):
                target = rule[4]
                matched_order = rule[0]
                break
        if target is None:
            continue  # shouldn't happen given the catch-all
        sla_due = opened_at + timedelta(hours=sla[target])
        cur.execute("UPDATE cases SET department_id = %s, sla_due_at = %s WHERE id = %s",
                    (target, sla_due, case_id))
        cur.execute(
            """INSERT INTO audit_log (actor_id, action, entity_type, entity_id, after_json, reason)
               VALUES (NULL, 'ROUTE_ASSIGNED', 'case', %s, %s, %s)""",
            (case_id, Json({"department_id": target, "matched_rule_order": matched_order}),
             f"matched routing rule #{matched_order}"),
        )
        routed += 1

    conn.commit()
    print(f"Routed {routed}/{len(cases)} cases.\n")

    # --- measure accuracy vs ground truth (gt_department, read only here) ---
    cur.execute("""
        WITH case_gt AS (
            SELECT c.id, dep.name AS routed_dept,
                   mode() WITHIN GROUP (ORDER BY p.gt_department) AS gt_dept
            FROM cases c
            JOIN departments dep ON dep.id = c.department_id
            JOIN reports r ON r.case_id = c.id
            JOIN report_provenance p ON p.report_id = r.id
            GROUP BY c.id, dep.name
        )
        SELECT count(*) total,
               count(*) FILTER (WHERE routed_dept = gt_dept) correct
        FROM case_gt
    """)
    total, correct = cur.fetchone()
    print(f"Routing accuracy vs gt_department: {correct}/{total} = {correct/total:.1%}")

    cur.execute("""
        WITH case_gt AS (
            SELECT c.id, dep.name AS routed_dept,
                   mode() WITHIN GROUP (ORDER BY p.gt_department) AS gt_dept
            FROM cases c
            JOIN departments dep ON dep.id = c.department_id
            JOIN reports r ON r.case_id = c.id
            JOIN report_provenance p ON p.report_id = r.id
            GROUP BY c.id, dep.name
        )
        SELECT routed_dept, gt_dept, count(*) n
        FROM case_gt WHERE routed_dept <> gt_dept
        GROUP BY routed_dept, gt_dept ORDER BY n DESC
    """)
    misses = cur.fetchall()
    if misses:
        print("\nMisroutes (routed -> should-be):")
        for routed_dept, gt_dept, n in misses:
            print(f"  {n:>2}  {routed_dept}  ->  {gt_dept}")

    cur.execute("""SELECT dep.name, count(*) FROM cases c
                   JOIN departments dep ON dep.id = c.department_id
                   GROUP BY dep.name ORDER BY count(*) DESC""")
    print("\nCase load by department:")
    for name, n in cur.fetchall():
        print(f"  {n:>2}  {name}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
