# CampusPulse — demo walkthrough (12 Sep)

Runnable cold. ⭐ = the three that survive a 5-minute cut (segments 1, 2, 3).
Honest-framing rules are baked in — say them as written, don't overclaim.

## Pre-flight (once, ~1 min before you present)
Run everything in ONE terminal — the scripts read the DB password from the gitignored
`.env` and set it for the session, so no password is typed anywhere.
```powershell
cd C:\Users\ibrah\CampusPulse
.\demo\stack_up.ps1                    # reads .env; starts API :8080, console :5173, Expo :8081
# wait ~30s for Expo to bundle, then:
.\demo\routing_fix_demo.ps1 -Reset     # routing rests at the 93.7% baseline
```
Baseline state — check the two things that are actually stable: routing **93.7%**, and case
**51** = `SANITATION @ Men's Washroom Hostel A`, priority **84**. (Case and report counts rise
by one every time someone submits through the app, so don't treat those as fixed numbers.)
(If data was rebuilt from scratch, run `.\demo\rescore.ps1` before the `-Reset`.)

---

## ⭐ 1. Cross-lingual clustering — case 51 (the best thing we built)
**Click:** open `http://localhost:5173` → sign in `admin@campus.edu` / `campus123` →
in the queue click the **top row** (case #51, score 84, "Sanitation · Men's Washroom
Hostel A") → in the detail scroll to **"Reports on this case (7)"**.
**Say:** "Seven reports auto-merged into one case. Two of them: *'Toilet blocked in Hostel A
washroom, water everywhere'* and *'hostel A washroom me pani bhara hua hai, toilet band hai'*
— English and Hindi, same fault, merged with no translation: pretrained multilingual
embeddings plus a hard location filter. And each report reads *'identity withheld by policy'*
— anonymity enforced at the query layer."
**Shows:** clustering (the hard part) working, cross-lingual, on screen, no slide.

## ⭐ 2. Routing is measured, and configurable — the live fix
**Run:**
```powershell
.\demo\routing_fix_demo.ps1
```
Step 1 prints **93.7%**; step 2 lists the 4 misroutes; [Enter]; step 3 adds one rule;
[Enter]; step 4 → **100%**.
**Say:** "Routing accuracy is measured against ground truth — 93.7%. The four misses are
outdoor water-logging routed to Housekeeping when it should be Civil. One configurable rule
— sanitation at an outdoor location → Civil — and we re-route to 100%, no restart. We say
*'93.7% measured; one rule closes the gap'* — **not** '100% accurate'."
**Shows:** honest measurement + per-institution configurability.

## ⭐ 3. Explanations can't be faked — the fact-guard
**Run:**
```powershell
& C:\Users\ibrah\miniconda3\python.exe C:\Users\ibrah\CampusPulse\intelligence\explain_cases.py
```
Look at the **bottom** ("fact-guard" block).
**Say:** "Every priority explanation is generated from the score's own components — no free
text. An optional LLM may smooth wording, but a deterministic guard rejects any number it
didn't get from the score. The real explanation passes; a fabricated '9999 rooms' is caught.
That's why every explanation is defensible."
**Shows:** the auditability guarantee (`template → passes`, `fabricated → flags {9999}`).

---
### ▶ 5-MINUTE CUT ENDS HERE (segments 1–3). Below is the full demo.
---

## 4. OPTIONAL — live submission: a fresh report scores ~0 on age
**Only run this if you're tracking under 5:30.** It comes after the routing demo and is the
one droppable beat — the admin dashboard below is the sixth feature and is NOT optional.

**Click:** open `http://localhost:8081` → sign in `student01@campus.edu` / `campus123` →
"What's wrong?" = *"Water leaking under the sink in Lab 1"* · Category **Water supply** ·
Location **Lab 1** → **Submit report** (shows "awaiting triage").
**Run** — the full five-step rebuild, **~15 seconds measured**. Run all five: skipping steps
leaves every case with a blank department and empties the Patterns view.
```powershell
.\demo\rescore.ps1
& 'C:\Program Files\PostgreSQL\18\bin\psql.exe' -U postgres -h localhost -d campuspulse -c "SELECT sc.input_name, sc.contribution FROM cases c JOIN scoring_components sc ON sc.scoring_record_id=c.current_scoring_record_id WHERE c.id=(SELECT max(id) FROM cases) ORDER BY sc.contribution DESC;"
```

**DON'T IMPROVISE INTO SILENCE — say these two while it runs (~15s of cover):**

> **(1) Nothing cached.** "What's running is a full rebuild — every report re-embedded and
> re-scored from scratch, nothing cached."

> **(2) Batch by design.** "And clustering is a batch job on purpose. A report isn't merged the
> instant it lands — it's compared against the case centroids in one deterministic pass, so the
> same inputs always produce the same merge, and we can re-run it later and audit why any two
> reports were grouped together. That's the trade: a few seconds of latency for a decision we
> can defend."

**Say (on the result):** "Scored moments after it opened, so age-vs-SLA contributes ~0 — unlike
the historical backlog where everything is long overdue and maxed at +20. The component
discriminates by freshness; the synthetic backlog just can't show that on its own."
**Shows:** `age_vs_sla ≈ 0` on the newest case. (rescore re-routes to baseline and re-acks.)

## 5. We can't cheat the metrics — the provenance gap
**Run:**
```powershell
& 'C:\Program Files\PostgreSQL\18\bin\psql.exe' -U postgres -h localhost -d campuspulse -c "SELECT (SELECT count(*) FROM reports) reports, (SELECT count(*) FROM report_provenance) provenance;"
```
**Say** (read the two numbers off the screen — don't memorise them): "Reports outnumber
provenance rows by exactly the number of app-submitted reports. Every seeded report has a
ground-truth row; every real one submitted through the app has none — so the gap grows by one
each time someone actually reports something. Ground-truth labels (which fault, which
department) live only in the provenance table, and the pipeline never joins it. So clustering
at 96% and routing at 93.7% are measured against an answer key the system physically cannot
read."
**Shows:** methodological honesty.

---
## Admin dashboard (full demo) — SAY THE DISCLOSURE
**Click:** in the console (as admin) click the **Patterns** tab → three views.
**Say (on the middle view):** "One disclosure up front: the demo runs on a synthetic
historical dataset with no real acknowledgement history, so we synthesise it to demonstrate
the view computes. **These per-department medians are a demonstration, not a measured
finding.** The recurring-faults and open-volume views are real pipeline output."

## Teardown
```powershell
.\demo\stack_down.ps1
```
