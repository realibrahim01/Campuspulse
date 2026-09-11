"""
explain.py — the explanation layer (Day 3).

Renders a case's priority into a readable sentence from its `scoring_components` rows
AND NOTHING ELSE. One template per component, driven by input_name / raw_value /
normalized_value / weight / contribution. Templates alone produce a complete sentence, so
the whole thing runs with the LLM disabled — which is the default and the demo path.

If an LLM is later enabled to smooth phrasing, it may ONLY rephrase: it receives the
component rows, and `find_invented_numbers()` rejects any number in its output that is not
already an allowed fact from those rows. The LLM can never introduce a fact the score
didn't use — that guarantee is enforced here, not trusted to the model.
"""

from __future__ import annotations

import re

TEMPLATE_VERSION = "explain-v1"


# --- small formatters ------------------------------------------------------

def _ordinal(n: int) -> str:
    if 10 <= (n % 100) <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def _severity_level(w: float) -> str:
    return "high" if w >= 0.7 else "moderate" if w >= 0.4 else "low"


def _crit_level(w: float) -> str:
    return "high-criticality" if w >= 1.3 else "elevated-criticality" if w >= 1.1 else "standard"


def _duration(hours: float) -> str:
    if hours >= 48:
        return f"{round(hours / 24)} days"
    if hours >= 1:
        return f"{round(hours)}h"
    return "under an hour"


# --- per-component templates ----------------------------------------------
# Each returns a clause built ONLY from that component's raw_value. Returns None when the
# component didn't contribute (e.g. a first occurrence has no recurrence signal).

def _clause(name: str, rv: dict) -> str | None:
    if name == "severity":
        if rv.get("safety_flag"):
            return "flagged as a health & safety hazard"
        return f"{_severity_level(float(rv['severity_weight']))} category severity"
    if name == "people_affected":
        n = int(rv["reporter_count"])
        reports = f"{n} report" + ("" if n == 1 else "s")
        return f"affects a location of ~{int(rv['population'])} people with {reports}"
    if name == "recurrence":
        if int(rv.get("prior_occurrences", 0)) <= 0:
            return None
        return f"the {_ordinal(int(rv['occurrence_seq']))} recorded occurrence of this fault"
    if name == "age_vs_sla":
        ratio = float(rv.get("ratio", 0))
        rel = "past" if ratio >= 1 else "within"
        return f"open {_duration(float(rv['hours_open']))}, {rel} the {int(rv['sla_hours'])}h SLA"
    if name == "location_criticality":
        level = _crit_level(float(rv["criticality_weight"]))
        article = "an" if level[0] in "aeiou" else "a"
        return f"at {article} {level} location"
    return None


def render(total_score: float, components: list[dict], audience: str = "student") -> str:
    """Build the explanation from component rows, ordered by contribution (biggest driver
    first). Only components that actually contributed are cited.

    audience:
      "student"    — judge-facing / reporter-facing: NO per-component (+pts) annotations.
      "department" — console: shows each factor's (+pts) contribution.

    Recurrence is pulled out as a prominent LEAD so two occurrences of the same recurring
    fault (adjacent scores, same category+location) cannot be misread as a dedup failure.
    """
    show_pts = (audience == "department")
    ordered = sorted(components, key=lambda c: float(c["contribution"]), reverse=True)

    lead = ""
    rec = next((c for c in components if c["input_name"] == "recurrence"), None)
    if rec and int(rec["raw_value"].get("prior_occurrences", 0)) > 0:
        rv = rec["raw_value"]
        seq = int(rv["occurrence_seq"])
        when = _fmt_date(rv.get("occurrence_date"))
        opened = f", opened {when}" if when else ""
        pts = f" (+{round(float(rec['contribution']))})" if show_pts else ""
        lead = f"Recurring fault — {_ordinal(seq)} occurrence of this issue{opened}{pts}. "

    clauses = []
    for c in ordered:
        if c["input_name"] == "recurrence":
            continue  # promoted into the lead
        contrib = float(c["contribution"])
        if contrib <= 0.0001:
            continue
        txt = _clause(c["input_name"], c["raw_value"])
        if txt is None:
            continue
        clauses.append(txt + (f" (+{round(contrib)})" if show_pts else ""))

    body = (" — driven by " + "; ".join(clauses)) if clauses else ""
    return f"{lead}Priority {round(total_score)}/100{body}."


_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _fmt_date(iso: str | None) -> str | None:
    if not iso:
        return None
    try:
        y, m, d = (int(x) for x in iso.split("-"))
        return f"{d} {_MONTHS[m - 1]} {y}"
    except (ValueError, IndexError):
        return None


# --- LLM-path safety guard (used only when smoothing is enabled) -----------
#
# The template is the vetted source of truth. An LLM smoother is asked ONLY to rephrase a
# template explanation, so its output may not contain any number the template didn't state
# (plus the raw component facts and the fixed 0-100 scale, as a safety superset). If it
# does, we reject the smoothed text and fall back to the template. This is why templates
# themselves are never "guarded" against — they DEFINE what is allowed.

_NUM = re.compile(r"\d+(?:\.\d+)?")


def numbers_in(text: str) -> set[str]:
    return {_fmt(float(m)) for m in _NUM.findall(text)}


def allowed_numbers(total_score: float, components: list[dict]) -> set[str]:
    """The raw numeric facts from the record: total, each contribution/normalized/weight,
    and every numeric value in every raw_value."""
    out: set[str] = set()

    def add(x):
        try:
            fx = float(x)
        except (TypeError, ValueError):
            return
        out.add(_fmt(fx))
        out.add(_fmt(round(fx)))

    add(total_score)
    for c in components:
        add(c["contribution"])
        add(c["normalized_value"])
        add(c["weight"])
        for v in c["raw_value"].values():
            add(v)
    return out


def allowed_for_smoothing(template_text: str, total_score: float,
                          components: list[dict]) -> set[str]:
    """Every number an LLM smoother may keep: the vetted template's own numbers, the raw
    component facts, and the fixed 0-100 scale. Anything else in its output is invented."""
    return numbers_in(template_text) | allowed_numbers(total_score, components) | {"100"}


def find_invented_numbers(text: str, allowed: set[str]) -> set[str]:
    """Numbers in `text` that are NOT in `allowed`. Non-empty => reject and fall back."""
    return {n for n in numbers_in(text) if n not in allowed}


def _fmt(x: float) -> str:
    xf = float(x)
    return str(int(xf)) if xf == int(xf) else f"{xf:g}"
