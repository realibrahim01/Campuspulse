# Day 2 decisions — clustering & scoring

A findable record of the choices made on 9 Sep 2026 (Part A/B/C). Numbers here are
meant to be cited to judges.

## Part A — candidate-retrieval matcher

For each report (processed in `created_at` order, replaying live arrival):
1. **Embed** with `all-MiniLM-L6-v2` (384-d, L2-normalized). Local, no API key.
2. **Hard filter, before any similarity math:** candidate = OPEN case with the **same
   `location_id`** whose last activity is within the **recency window `W`**.
3. **Similarity:** cosine(report, case running-centroid) for each candidate.
4. **Attach if best ≥ threshold `T`**, folding the report into the centroid; else **open a
   new case**, which links to an existing fault at the same location+category
   (recurrence, `occurrence_seq = count+1`) or starts a new fault (`seq = 1`).

### Why location is a pre-filter, not a feature
Checked before embeddings are compared, so near-miss reports (identical wording, different
`location_id`) are **never compared** — no threshold can merge them. Hard by construction.

### Why the recency window W — the duplicate-vs-recurrence boundary (CITE THIS)
Measured on the 332-report seed set, straight from the database:

| Quantity | Value |
|---|---|
| Max spread of reports **within** one occurrence | **43.9 hours** (~1.8 days) |
| Min gap **between** consecutive occurrences of the same fault | **20.9 days** |

That is an ~11× separation. Any `W` in **~3–15 days** merges same-occurrence duplicates
while letting the next occurrence fall through to a **new case under the same fault**
(which is exactly what recurrence detection needs). **Default W = 7 days**, mid-band with
margin on both sides. W is swept in the eval.

### Model
Production model is `all-MiniLM-L6-v2` and is NOT being changed on Day 2 — swapping models
changes the embedding dimension and would force migrating persisted vectors. Hinglish
(code-mixed EN/HI) is the known weak spot; the eval compares against
`paraphrase-multilingual-MiniLM-L12-v2` **eval-only** so we can decide on Day 3 with
numbers in hand. FAISS owns the vector index (per the architecture); at this scale the
per-location candidate search is exact.

## Part B — threshold sweep (results, 9 Sep 2026)

Ground truth read ONLY from `report_provenance` (never joined into matching).
Full tables: `docs/day2_sweep_results.md` (W=7) and `docs/day2_sweep_lowT_W3.md` (W=3).
Truth for a same-case pair = same `gt_occurrence_id`.

### The precision cliff (all-MiniLM-L6-v2, W=3 days)

| T | precision | recall | F1 | runtime cases | FP pairs |
|---|---|---|---|---|---|
| 0.18 | 0.966 | 1.000 | 0.983 | 57 | 32 |
| 0.24 | 0.965 | 0.960 | 0.962 | 61 | 32 |
| **0.26** | **1.000** | **0.960** | **0.979** | 63 | **0** |
| 0.30 | 1.000 | 0.932 | 0.965 | 68 | 0 |
| 0.40 | 1.000 | 0.819 | 0.900 | 78 | 0 |

Below T=0.26, 32 pairs of DISTINCT problems merge (precision drops). At 0.26+ precision
is 1.000. Above 0.26 buys no precision and only loses recall + Hinglish.

### Window sweep confirms the W justification
At T=0.18: W=3 → P=0.966; W=7 → P=0.929; W=14 → P=0.919; **W=30 → P=0.274** (collapses,
because 30 d > the 20.9 d inter-occurrence gap, so separate occurrences merge). This is
the 43.9 h / 20.9 d separation showing up directly in the numbers.

### Structure checks — PASS at the chosen region (0.18–0.30, W=3)
- near-miss pairs (3/3): NOT merged (location hard-gate; independent of T).
- singletons (4/4): each alone in its own case.
- largest group `wifi_hostelB#3` (10 reports): 1 case, 0 foreign reports.

### Centroid drift — clean
Across T ∈ [0.18, 0.30], **0 members** fall below threshold vs their case's FINAL centroid
— i.e. no member is carried by drift; every member is genuinely similar to the final
cluster. Attach→final gap is positive (clusters tighten), mean ≈ 0.12.

### Hinglish (code-mixed) — the honest weak spot, W=3
en-hi = cross-lingual positive pairs (one English + one Hinglish report):

| T | all-MiniLM en-hi | multilingual en-hi | all-MiniLM hi-hi | multilingual hi-hi |
|---|---|---|---|---|
| 0.26 | 0.910 | 0.959 | 1.000 | 1.000 |
| 0.30 | 0.854 | 0.934 | 0.982 | 0.982 |

Same-language Hindi merges fine on both. Cross-lingual is where the production model
(all-MiniLM) trails the multilingual model by ~5 pts at T=0.26, widening at higher T.
Production model stays all-MiniLM (no dim migration on Day 2); this table is the evidence
for the Day-3 model decision.

### Recommendation (pending user confirmation)
**T = 0.26, W = 3 days.** Highest-recall point that still has PERFECT precision
(P=1.000, R=0.960, F1=0.979), best achievable Hinglish on the production model (0.910),
all structure checks pass, drift clean.
Cost on the recall side: ~4% of same-occurrence pairs split (63 cases vs 59 true; the
SAFE error — under-merge, never wrong-merge). Cost on Hinglish: ~9% of cross-lingual
pairs still miss (all-MiniLM limit, revisit Day 3).

> **Chosen: T = 0.26, W = 3 days** (confirmed by the user, 9 Sep 2026).
> P=1.000, R=0.960, F1=0.979 on the 332-report seed set; all structure checks pass;
> drift clean. Locked in `persist_cases.py` and the live matcher config.

## Part C — scoring engine (built & verified, 9 Sep 2026)

Pure function `score_case(facts, weights, as_of)` in `campuspulse_intel/scoring.py`;
driver `score_cases.py`. Five components, each normalized to 0–1, weighted from
`scoring_weights`, summed, scaled to 0–100:

| Component | Raw inputs | Normalization |
|---|---|---|
| severity | category `severity_weight`, `safety_flag` | base + 0.2 safety bump, clamp 1 |
| people_affected | `reporter_count`, location `population` | 0.5·(rep/10) + 0.5·(pop/500) |
| recurrence | `occurrence_seq` | (seq−1)/5, clamp 1 — first occurrence scores 0 |
| age_vs_sla | hours open vs dept SLA (routed dept, else category default) | min(ratio,3)/3 |
| location_criticality | location `criticality_weight` | crit/1.5, clamp 1 |

**Determinism / reproducibility:** the only time-dependent input (age) is computed against
an explicit `as_of` timestamp that is stored on the record along with every raw input. Same
`(facts, weights, as_of)` → byte-identical score (verified: two dry runs identical). A
re-score is a NEW append-only `scoring_record`; records are never mutated. No LLM anywhere.

**Persisted & verified:** 63 scoring_records, 315 scoring_components (63×5), all 63 cases
have `priority_score` + `current_scoring_record_id`, one `audit_log` SCORE_COMPUTED per
case. Integrity check: component contributions sum to `total_score` for **all 63** records
(0 mismatches) — this is what lets the explanation layer render from `scoring_components`
alone and never cite an input the score didn't use.

Top case: recurring (5th occurrence) SANITATION+safety issue at a high-population washroom,
past SLA — the ranking is legible straight from its component contributions.
