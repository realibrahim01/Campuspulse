"""
Candidate-retrieval matcher (Part A).

Pure, deterministic matching over in-memory state. Reads ONLY report fields
(text embedding, location_id, category_id, timestamp) — never ground truth. The eval
drives it over precomputed embeddings so a full threshold sweep costs no DB writes.

Decision per report (processed in chronological order):
  1. HARD FILTER (before any similarity math): open cases at the SAME location_id whose
     last activity is within the recency window W.
  2. cosine(report, case running-centroid) over those candidates.
  3. best >= T  -> attach (fold into centroid);  else open a NEW case.
  4. A new case links to an existing fault at the same (location, category) if similar
     to that fault's centroid (recurrence), else starts a new fault.

Vectors are assumed L2-normalized, so dot product == cosine similarity.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class ReportInput:
    report_id: int
    emb: np.ndarray          # L2-normalized 384-d
    location_id: int
    category_id: int
    ts: float                # epoch seconds


@dataclass
class CaseState:
    case_id: int
    location_id: int
    category_id: int
    fault_id: int
    occurrence_seq: int                        # 1st/2nd/3rd occurrence of its fault
    opened_ts: float                           # earliest member ts (= seed ts)
    sum_vec: np.ndarray                       # running sum of member embeddings
    centroid: np.ndarray                      # sum_vec normalized
    n: int
    last_activity: float
    member_report_ids: list = field(default_factory=list)
    member_embs: list = field(default_factory=list)   # kept for drift analysis
    attach_sims: list = field(default_factory=list)   # sim vs centroid at attach; None for seed


@dataclass
class FaultState:
    fault_id: int
    location_id: int
    category_id: int
    sum_vec: np.ndarray
    centroid: np.ndarray
    occurrence_count: int = 0


class Matcher:
    def __init__(self, threshold: float, window_days: float,
                 recurrence_threshold: Optional[float] = None):
        self.T = float(threshold)
        self.W = float(window_days) * 86400.0
        # Recurrence uses the same similarity bar by default but no recency window.
        self.RT = float(recurrence_threshold) if recurrence_threshold is not None else float(threshold)
        self.cases: list[CaseState] = []
        self.faults: list[FaultState] = []
        self.cases_by_loc: dict[int, list[int]] = defaultdict(list)
        self.faults_by_lc: dict[tuple, list[int]] = defaultdict(list)
        self._next_case_id = 1
        self._next_fault_id = 1
        # assignment result: report_id -> case_id
        self.assignment: dict[int, int] = {}

    # --- public ---------------------------------------------------------------

    def process(self, r: ReportInput) -> int:
        """Assign one report; returns its case_id. Reports must arrive in ts order."""
        best_case: Optional[CaseState] = None
        best_sim = -1.0
        # [1] hard filter: same location, within recency window. Similarity is computed
        # ONLY for cases that pass — different-location cases are never compared.
        for ci in self.cases_by_loc[r.location_id]:
            c = self.cases[ci]
            if r.ts - c.last_activity <= self.W:
                sim = float(np.dot(r.emb, c.centroid))   # [2]
                if sim > best_sim:
                    best_sim = sim
                    best_case = c

        if best_case is not None and best_sim >= self.T:   # [3] attach
            self._attach(best_case, r, best_sim)
            cid = best_case.case_id
        else:                                              # [3] open new case
            cid = self._open_case(r)

        self.assignment[r.report_id] = cid
        return cid

    # --- internals ------------------------------------------------------------

    def _attach(self, c: CaseState, r: ReportInput, sim_at_attach: float) -> None:
        c.attach_sims.append(sim_at_attach)
        c.sum_vec = c.sum_vec + r.emb
        c.centroid = _norm(c.sum_vec)
        c.n += 1
        c.last_activity = max(c.last_activity, r.ts)
        c.member_report_ids.append(r.report_id)
        c.member_embs.append(r.emb)

    def _open_case(self, r: ReportInput) -> int:
        fault = self._link_fault(r)                        # [4]
        cid = self._next_case_id
        self._next_case_id += 1
        c = CaseState(
            case_id=cid, location_id=r.location_id, category_id=r.category_id,
            fault_id=fault.fault_id,
            occurrence_seq=fault.occurrence_count + 1,   # this is the Nth occurrence
            opened_ts=r.ts,
            sum_vec=r.emb.copy(), centroid=r.emb.copy(),
            n=1, last_activity=r.ts,
            member_report_ids=[r.report_id], member_embs=[r.emb],
            attach_sims=[None],   # seed member has no attach similarity
        )
        self.cases.append(c)
        self.cases_by_loc[r.location_id].append(len(self.cases) - 1)
        fault.occurrence_count += 1
        return cid

    def _link_fault(self, r: ReportInput) -> FaultState:
        """Recurrence: same location+category and similar to the fault centroid (no
        recency window — recurrence is by definition across time)."""
        best: Optional[FaultState] = None
        best_sim = -1.0
        for fi in self.faults_by_lc[(r.location_id, r.category_id)]:
            f = self.faults[fi]
            sim = float(np.dot(r.emb, f.centroid))
            if sim > best_sim:
                best_sim = sim
                best = f
        if best is not None and best_sim >= self.RT:
            best.sum_vec = best.sum_vec + r.emb
            best.centroid = _norm(best.sum_vec)
            return best
        fid = self._next_fault_id
        self._next_fault_id += 1
        f = FaultState(fault_id=fid, location_id=r.location_id, category_id=r.category_id,
                       sum_vec=r.emb.copy(), centroid=r.emb.copy())
        self.faults.append(f)
        self.faults_by_lc[(r.location_id, r.category_id)].append(len(self.faults) - 1)
        return f

    # --- drift analysis (for the eval) ---------------------------------------

    def drift_report(self) -> dict:
        """For each non-seed member: similarity to the FINAL centroid vs at attach.
        Surfaces members carried by centroid drift rather than genuine similarity."""
        gaps = []            # sim_final - sim_at_attach (non-seed members)
        below_T_vs_final = 0  # members that would NOT attach to the final centroid
        marginal = 0          # attached within a hair of the threshold
        total_members = 0
        worst = []            # (gap, case_id, attach_sim, final_sim)
        for c in self.cases:
            for emb, att in zip(c.member_embs, c.attach_sims):
                total_members += 1
                sim_final = float(np.dot(emb, c.centroid))
                if sim_final < self.T:
                    below_T_vs_final += 1
                if att is None:
                    continue
                gap = sim_final - att
                gaps.append(gap)
                if att <= self.T + 0.05:
                    marginal += 1
                worst.append((gap, c.case_id, att, sim_final))
        gaps_arr = np.array(gaps) if gaps else np.array([0.0])
        worst.sort(reverse=True)
        return {
            "members_total": total_members,
            "non_seed_members": len(gaps),
            "marginal_attaches": marginal,          # attach_sim in [T, T+0.05]
            "below_T_vs_final_centroid": below_T_vs_final,
            "gap_mean": float(gaps_arr.mean()),
            "gap_p90": float(np.percentile(gaps_arr, 90)),
            "gap_max": float(gaps_arr.max()),
            "worst5": worst[:5],
        }


def _norm(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / n if n > 0 else v
