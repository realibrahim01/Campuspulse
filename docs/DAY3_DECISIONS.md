# Day 3 decisions — explanation layer, routing, console

Order: explanation layer → routing rules + classification → department console → Expo
submit/list screen last.

## Explanation layer (built & verified, 10 Sep 2026)

`campuspulse_intel/explain.py` (pure renderer) + `explain_cases.py` (driver). An
explanation is rendered from a case's `scoring_components` rows AND NOTHING ELSE — one
template per component, driven by `input_name` / `raw_value` / `normalized_value` /
`weight` / `contribution`. Components are ordered by contribution (biggest driver first)
and only contributing components are cited (a first-occurrence case never mentions
recurrence). Written to `scoring_records.explanation_text` (template `explain-v1`).

**Templates alone produce a complete sentence — the LLM is disabled by default and this is
the demo path.** An optional LLM smoother is a bounded seam: it would receive only the
component rows + the template, and `find_invented_numbers()` rejects any number in its
output not already present (template numbers ∪ raw component facts ∪ the fixed 0-100
scale). The LLM can only rephrase; it can never introduce a fact the score didn't use —
enforced in code, not trusted to the model. Guard demo: the template passes; a fabricated
"9999 rooms" variant is flagged.

### Two audiences (10 Sep 2026)
- **Student / judge-facing view** (stored in `explanation_text`): no `(+pts)` annotations.
- **Department console view** (`render(..., "department")`): shows each factor's `(+pts)`.
Recurrence is promoted to a LEAD ("Recurring fault — Nth occurrence…, opened <date>") so two
occurrences of one recurring fault (adjacent scores, same category+location) can't be
misread as a dedup failure. The occurrence date is carried in the recurrence component's
`raw_value`, so the explanation still reads from `scoring_components` only.

### Top-5 STUDENT VIEW (DEMO COPY — templates only, LLM disabled)

```
[case 51] SANITATION @ Men's Washroom Hostel A
  Recurring fault — 5th occurrence of this issue, opened 30 Aug 2026. Priority 84/100 —
  driven by flagged as a health & safety hazard; open 10 days, past the 12h SLA; affects a
  location of ~300 people with 7 reports; at an elevated-criticality location.

[case 36] SANITATION @ Men's Washroom Hostel A
  Recurring fault — 4th occurrence of this issue, opened 4 Aug 2026. Priority 83/100 —
  driven by flagged as a health & safety hazard; open 35 days, past the 12h SLA; affects a
  location of ~300 people with 9 reports; at an elevated-criticality location.

[case 42] SANITATION @ Central Canteen
  Recurring fault — 3rd occurrence of this issue, opened 16 Aug 2026. Priority 80/100 —
  driven by flagged as a health & safety hazard; open 23 days, past the 12h SLA; affects a
  location of ~400 people with 7 reports; at an elevated-criticality location.

[case 39] ELECTRICAL @ Academic Block Corridor
  Recurring fault — 2nd occurrence of this issue, opened 13 Aug 2026. Priority 80/100 —
  driven by flagged as a health & safety hazard; open 27 days, past the 24h SLA; affects a
  location of ~500 people with 6 reports; at an elevated-criticality location.

[case 62] ELECTRICAL @ Academic Block Corridor
  Recurring fault — 3rd occurrence of this issue, opened 6 Sep 2026. Priority 79/100 —
  driven by flagged as a health & safety hazard; open 3 days, past the 24h SLA; affects a
  location of ~500 people with 3 reports; at an elevated-criticality location.
```

Every number traces to a component; nothing is asserted that the score didn't compute.

### Age-vs-SLA saturation (measured, flagged 10 Sep 2026)
Across all 63 cases the age component is saturated: **57/63 sit at the max** (avg
normalized 0.976), because the synthetic set is HISTORICAL — occurrences opened
days-to-months ago (median 38× the SLA, max 226×) against hour-scale SLAs. This is a
data artifact, not a scoring bug: capping at 3× is correct (226× overdue is not
meaningfully more urgent than 3× overdue), and age still discriminates between fresh and
old cases (a report open 6h vs a 24h SLA → ratio 0.25 → +1.7, not +20). On a historical
backlog "everything is overdue," so ranking is correctly driven by the other four
components. **Decision: weights unchanged at w_age_sla=0.20 (production-correct); demo the
dynamic range live by submitting a fresh report.** Revisit only if the user wants age to
visibly spread across historical cases (would need soft/log normalization — not
recommended, it tunes the metric to the data).

## Routing rules + classification (built & measured, 10 Sep 2026)

`intelligence/route_cases.py` — deterministic rule engine over the seeded `routing_rules`,
evaluated in `rule_order`: a rule matches when its category / location-type / keyword (in
the case title) all match; first match wins; a per-category catch-all (rule_order 1000)
guarantees every case routes. Sets `cases.department_id` + `cases.sla_due_at`, logs
`ROUTE_ASSIGNED`. No ML (out of scope) — transparent, configurable rules.

**Measured vs gt_department (read only for scoring, never to route): 59/63 = 93.7%.**
Case load: Electrical 16, Housekeeping 14, Water 13, IT 13, Civil 4, Security 3.

**The 4 misses are one pattern:** `Housekeeping -> should be Civil Maintenance` — the
stagnant-water-at-back-gate cases. They're SANITATION category (default → Housekeeping),
but ground truth routes outdoor water-logging to Civil (drainage). The seeded rule for this
(`SANITATION + GROUNDS → Civil`) doesn't fire because Back Gate's location type is `OTHER`,
not `GROUNDS`. This is exactly a **configurable-routing** case: an admin adds one rule
(e.g. keyword "logging"/"stagnant" or `SANITATION + OTHER → Civil Maintenance`) and it goes
to 100%.

**Resolved: keep 93.7% and fix it LIVE on stage** (`demo/routing_fix_demo.ps1`, verified
end-to-end and rehearsable): STEP 1 baseline 93.7% -> STEP 2 show the 4 misroutes (cases 10,
11, 26, 43) -> STEP 3 add rule #25 (`SANITATION + OTHER -> Civil Maintenance`) -> STEP 4
re-route -> 100%. No cache / no restart: `route_cases.py` SELECTs `routing_rules` fresh every
run, so the live INSERT applies on the next re-route. The script self-resets each run
(removes rule #25 first) and has `-Reset` / `-NoPause`. **Framing rule: say "93.7% measured
against ground truth; one config rule closes the gap" - never "100% accurate."** Resting DB
state is the honest 93.7% baseline. When the Spring console adds a routing/re-route endpoint,
it must read rules cache-free (no `@Cacheable`) to preserve this guarantee.

## Department console (built & verified, 10 Sep 2026)

Backend (Spring API, JdbcTemplate — read-optimized, avoids 8 more validate-checked entities):
- `GET /cases` — prioritized queue; DEPARTMENT sees only its own cases, ADMIN sees all.
- `GET /cases/{id}` — scoring breakdown (components + contributions) + explanation + reports
  (text only; reporter identity never selected). Cross-department access returns 404.
- `PATCH /cases/{id}/status` — status + `case_status_events` + one notification per reporter
  (Track) + `STATUS_CHANGE` audit.
- `PATCH /cases/{id}/department` — manual override, recomputes `sla_due_at`, `ROUTE_OVERRIDE`.
- `GET /departments` — reference list for the override dropdown.
Role scoping and identity-hiding are enforced in `CaseService`, not just the URL rules.
(Two fixes worth noting: NUMERIC -> BigDecimal converter for JDBC; CORS for the Vite origin.)

Frontend (`console/`, React + Vite, plain): login -> prioritized queue (color-coded priority)
-> case detail with the `+pts` breakdown table, explanation, status dropdown, override
dropdown. Verified live via the browser: queue scoping, breakdown, controls, and the reports.

**Reporter identity is made VISIBLE, not just absent:** each report renders
"🔒 Reported anonymously · identity withheld by policy" where a name would be — turns the
anonymity limitation into something judges can see. (Screenshots couldn't be captured in this
env due to a CDP timeout; verified via the accessibility tree instead.)

Run: API on :8080, then `cd console && npm run dev` (:5173), sign in as house@campus.edu /
it@campus.edu / admin@campus.edu, password campus123.

## DEMO KEEPERS (do not lose)

- **Case #51 — English + Hinglish reports merged into one visible case.** In the console's
  case detail, the same washroom fault appears as both "Toilet blocked in Hostel A washroom,
  water everywhere" and "hostel A washroom me pani bhara hua hai, toilet band hai", clustered
  into a single case. This is the single strongest artifact we've built: it shows
  cross-lingual clustering working on screen, with no slide needed to explain it. Open case
  51 in the console during the demo. (Depends on the seed load; case id is stable given the
  fixed RNG + pipeline order.)

## Expo student app (built & verified, 10 Sep 2026)

`mobile/` — Expo (React Native, blank template, JS), Node 22.20.0 LTS via nvm. Screens:
login -> report form (description, category picker, location picker, optional specific
spot) -> "My reports" list. `GET /reports` is scoped so a STUDENT sees only their own
reports; POST creates a raw report (caseId null -> shows "Submitted · awaiting triage").
Added API endpoints `GET /categories`, `GET /locations`, scoped `GET /reports`; CORS
widened to `http://localhost:*` for the Vite (5173) and Expo web (8081) origins.

Verified end-to-end on Expo web (browser): login, form with 8 categories / 19 locations,
submit -> success + "My reports" went 5 -> 6. (Automation note: RN-web's press responder
ignores a synthetic click; a real tap works — verified by dispatching a full pointer
sequence.) Left one app-submitted report in the DB from the E2E test (student01, "Fan not
working Room 210", unclustered). **KEEP IT — deliberate demo artifact** for age-vs-SLA's
low end (a fresh report scores ~0 on age). Do NOT reload the seed, or it disappears
(reports would drop back to 332 seed-only). If you must rebuild data, re-submit one fresh
report from the student app afterward.

Run: API on :8080, then `cd mobile && npx expo start` -> press `w` for web, or scan the QR
with Expo Go (for a phone, change `BASE` in mobile/api.js from localhost to the machine's
LAN IP). Login student01@campus.edu / campus123.

## Pattern dashboard — admin view (built & verified, 10 Sep 2026)

The 6th in-scope feature and the entire ADMIN view (admin is one of our three user types).
Three read-only views, exactly as scoped, in the React console under an admin-only tab:
1. Recurring faults ranked by occurrence count.
2. Departments ranked by median time to acknowledge (first move off NEW).
3. Locations ranked by open case volume (not resolved/closed).

Backend: `GET /admin/patterns` (ADMIN only, 403 otherwise) + `GET /me` (so the console shows
the Patterns tab only to admins). Frontend: `Patterns.jsx`, role-gated nav in `App.jsx`.
No new dependencies. Verified in-browser as admin (tables populate; department login has no
Patterns tab).

**Data dependency — SAY THIS PLAINLY, don't wait to be asked.** The "median time to
acknowledge" view needs acknowledgement history, which the historical seed lacks.
`intelligence/seed_activity.py` SYNTHESISES it: ~70% of cases get a NEW→ASSIGNED event at
opened_at + a per-department delay (the rest stay NEW as a backlog). **The per-department
medians (Security ~2h → Civil ~59h) are a DEMONSTRATION that the view computes correctly —
they are NOT a measured finding about real departments.** This is part of the same
synthetic-dataset limitation already on our slide ("the demo runs on a synthetic dataset").
The recurring-faults and open-volume views use real pipeline output; only the ack timings
are synthesised. Run seed_activity AFTER route_cases.py.

**Fix (10 Sep):** `persist_cases.py` cleared `scoring_records` before nulling
`cases.current_scoring_record_id`, which fails the FK once scoring exists (any rebuild after
the first score). Fixed by nulling the case→score reference first. Added `demo/rescore.ps1`
(the full pipeline in one command; uses HF_HUB_OFFLINE so ML stderr warnings don't abort it)
— run it after a live report submission to cluster+score it (fresh report -> age ≈ 0,
verified: hours_open 0.02 -> age contribution 0.004).

**Full data-rebuild pipeline (order matters):**
  persist_cases -> route_cases -> score_cases --fresh -> explain_cases -> seed_activity
(then the stray student01 fresh report is gone — re-submit one from the app if needed.)

--- ALL SIX IN-SCOPE FEATURES SHIP + BOTH CLIENTS BUILT. Day 4 = testing & rehearsal. ---
