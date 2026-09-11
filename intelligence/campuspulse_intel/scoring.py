"""
scoring.py — the priority scoring engine (Part C).

A PURE, deterministic function: case facts + weights + an `as_of` timestamp go in; a
total priority plus a per-component breakdown come out. No DB, no randomness, NO LLM.

Five components, each normalized to [0, 1], multiplied by a weight from `scoring_weights`,
and summed. The result is scaled to 0-100 for readability, so each component's
`contribution = weight * normalized * 100` and the contributions sum to `total_score`.

Determinism / reproducibility: the ONLY time-dependent input is age (hours open), which is
computed against the explicit `as_of` argument and stored in the record. Re-running with
the same `as_of` reproduces the score exactly; a later re-score is a NEW append-only
record that legitimately reflects more age. Nothing here is stochastic.

Every component returns the RAW inputs it used, so the Day-3 explanation layer can render a
sentence from these rows alone and never cite a reason the score did not use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

SCALE = 100.0  # total_score and contributions are on a 0-100 scale


@dataclass
class Component:
    input_name: str
    raw_value: dict            # the exact inputs used (for the explanation layer)
    normalized_value: float    # 0..1
    weight: float
    contribution: float        # weight * normalized_value * SCALE


@dataclass
class ScoreResult:
    total_score: float
    components: list = field(default_factory=list)


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def score_case(f: dict, weights: dict, as_of: datetime) -> ScoreResult:
    """
    f: case facts with keys
        severity_weight, safety_flag, reporter_count, population, occurrence_seq,
        opened_at (tz-aware datetime), sla_hours, criticality_weight
    weights: row from scoring_weights (w_* floats + norm_params dict)
    """
    np_ = weights["norm_params"]
    comps: list[Component] = []

    # 1) severity / safety — category severity (already 0..1) plus a safety bump.
    safety_bump = float(np_.get("severity", {}).get("safety_bump", 0.2))
    sev_base = float(f["severity_weight"])
    sev_norm = _clamp01(sev_base + (safety_bump if f["safety_flag"] else 0.0))
    comps.append(_mk("severity", {
        "severity_weight": sev_base, "safety_flag": bool(f["safety_flag"]),
        "safety_bump_applied": safety_bump if f["safety_flag"] else 0.0,
    }, sev_norm, float(weights["w_severity"])))

    # 2) people affected — cluster size (reporters) and the location's population.
    cc = float(np_["people"]["cluster_cap"])
    pc = float(np_["people"]["population_cap"])
    n_rep = int(f["reporter_count"])
    pop = int(f["population"])
    ppl_norm = 0.5 * _clamp01(n_rep / cc) + 0.5 * _clamp01(pop / pc)
    comps.append(_mk("people_affected", {
        "reporter_count": n_rep, "population": pop,
        "cluster_cap": cc, "population_cap": pc,
    }, ppl_norm, float(weights["w_people"])))

    # 3) recurrence — how many times this fault has occurred. seq=1 (first time) -> 0.
    #    occurrence_date is recorded so the explanation can distinguish two occurrences of
    #    the same recurring fault (which otherwise look like duplicates on a screen).
    cap = float(np_["recurrence"]["cap"])
    seq = int(f["occurrence_seq"])
    rec_norm = _clamp01((seq - 1) / cap)
    opened = f.get("opened_at")
    comps.append(_mk("recurrence", {
        "occurrence_seq": seq, "prior_occurrences": seq - 1, "cap": cap,
        "occurrence_date": opened.date().isoformat() if opened is not None else None,
    }, rec_norm, float(weights["w_recurrence"])))

    # 4) age vs department SLA — hours open / SLA, capped, against `as_of`.
    hours_open = (as_of - f["opened_at"]).total_seconds() / 3600.0
    sla = float(f["sla_hours"])
    cap_ratio = float(np_["age_sla"]["cap_ratio"])
    ratio = hours_open / sla if sla > 0 else 0.0
    age_norm = _clamp01(min(ratio, cap_ratio) / cap_ratio)
    comps.append(_mk("age_vs_sla", {
        "hours_open": round(hours_open, 2), "sla_hours": sla,
        "ratio": round(ratio, 3), "cap_ratio": cap_ratio,
        "as_of": as_of.isoformat(),
    }, age_norm, float(weights["w_age_sla"])))

    # 5) location criticality — the location's criticality weight, normalized.
    mw = float(np_["location"]["max_weight"])
    crit = float(f["criticality_weight"])
    loc_norm = _clamp01(crit / mw)
    comps.append(_mk("location_criticality", {
        "criticality_weight": crit, "max_weight": mw,
    }, loc_norm, float(weights["w_location"])))

    total = round(sum(c.contribution for c in comps), 3)
    return ScoreResult(total_score=total, components=comps)


def _mk(name: str, raw: dict, norm: float, weight: float) -> Component:
    norm = round(_clamp01(norm), 4)
    return Component(
        input_name=name, raw_value=raw, normalized_value=norm, weight=weight,
        contribution=round(weight * norm * SCALE, 4),
    )
