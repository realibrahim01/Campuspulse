"""
eval_matcher.py — measure the Part A matcher against ground truth.

RULE: ground truth (gt_occurrence_id / gt_fault_key) is read ONLY from
report_provenance, ONLY here, and is NEVER passed into the matcher. The matcher sees
text embeddings + location_id + category_id + timestamp, nothing else.

Outputs:
  * pairwise same-case precision/recall/F1 swept over threshold T (truth = same
    gt_occurrence_id), at the default window and across a few windows
  * the three built-in structure checks (near-miss must NOT merge; singletons stay
    unmerged; largest duplicate group merges into one clean case)
  * Hinglish (code-mixed) cross-lingual recall, all-MiniLM-L6-v2 vs the multilingual
    model, side by side (eval-only; production model is unchanged)
  * centroid-drift analysis at the recommended config

Usage:  set CAMPUSPULSE_DB_PASSWORD=...  then  python eval_matcher.py
"""

from __future__ import annotations

import os
import re
import sys
import json
import argparse
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import psycopg2

# Import the matcher package (parent dir on path).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from campuspulse_intel.matcher import Matcher, ReportInput  # noqa: E402

PRIMARY_MODEL = "all-MiniLM-L6-v2"                              # production (384-d)
MULTILINGUAL_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"   # eval-only compare (384-d)

# Romanized-Hindi tokens used by the generator's Hinglish phrasings. Heuristic bucketing
# for the eval only — it is not a ground-truth label and never touches the matcher.
HINGLISH_TOKENS = {
    "nahi", "hai", "raha", "rahe", "kharab", "pani", "band", "gaya", "nal", "chal",
    "bahut", "jam", "gandagi", "safai", "garam", "machar", "theek", "subah", "shaam",
    "koi", "suraksha", "tooti", "hui", "bhara", "hua", "ka", "ki", "ke", "me", "se",
    "geyser", "block",  # weak; combined with others below
}
_STRONG_HI = {"nahi", "hai", "raha", "rahe", "kharab", "pani", "band", "gaya", "chal",
              "bahut", "gandagi", "safai", "garam", "machar", "theek", "subah", "shaam",
              "tooti", "bhara", "hua", "nal", "suraksha", "jam", "koi"}


def is_hinglish(text: str) -> bool:
    toks = set(re.findall(r"[a-zA-Z]+", text.lower()))
    return len(toks & _STRONG_HI) >= 1


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

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


def load_data():
    conn = get_conn()
    cur = conn.cursor()
    # Reports in arrival order (tie-break by id for determinism). NO gt here.
    cur.execute("""
        SELECT id, raw_text, category_id, location_id, created_at
        FROM reports ORDER BY created_at ASC, id ASC
    """)
    rows = cur.fetchall()
    reports = [{
        "id": r[0], "text": r[1], "category_id": r[2], "location_id": r[3],
        "ts": r[4].timestamp(),
    } for r in rows]

    # Ground truth — ONLY from report_provenance, used ONLY for measurement.
    cur.execute("SELECT report_id, gt_fault_key, gt_occurrence_id FROM report_provenance")
    gt_fault, gt_occ = {}, {}
    for rid, fk, oid in cur.fetchall():
        gt_fault[rid] = fk
        gt_occ[rid] = oid
    cur.close()
    conn.close()
    return reports, gt_fault, gt_occ


def load_structures():
    p = Path(__file__).resolve().parents[2] / "seed" / "campus_reports.json"
    meta = json.loads(p.read_text(encoding="utf-8"))["meta"]["structures"]
    return meta["near_miss_pairs"], meta["singleton_keys"]


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _c2(n):
    return n * (n - 1) // 2


def pairwise_prf(assignment: dict, truth: dict):
    """Pairwise precision/recall/F1. Positive pair = same cluster."""
    pred = defaultdict(list)
    for rid, cid in assignment.items():
        pred[cid].append(rid)
    tp = 0
    pred_pos = 0
    for members in pred.values():
        pred_pos += _c2(len(members))
        cnt = Counter(truth[m] for m in members)
        tp += sum(_c2(v) for v in cnt.values())
    true_sizes = Counter(truth[m] for m in assignment)
    actual_pos = sum(_c2(v) for v in true_sizes.values())
    fp = pred_pos - tp
    fn = actual_pos - tp
    prec = tp / (tp + fp) if (tp + fp) else 1.0
    rec = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return dict(precision=prec, recall=rec, f1=f1, tp=tp, fp=fp, fn=fn)


def run_matcher(reports, emb_by_id, T, W, recurrence_threshold=None):
    m = Matcher(threshold=T, window_days=W, recurrence_threshold=recurrence_threshold)
    for r in reports:  # already in ts order
        m.process(ReportInput(
            report_id=r["id"], emb=emb_by_id[r["id"]],
            location_id=r["location_id"], category_id=r["category_id"], ts=r["ts"],
        ))
    return m


def embed(model_name, reports):
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(model_name)
    texts = [r["text"] for r in reports]
    vecs = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True,
                        batch_size=64, show_progress_bar=False).astype(np.float32)
    return {r["id"]: vecs[i] for i, r in enumerate(reports)}


# ---------------------------------------------------------------------------
# Structure checks
# ---------------------------------------------------------------------------

def structure_checks(assignment, gt_fault, gt_occ, near_miss_pairs, singleton_keys):
    ids_by_fault = defaultdict(list)
    ids_by_occ = defaultdict(list)
    for rid in assignment:
        ids_by_fault[gt_fault[rid]].append(rid)
        ids_by_occ[gt_occ[rid]].append(rid)
    case_sizes = Counter(assignment.values())

    # 1. near-miss pairs must NOT share a case
    nm = []
    for a, b in near_miss_pairs:
        casesA = {assignment[r] for r in ids_by_fault.get(a, [])}
        casesB = {assignment[r] for r in ids_by_fault.get(b, [])}
        shared = casesA & casesB
        nm.append({"pair": [a, b], "merged": bool(shared), "ok": not shared})

    # 2. singletons stay unmerged (their single report is alone in its case)
    sg = []
    for key in singleton_keys:
        rids = ids_by_fault.get(key, [])
        ok = all(case_sizes[assignment[r]] == 1 for r in rids)
        sg.append({"key": key, "n_reports": len(rids), "ok": ok})

    # 3. largest duplicate group merges into ONE clean case
    largest_occ = max(ids_by_occ, key=lambda o: len(ids_by_occ[o]))
    rids = ids_by_occ[largest_occ]
    cases = Counter(assignment[r] for r in rids)
    dominant_case, in_dominant = cases.most_common(1)[0]
    foreign = case_sizes[dominant_case] - in_dominant   # non-group reports in that case
    lg = {
        "occurrence": largest_occ, "group_size": len(rids),
        "cases_spanned": len(cases), "in_dominant_case": in_dominant,
        "foreign_in_case": foreign,
        "ok": len(cases) == 1 and foreign == 0,
    }
    return {"near_miss": nm, "singletons": sg, "largest_group": lg}


def hinglish_recall(reports, assignment, gt_occ):
    """Recall on positive pairs, split by language mix. en-hi (cross-lingual) is the crux."""
    lang = {r["id"]: ("hi" if is_hinglish(r["text"]) else "en") for r in reports}
    by_occ = defaultdict(list)
    for r in reports:
        by_occ[gt_occ[r["id"]]].append(r["id"])
    buckets = {"en-en": [0, 0], "hi-hi": [0, 0], "en-hi": [0, 0]}  # [merged, total]
    for rids in by_occ.values():
        for i in range(len(rids)):
            for j in range(i + 1, len(rids)):
                a, b = rids[i], rids[j]
                key = "-".join(sorted((lang[a], lang[b])))
                merged = assignment[a] == assignment[b]
                buckets[key][1] += 1
                if merged:
                    buckets[key][0] += 1
    out = {}
    for k, (mrg, tot) in buckets.items():
        out[k] = {"recall": (mrg / tot if tot else None), "pairs": tot, "merged": mrg}
    n_hi = sum(1 for v in lang.values() if v == "hi")
    return out, n_hi


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=float, default=7.0, help="default recency window (days)")
    ap.add_argument("--tmin", type=float, default=0.30)
    ap.add_argument("--tmax", type=float, default=0.85)
    ap.add_argument("--tstep", type=float, default=0.05)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[2] / "docs" / "day2_sweep_results.md"))
    args = ap.parse_args()

    reports, gt_fault, gt_occ = load_data()
    near_miss_pairs, singleton_keys = load_structures()
    print(f"Loaded {len(reports)} reports; "
          f"{len(set(gt_occ.values()))} occurrences; {len(set(gt_fault.values()))} faults.")

    grid = [round(t, 4) for t in np.arange(args.tmin, args.tmax + 1e-9, args.tstep)]
    lines = ["# Day 2 — matcher sweep results", ""]

    # --- Primary model: T sweep at default window --------------------------
    print(f"\nEmbedding with primary model {PRIMARY_MODEL} ...")
    embA = embed(PRIMARY_MODEL, reports)

    print(f"\n=== {PRIMARY_MODEL}  |  W = {args.window} days  |  threshold sweep ===")
    header = f"{'T':>6} {'prec':>7} {'recall':>7} {'F1':>7} {'#cases':>7} {'FP':>6} {'FN':>6}"
    print(header)
    lines += [f"## {PRIMARY_MODEL} — T sweep at W={args.window}d", "", "```", header]
    best = None
    for T in grid:
        m = run_matcher(reports, embA, T, args.window)
        prf = pairwise_prf(m.assignment, gt_occ)
        ncases = len(set(m.assignment.values()))
        row = (f"{T:>6.2f} {prf['precision']:>7.3f} {prf['recall']:>7.3f} "
               f"{prf['f1']:>7.3f} {ncases:>7} {prf['fp']:>6} {prf['fn']:>6}")
        print(row)
        lines.append(row)
        if best is None or prf["f1"] > best[1]["f1"]:
            best = (T, prf, ncases)
    lines += ["```", ""]
    T_star = best[0]
    print(f"\nBest F1 at T={T_star:.2f}: "
          f"P={best[1]['precision']:.3f} R={best[1]['recall']:.3f} F1={best[1]['f1']:.3f} "
          f"({best[2]} cases vs 59 true occurrences)")

    # --- Window sweep at T* -------------------------------------------------
    print(f"\n=== {PRIMARY_MODEL}  |  T = {T_star:.2f}  |  window sweep ===")
    lines += [f"## Window sweep at T={T_star:.2f}", "", "```",
              f"{'W(d)':>6} {'prec':>7} {'recall':>7} {'F1':>7} {'#cases':>7}"]
    print(f"{'W(d)':>6} {'prec':>7} {'recall':>7} {'F1':>7} {'#cases':>7}")
    for W in (3, 7, 14, 30):
        m = run_matcher(reports, embA, T_star, W)
        prf = pairwise_prf(m.assignment, gt_occ)
        ncases = len(set(m.assignment.values()))
        row = f"{W:>6} {prf['precision']:>7.3f} {prf['recall']:>7.3f} {prf['f1']:>7.3f} {ncases:>7}"
        print(row)
        lines.append(row)
    lines += ["```", ""]

    # --- Structure checks at (T*, default W) --------------------------------
    m_star = run_matcher(reports, embA, T_star, args.window)
    sc = structure_checks(m_star.assignment, gt_fault, gt_occ, near_miss_pairs, singleton_keys)
    print(f"\n=== structure checks at T={T_star:.2f}, W={args.window}d ===")
    print("near-miss pairs (must NOT merge):")
    for x in sc["near_miss"]:
        print(f"  {x['pair'][0]:>22} / {x['pair'][1]:<22} merged={x['merged']}  {'OK' if x['ok'] else 'FAIL'}")
    print("singletons (must stay alone):")
    for x in sc["singletons"]:
        print(f"  {x['key']:>22}  n={x['n_reports']}  {'OK' if x['ok'] else 'FAIL'}")
    lg = sc["largest_group"]
    print(f"largest group '{lg['occurrence']}': size={lg['group_size']}, "
          f"cases_spanned={lg['cases_spanned']}, foreign_in_case={lg['foreign_in_case']}  "
          f"{'OK' if lg['ok'] else 'FAIL'}")
    lines += ["## Structure checks at chosen config", "", "```"]
    lines += [f"near-miss {x['pair']} merged={x['merged']} {'OK' if x['ok'] else 'FAIL'}" for x in sc["near_miss"]]
    lines += [f"singleton {x['key']} n={x['n_reports']} {'OK' if x['ok'] else 'FAIL'}" for x in sc["singletons"]]
    lines += [f"largest_group {lg['occurrence']} size={lg['group_size']} spanned={lg['cases_spanned']} foreign={lg['foreign_in_case']} {'OK' if lg['ok'] else 'FAIL'}", "```", ""]

    # --- Drift at (T*, default W) ------------------------------------------
    dr = m_star.drift_report()
    print(f"\n=== centroid drift at T={T_star:.2f}, W={args.window}d ===")
    print(f"  non-seed members: {dr['non_seed_members']}, marginal attaches (sim in [T,T+0.05]): {dr['marginal_attaches']}")
    print(f"  members BELOW T vs FINAL centroid (drift-carried): {dr['below_T_vs_final_centroid']}")
    print(f"  attach->final sim gap  mean={dr['gap_mean']:.3f}  p90={dr['gap_p90']:.3f}  max={dr['gap_max']:.3f}")
    lines += ["## Centroid drift at chosen config", "", "```",
              f"non_seed_members={dr['non_seed_members']} marginal={dr['marginal_attaches']} below_T_vs_final={dr['below_T_vs_final_centroid']}",
              f"gap mean={dr['gap_mean']:.3f} p90={dr['gap_p90']:.3f} max={dr['gap_max']:.3f}", "```", ""]

    # --- Hinglish: primary vs multilingual, across T -----------------------
    print(f"\nEmbedding with multilingual model {MULTILINGUAL_MODEL} (eval-only) ...")
    embB = embed(MULTILINGUAL_MODEL, reports)
    print(f"\n=== Hinglish cross-lingual recall (en-hi pairs) across T, W={args.window}d ===")
    print(f"{'T':>6} {'A en-hi':>9} {'A hi-hi':>9} {'B en-hi':>9} {'B hi-hi':>9}   (A={PRIMARY_MODEL}, B=multilingual)")
    lines += ["## Hinglish cross-lingual recall (en-hi), primary vs multilingual", "", "```",
              f"{'T':>6} {'A en-hi':>9} {'A hi-hi':>9} {'B en-hi':>9} {'B hi-hi':>9}"]
    for T in grid:
        mA = run_matcher(reports, embA, T, args.window)
        mB = run_matcher(reports, embB, T, args.window)
        hA, n_hi = hinglish_recall(reports, mA.assignment, gt_occ)
        hB, _ = hinglish_recall(reports, mB.assignment, gt_occ)
        def fmt(x):
            return f"{x:.3f}" if x is not None else "  -  "
        row = f"{T:>6.2f} {fmt(hA['en-hi']['recall']):>9} {fmt(hA['hi-hi']['recall']):>9} {fmt(hB['en-hi']['recall']):>9} {fmt(hB['hi-hi']['recall']):>9}"
        print(row)
        lines.append(row)
    lines += ["```", "",
              f"(Hinglish reports detected by heuristic: {n_hi} of {len(reports)}. "
              f"en-hi = positive pairs with one English + one Hinglish report — the cross-lingual crux.)"]

    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote full results to {args.out}")
    print(f"\nRECOMMENDATION (not locked): T={T_star:.2f}, W={args.window}d. "
          f"Confirm before we persist cases.")


if __name__ == "__main__":
    main()
