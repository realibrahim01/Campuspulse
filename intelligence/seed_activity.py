"""
seed_activity.py — synthetic acknowledgement history for the admin pattern dashboard.

The "median time to acknowledge" view needs cases that were acknowledged some time after
they opened. The seed dataset is historical but has no activity, so this script creates a
deterministic slice of it: ~70% of cases get a NEW -> ASSIGNED status event at
`opened_at + a per-department delay`, and the case status is set to ASSIGNED. The remaining
~30% stay NEW (a realistic unacknowledged backlog).

Per-department median delays differ so departments rank meaningfully. This is synthetic
demo activity, in the same spirit as the synthetic reports — stated openly, not hidden.
Deterministic (seeded), idempotent (removes its own prior events, tagged 'seed-activity').

Run AFTER route_cases.py (needs department_id set). Usage:
  set CAMPUSPULSE_DB_PASSWORD=...  then  python seed_activity.py
"""

from __future__ import annotations

import os
import sys
import random
from datetime import timedelta

import psycopg2

SEED = 42
ACK_FRACTION = 0.70

# Median hours-to-acknowledge by department (jittered per case). Chosen to rank distinctly.
DELAY_HOURS = {
    "Security": 2,
    "Housekeeping": 6,
    "Water & Plumbing": 12,
    "Electrical Maintenance": 18,
    "IT & Network": 30,
    "Civil Maintenance": 48,
}
DEFAULT_DELAY = 24


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
    rng = random.Random(SEED)
    conn = get_conn()
    cur = conn.cursor()

    # Idempotent: remove our prior synthetic acks and reset those cases to NEW.
    cur.execute("""UPDATE cases SET status = 'NEW'
                   WHERE id IN (SELECT case_id FROM case_status_events WHERE note = 'seed-activity')""")
    cur.execute("DELETE FROM case_status_events WHERE note = 'seed-activity'")

    cur.execute("""SELECT c.id, c.opened_at, d.name
                   FROM cases c JOIN departments d ON d.id = c.department_id
                   ORDER BY c.id""")
    rows = cur.fetchall()

    acked = 0
    for case_id, opened_at, dept in rows:
        if rng.random() > ACK_FRACTION:
            continue  # stays NEW (unacknowledged backlog)
        base = DELAY_HOURS.get(dept, DEFAULT_DELAY)
        hours = base * rng.uniform(0.5, 1.5)  # jitter around the department median
        acked_at = opened_at + timedelta(hours=hours)
        cur.execute("""INSERT INTO case_status_events
                         (case_id, from_status, to_status, changed_by, note, created_at)
                       VALUES (%s, 'NEW', 'ASSIGNED', NULL, 'seed-activity', %s)""",
                    (case_id, acked_at))
        cur.execute("UPDATE cases SET status = 'ASSIGNED' WHERE id = %s", (case_id,))
        acked += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"Seeded acknowledgement activity: {acked}/{len(rows)} cases acknowledged "
          f"(rest stay NEW).")


if __name__ == "__main__":
    main()
