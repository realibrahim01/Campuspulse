"""
generate_campus_reports.py — synthetic seed generator for CampusPulse.

Produces campus_reports.json: a self-contained campus (reference data) plus ~310
student reports carrying ground-truth labels. The loader rebuilds the whole demo DB
from this one file.

WHY THIS EXISTS (defend this to judges):
  We do not eyeball clustering quality — we measure it. Each report is stamped with:
    * fault_key      — which underlying fault it describes  (dedup ground truth)
    * occurrence_id  — which occurrence of that fault       (recurrence ground truth)
    * department_true — the department that should own it    (routing ground truth)
  These labels never enter the running pipeline (they land in report_provenance, which
  the pipeline never joins). They exist only so we can compute clustering
  precision/recall and routing accuracy against a known answer key.

THREE STRUCTURES ARE BUILT IN ON PURPOSE, each a specific test:
  1. Code-mixed English/Hindi phrasings of the SAME fault  -> must MERGE.
     (Tests that multilingual embeddings unify Hinglish paraphrases.)
  2. Near-miss pairs: near-identical wording, DIFFERENT location -> must NOT merge.
     (Tests that location is a hard signal, not overridden by text similarity.)
  3. Singletons: a fault reported exactly once -> must stay UNMERGED.
     (Tests that we don't hallucinate clusters.)

Determinism: a fixed RNG seed makes the dataset — and therefore every metric computed
on it — reproducible across the several rebuilds we'll do before the 11th.
"""

import json
import random
import argparse
from datetime import datetime, timedelta, timezone

SEED = 42
SEED_BATCH = "seed-2026-09-demo-v1"   # bump when the dataset shape changes
GENERATOR = "generate_campus_reports.py"

# ---------------------------------------------------------------------------
# Reference data (a single campus). Weights/populations are tunable per campus;
# they live in the DB as data, not code, once loaded.
# ---------------------------------------------------------------------------

DEPARTMENTS = [
    # name,                    sla_hours (target response time)
    ("Electrical Maintenance", 24),
    ("Water & Plumbing",       24),
    ("Housekeeping",           12),
    ("IT & Network",           48),
    ("Civil Maintenance",      72),
    ("Security",                6),
]

# severity_weight is the fault's inherent severity on a 0..1 scale; safety_flag marks a
# health/safety hazard. Both feed the "severity and safety risk" scoring input.
CATEGORIES = [
    # key,        label,                 severity, safety, default_department
    ("ELECTRICAL", "Electrical",          0.80, True,  "Electrical Maintenance"),
    ("WATER",      "Water supply",        0.55, False, "Water & Plumbing"),
    ("SANITATION", "Sanitation",          0.70, True,  "Housekeeping"),
    ("INTERNET",   "Internet / WiFi",     0.40, False, "IT & Network"),
    ("FURNITURE",  "Furniture",           0.30, False, "Civil Maintenance"),
    ("CIVIL",      "Civil / structural",  0.60, False, "Civil Maintenance"),
    ("SECURITY",   "Security",            0.85, True,  "Security"),
    ("EQUIPMENT",  "Lab / AV equipment",  0.45, False, "IT & Network"),
]

# name, type, population, criticality_weight
LOCATIONS = [
    ("Hostel A Block",           "HOSTEL",    300, 1.30),
    ("Hostel B Block",           "HOSTEL",    320, 1.30),
    ("Hostel C Block",           "HOSTEL",    280, 1.30),
    ("Hostel D Block",           "HOSTEL",    260, 1.30),
    ("Lab Wing 2F",              "LAB",       120, 1.50),
    ("Lab 1",                    "LAB",        60, 1.50),
    ("Academic Block Corridor",  "CORRIDOR",  500, 1.10),
    ("Lecture Hall 1",           "CLASSROOM", 150, 1.20),
    ("Library",                  "LIBRARY",   200, 1.40),
    ("Central Canteen",          "CANTEEN",   400, 1.20),
    ("Sports Ground",            "GROUNDS",   150, 0.90),
    ("Parking Lot",              "GROUNDS",   100, 1.00),
    ("Main Road",                "OTHER",     200, 1.00),
    ("Back Gate",                "OTHER",     120, 1.10),
    ("Men's Washroom Hostel A",  "WASHROOM",  300, 1.20),
    ("Men's Washroom Hostel B",  "WASHROOM",  320, 1.20),
    ("Room 210 Hostel B",        "HOSTEL",      4, 1.00),
    ("Room 305 Hostel B",        "HOSTEL",      4, 1.00),
    ("Admin Office",             "OFFICE",     40, 1.10),
]

# A transparent weighted function. Weights sum to 1.0 for interpretability; norm_params
# cap each raw input before weighting so no single input can dominate unboundedly.
SCORING_WEIGHTS = {
    "version_label": "v1-demo",
    "w_severity":   0.30,
    "w_people":     0.20,
    "w_recurrence": 0.15,
    "w_age_sla":    0.20,
    "w_location":   0.15,
    "norm_params": {
        "people":     {"cluster_cap": 10, "population_cap": 500},
        "recurrence": {"cap": 5},
        "age_sla":    {"cap_ratio": 3.0},
        "location":   {"max_weight": 1.5},
    },
}

# Most routing is the category's default department. A few explicit rules demonstrate
# that routing is configurable and can override the default (evaluated by rule_order).
ROUTING_RULES = [
    # rule_order, match_category, match_location_type, match_keyword, target_department
    (10, None,        None,       "gas",     "Security"),           # safety keyword escalation
    (20, "SANITATION","GROUNDS",  None,      "Civil Maintenance"),  # outdoor sanitation -> Civil
    (30, "EQUIPMENT", "CLASSROOM",None,      "IT & Network"),
    # rule_order 1000 = fall through to the category default_department (loader inserts
    # a catch-all per category so every case routes somewhere).
]

# ---------------------------------------------------------------------------
# Fault catalogue. Each fault is one underlying problem at one location. `occ` is how
# many times it has occurred (recurrence). `reports` is reports-per-occurrence range.
# `phrasings` are English + Hinglish variants of the SAME fault (must merge together).
# `near_miss_of` documents an intentional near-duplicate-at-a-different-location pair.
# ---------------------------------------------------------------------------

FAULTS = [
    # --- Group A: recurring faults (multi-occurrence) ---
    dict(key="wifi_hostelB", category="INTERNET", location="Hostel B Block",
         dept="IT & Network", occ=6, reports=(6, 10), phrasings=[
            "WiFi is not working in B block since morning",
            "Internet down in Hostel B, cannot attend online class",
            "B block me wifi nahi chal raha",
            "hostel B ka internet band hai please dekho",
            "No connectivity in B block wifi again",
            "wifi keeps disconnecting in hostel B",
         ]),
    dict(key="water_cooler_lab2f", category="WATER", location="Lab Wing 2F",
         dept="Water & Plumbing", occ=5, reports=(6, 10), phrasings=[
            "Water cooler on Lab Wing 2nd floor not giving cold water",
            "The RO water cooler near lab 2F is not working",
            "lab 2F ka water cooler kharab hai, pani garam aa raha",
            "cooler pe pani nahi aa raha 2nd floor lab",
            "No drinking water from the cooler in lab wing",
         ]),
    dict(key="washroom_hostelA_clog", category="SANITATION", location="Men's Washroom Hostel A",
         dept="Housekeeping", occ=5, reports=(5, 9),
         near_miss_of="washroom_hostelB_clog", phrasings=[
            "Toilet blocked in Hostel A washroom, water everywhere",
            "Hostel A bathroom is clogged and smelling badly",
            "hostel A washroom me pani bhara hua hai, toilet band hai",
            "gandagi bahut hai A block bathroom, jam ho gaya",
            "Washroom in A block flooded, please clean urgently",
         ]),
    dict(key="corridor_light_acad", category="ELECTRICAL", location="Academic Block Corridor",
         dept="Electrical Maintenance", occ=4, reports=(4, 8), phrasings=[
            "Corridor lights not working in academic block",
            "Academic block corridor is completely dark at night",
            "acad block corridor ki light kharab hai",
            "tubelight fused in the main corridor, very dark",
         ]),
    dict(key="hostelC_water_supply", category="WATER", location="Hostel C Block",
         dept="Water & Plumbing", occ=4, reports=(5, 9), phrasings=[
            "No water supply in Hostel C since last night",
            "Hostel C has no running water in bathrooms",
            "C block me pani nahi aa raha subah se",
            "water supply band hai hostel C, bahut problem",
         ]),
    dict(key="library_ac", category="ELECTRICAL", location="Library",
         dept="Electrical Maintenance", occ=3, reports=(4, 8), phrasings=[
            "AC not cooling in the library reading hall",
            "Library air conditioning is not working, too hot to study",
            "library ka AC theek se nahi chal raha, garmi bahut hai",
            "reading room AC stopped working again",
         ]),
    dict(key="canteen_hygiene", category="SANITATION", location="Central Canteen",
         dept="Housekeeping", occ=3, reports=(5, 9), phrasings=[
            "Canteen tables are dirty and not cleaned",
            "Hygiene issue in the central canteen, flies everywhere",
            "canteen me safai nahi hoti, ganda rehta hai",
            "food area dirty, dustbins overflowing in canteen",
         ]),
    dict(key="lab1_pc", category="EQUIPMENT", location="Lab 1",
         dept="IT & Network", occ=3, reports=(4, 8), phrasings=[
            "Several PCs in Lab 1 are not turning on",
            "Computers in Lab 1 keep crashing during practical",
            "lab 1 ke computer on nahi ho rahe",
            "half the systems in lab 1 not booting",
         ]),
    dict(key="hostelB_fan_r210", category="ELECTRICAL", location="Room 210 Hostel B",
         dept="Electrical Maintenance", occ=3, reports=(2, 4),
         near_miss_of="fan_room305", phrasings=[
            "Fan not working in room 210",
            "Ceiling fan stopped in Hostel B room 210",
            "room 210 ka fan nahi chal raha",
         ]),
    dict(key="stagnant_water_backgate", category="SANITATION", location="Back Gate",
         dept="Civil Maintenance", occ=3, reports=(4, 6), phrasings=[
            "Stagnant water collecting near the back gate, mosquito breeding",
            "Dirty water logged at back gate for days, dengue risk",
            "back gate pe pani jama hai, machar bahut ho gaye",
            "water logging near back gate, please drain it",
         ]),
    dict(key="ground_floodlight", category="ELECTRICAL", location="Sports Ground",
         dept="Electrical Maintenance", occ=2, reports=(4, 6), phrasings=[
            "Floodlights not working on the sports ground",
            "Ground lights are off, cannot play in the evening",
            "sports ground ki light band hai shaam ko",
         ]),

    # --- Group B: low-recurrence faults (2 occurrences each) ---
    dict(key="hostelA_hot_water", category="WATER", location="Hostel A Block",
         dept="Water & Plumbing", occ=2, reports=(4, 8), phrasings=[
            "No hot water in Hostel A geyser in the morning",
            "Geyser not working in A block, only cold water",
            "hostel A me garam pani nahi aa raha, geyser kharab",
         ]),
    dict(key="parking_security", category="SECURITY", location="Parking Lot",
         dept="Security", occ=2, reports=(3, 5), phrasings=[
            "No security guard at the parking lot, bikes unsafe",
            "Parking area unmanned, a scooter went missing",
            "parking me koi guard nahi hai, suraksha ka issue",
         ]),
    dict(key="classroom_bench", category="FURNITURE", location="Lecture Hall 1",
         dept="Civil Maintenance", occ=2, reports=(3, 5), phrasings=[
            "Broken benches in Lecture Hall 1, unsafe to sit",
            "Several desks damaged in lecture hall 1",
            "lecture hall 1 ki bench tooti hui hai",
         ]),
    dict(key="projector_hall1", category="EQUIPMENT", location="Lecture Hall 1",
         dept="IT & Network", occ=2, reports=(3, 5), phrasings=[
            "Projector not working in Lecture Hall 1",
            "The projector display is blank in hall 1",
            "hall 1 ka projector on nahi ho raha",
         ]),
    dict(key="leaking_tap_hostelD", category="WATER", location="Hostel D Block",
         dept="Water & Plumbing", occ=2, reports=(3, 5), phrasings=[
            "Tap continuously leaking in Hostel D washroom",
            "Water wastage from a broken tap in D block",
            "hostel D me nal se pani leak ho raha hai",
         ]),
    dict(key="wifi_hostelD", category="INTERNET", location="Hostel D Block",
         dept="IT & Network", occ=2, reports=(4, 6),
         near_miss_of="wifi_hostelB", phrasings=[
            "WiFi is not working in D block since morning",
            "Internet down in Hostel D, cannot attend online class",
            "D block me wifi nahi chal raha",
         ]),
    dict(key="washroom_hostelB_clog", category="SANITATION", location="Men's Washroom Hostel B",
         dept="Housekeeping", occ=2, reports=(4, 6),
         near_miss_of="washroom_hostelA_clog", phrasings=[
            "Toilet blocked in Hostel B washroom, water everywhere",
            "Hostel B bathroom is clogged and smelling badly",
            "hostel B washroom me pani bhara hua hai, toilet band hai",
         ]),

    # --- Group C: singletons (exactly one occurrence, one report) — must stay unmerged ---
    dict(key="broken_window_lib", category="CIVIL", location="Library",
         dept="Civil Maintenance", occ=1, reports=(1, 1), phrasings=[
            "A window pane is broken in the library, glass on the floor",
         ]),
    dict(key="fan_room305", category="ELECTRICAL", location="Room 305 Hostel B",
         dept="Electrical Maintenance", occ=1, reports=(1, 1),
         near_miss_of="hostelB_fan_r210", phrasings=[
            "Fan not working in room 305",
         ]),
    dict(key="pothole_mainroad", category="CIVIL", location="Main Road",
         dept="Civil Maintenance", occ=1, reports=(1, 1), phrasings=[
            "Large pothole on the main road near the gate, risky for two-wheelers",
         ]),
    dict(key="gasleak_canteen", category="SECURITY", location="Central Canteen",
         dept="Security", occ=1, reports=(1, 1), phrasings=[
            "Smell of gas leak near the canteen kitchen, please check urgently",
         ]),
]

# Small variations added to a base phrasing so within-occurrence reports are
# near-duplicates (as real reports are) without being byte-identical.
PREFIXES = ["", "Please note: ", "Urgent: ", "Complaint: ", "Hi, ", "FYI - "]
SUFFIXES = ["", " Please fix soon.", " Kindly resolve.", " Thanks.", " It's been days.", ""]


def vary(text, rng):
    t = rng.choice(PREFIXES) + text + rng.choice(SUFFIXES)
    if rng.random() < 0.15:               # occasional lowercasing (real user noise)
        t = t.lower()
    return t


def build(rng):
    students = [
        {"email": f"student{n:02d}@campus.edu", "display_name": f"Student {n:02d}"}
        for n in range(1, 41)
    ]
    department_users = [
        {"email": "elec@campus.edu",  "display_name": "Electrical Desk", "department": "Electrical Maintenance"},
        {"email": "water@campus.edu", "display_name": "Plumbing Desk",   "department": "Water & Plumbing"},
        {"email": "house@campus.edu", "display_name": "Housekeeping Desk","department": "Housekeeping"},
        {"email": "it@campus.edu",    "display_name": "IT Desk",          "department": "IT & Network"},
        {"email": "civil@campus.edu", "display_name": "Civil Desk",       "department": "Civil Maintenance"},
        {"email": "security@campus.edu","display_name": "Security Desk",  "department": "Security"},
    ]
    admins = [{"email": "admin@campus.edu", "display_name": "Campus Admin"}]

    # Occurrences spread across the last ~180 days; reports within an occurrence fall in
    # a 1-3 day window (a real burst of complaints about one incident).
    now = datetime(2026, 9, 8, 9, 0, tzinfo=timezone.utc)
    reports = []
    report_id_seq = 0

    for fault in FAULTS:
        # Space this fault's occurrences out over time so recurrence has real history.
        # ALL occurrences must fall in the PAST: the highest seq is the most recent
        # (a couple of weeks ago at most) and earlier seqs step further back. This is
        # what makes recurrence ("3rd failure") and "age vs SLA" meaningful and stops
        # any report landing in the future.
        occ_gap_days = rng.randint(18, 40)
        recent_offset = rng.randint(2, 25)         # last occurrence this many days ago
        n_occ = fault["occ"]
        for seq in range(1, n_occ + 1):
            days_ago = recent_offset + (n_occ - seq) * occ_gap_days
            occ_time = now - timedelta(days=days_ago)
            occurrence_id = f"{fault['key']}#{seq}"
            n_reports = rng.randint(*fault["reports"])
            for _ in range(n_reports):
                report_id_seq += 1
                base = rng.choice(fault["phrasings"])
                # Reports of one occurrence arrive within ~2 days of it; capped below
                # recent_offset's 2-day floor so even the latest reports stay <= now.
                created = occ_time + timedelta(
                    hours=rng.randint(0, 44), minutes=rng.randint(0, 59)
                )
                reports.append({
                    "text": vary(base, rng),
                    "category_key": fault["category"],
                    "location_name": fault["location"],
                    "reporter_email": rng.choice(students)["email"],
                    "created_at": created.isoformat(),
                    # ground truth:
                    "fault_key": fault["key"],
                    "occurrence_id": occurrence_id,
                    "department_true": fault["dept"],
                })

    rng.shuffle(reports)  # arrival order is not fault order

    return {
        "meta": {
            "generator": GENERATOR,
            "seed": SEED,
            "seed_batch": SEED_BATCH,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "counts": {
                "faults": len(FAULTS),
                "occurrences": sum(f["occ"] for f in FAULTS),
                "reports": len(reports),
                "singletons": sum(1 for f in FAULTS if f["occ"] == 1),
                "near_miss_pairs": sum(1 for f in FAULTS if f.get("near_miss_of")),
            },
            # Structural metadata for the eval's three special checks. This is dataset
            # STRUCTURE (which faults are near-misses / singletons), not gt_* labels — the
            # eval reads gt_fault_key / gt_occurrence_id from report_provenance, and uses
            # this only to know which structures to assert on.
            "structures": {
                # Unique, order-independent near-miss fault pairs (identical wording,
                # different location -> must NOT merge).
                "near_miss_pairs": sorted({
                    tuple(sorted((f["key"], f["near_miss_of"])))
                    for f in FAULTS if f.get("near_miss_of")
                }),
                # Faults that occur exactly once with a single report -> must stay unmerged.
                "singleton_keys": sorted(f["key"] for f in FAULTS if f["occ"] == 1),
            },
        },
        "reference": {
            "departments": [{"name": n, "sla_hours": s} for n, s in DEPARTMENTS],
            "categories": [
                {"key": k, "label": l, "severity_weight": sv,
                 "safety_flag": sf, "default_department": dd}
                for k, l, sv, sf, dd in CATEGORIES
            ],
            "locations": [
                {"name": n, "type": t, "population": p, "criticality_weight": c}
                for n, t, p, c in LOCATIONS
            ],
            "students": students,
            "department_users": department_users,
            "admins": admins,
            "scoring_weights": SCORING_WEIGHTS,
            "routing_rules": [
                {"rule_order": o, "match_category": mc, "match_location_type": ml,
                 "match_keyword": mk, "target_department": td, "active": True}
                for o, mc, ml, mk, td in ROUTING_RULES
            ],
        },
        "reports": reports,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default="campus_reports.json")
    args = ap.parse_args()

    rng = random.Random(SEED)
    data = build(rng)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)

    c = data["meta"]["counts"]
    print(f"Wrote {args.out}")
    print(f"  faults={c['faults']} occurrences={c['occurrences']} reports={c['reports']}")
    print(f"  singletons={c['singletons']} near_miss_faults={c['near_miss_pairs']}")


if __name__ == "__main__":
    main()
