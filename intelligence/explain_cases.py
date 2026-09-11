"""
explain_cases.py — generate + store a priority explanation for every scored case.

Reads each case's CURRENT scoring_record and its scoring_components, renders the
explanation from those rows only (templates; LLM disabled), writes it back to
scoring_records.explanation_text, and prints the top-5 for the demo.

Self-check: for every explanation, the fact-guard confirms it contains no number that
isn't an allowed fact from the component rows. Templates pass this by construction; the
same guard is what would police an LLM smoother if one were enabled.

Usage:  set CAMPUSPULSE_DB_PASSWORD=...  then  python explain_cases.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parent))
from campuspulse_intel import explain  # noqa: E402


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


def load_components(cur, record_id):
    cur.execute("""SELECT input_name, raw_value, normalized_value, weight, contribution
                   FROM scoring_components WHERE scoring_record_id = %s""", (record_id,))
    comps = []
    for name, raw, norm, weight, contrib in cur.fetchall():
        comps.append({
            "input_name": name, "raw_value": raw,
            "normalized_value": float(norm), "weight": float(weight),
            "contribution": float(contrib),
        })
    return comps


def main():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT c.id, c.priority_score, c.current_scoring_record_id,
               cat.key, l.name
        FROM cases c
        JOIN categories cat ON cat.id = c.category_id
        JOIN locations  l   ON l.id  = c.location_id
        WHERE c.current_scoring_record_id IS NOT NULL
        ORDER BY c.priority_score DESC, c.id
    """)
    cases = cur.fetchall()

    generated = 0
    top = []
    demo = None
    for case_id, score, record_id, cat_key, loc_name in cases:
        comps = load_components(cur, record_id)
        total = float(score)
        # Store the student/judge-facing view (no +pts). The department console renders the
        # annotated view on demand via render(..., "department").
        student = explain.render(total, comps, "student")

        cur.execute(
            "UPDATE scoring_records SET explanation_text = %s, explanation_template_version = %s WHERE id = %s",
            (student, explain.TEMPLATE_VERSION, record_id),
        )
        generated += 1
        if len(top) < 5:
            dept = explain.render(total, comps, "department")
            top.append((case_id, total, cat_key, loc_name, student, dept))
        if demo is None:
            demo = (total, comps, student)

    conn.commit()
    cur.close()
    conn.close()

    print(f"Generated {generated} explanations (template {explain.TEMPLATE_VERSION}), LLM disabled.\n")
    print("=== TOP 5 CASES (for the demo) ===")
    for case_id, total, cat_key, loc_name, student, dept in top:
        print(f"\n[case {case_id}]  {cat_key} @ {loc_name}")
        print(f"  STUDENT VIEW (judge-facing): {student}")
        print(f"  DEPT VIEW (console)        : {dept}")

    # Demonstrate the fact-guard that would police an optional LLM smoother: the vetted
    # template passes; a fabricated number is caught and would trigger a fallback.
    total, comps, text = demo
    allowed = explain.allowed_for_smoothing(text, total, comps)
    clean = explain.find_invented_numbers(text, allowed)
    fabricated = text[:-1] + ", and 9999 nearby rooms are affected."
    caught = explain.find_invented_numbers(fabricated, allowed)
    print("\n=== fact-guard (arms the optional LLM smoother) ===")
    print(f"  template explanation -> invented numbers: {clean or '{} (passes)'}")
    print(f"  fabricated '9999 rooms' variant -> guard flags: {caught}")


if __name__ == "__main__":
    main()
