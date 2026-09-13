# CampusPulse — demo video recording script

Self-recorded, editable. **~3:55 with the optional Segment 4, ~3:00 without.** Read the
**SAY** lines verbatim while recording; **DO** is the click path; **ON SCREEN** is what the
frame shows. This is NOT `WALKTHROUGH.md` (that one is for a live judged session with pauses).

**Keepers, in order:** (1) case 51 — cross-lingual merge, (2) the routing live-fix. Those two
never get cut. **Segment 4 (live submission) is the flex** — include it only if the cut is
trending under **5:30**. Segment 5 (the pattern dashboard) is the sixth feature on the
abstract and is not optional.

## Recording setup (resolution & zoom)

- **Record at 1920×1080 (1080p).** Universally supported and compresses cleanly for upload.
- **Browser zoom 150%** on the console and the student app (`Ctrl` `+` twice). At 1080p this
  keeps the scoring table, the explanation, and the dashboard legible after compression, and
  the layouts still fit (console two-column, dashboard three cards).
- **Terminal font ~18–20 pt**, dark high-contrast theme.
- If your monitor is 1440p/4K, record a 1080p region or downscale — don't capture a small
  window on a big screen, or text turns to mush after compression.
- Close other tabs, silence notifications, hide the taskbar.

## Pre-flight checklist (do this BEFORE hitting record)

1. **Stack up:** `cd C:\Users\ibrah\CampusPulse ; .\demo\stack_up.ps1` — wait ~30 s for Expo
   to bundle. Confirm http://localhost:8080 (API), :5173 (console), :8081 (student app).
2. **Routing resting at 93.7%:** `.\demo\routing_fix_demo.ps1 -Reset` — confirm it prints
   `93.7%`. (If the data looks off, run `.\demo\rescore.ps1` then `-Reset` again.)
3. **Case 51 present:** open http://localhost:5173, sign in `admin@campus.edu` / `campus123`.
   Top of the queue must be **case #51, priority 84, "Sanitation · Men's Washroom Hostel A"**,
   and its detail must show both an English and a Hindi/Hinglish report. If not, run
   `.\demo\rescore.ps1` then `-Reset`.
4. **Pre-login both apps** (saves video time): console as `admin@campus.edu`; student app
   (http://localhost:8081) as `student01@campus.edu` — both `campus123`. Leave the console on
   the queue view.
   - **Confirm the student app is signed in as `student01`, NOT admin.** It must show the
     "Report a problem" form. A department/admin login now shows a "This app is for students"
     message instead of the form — correct behaviour, but wrong account for Segment 4.
5. **Browser zoom 150%** on both; **terminal ready** in the same window you ran the scripts in
   (so `PGPASSWORD` is already set for the psql one-liner in Segment 4).
6. Keep this script on a second screen / phone to read from.

---

## SEGMENT 1 — The problem (0:00–0:20)

**ON SCREEN:** Console queue (as admin), dozens of cases sorted by priority score.
**SAY:** *"Every campus can collect problem reports. The hard part is this — dozens of open
cases at once, and no way to know which to fix first. CampusPulse answers that question and
shows its reasoning. Quick honesty up front: this runs on a synthetic dataset, and I'll flag
what's synthetic as we go."*
**DO:** Start on the queue. Slowly scroll it once, top to bottom, then back to the top.

## SEGMENT 2 — Case 51: clustering, scoring, explanation (0:20–1:20)

**ON SCREEN:** Case 51 detail — reports list, then the breakdown table and explanation.
**SAY (as it opens):** *"Top of the queue, priority 84 — a recurring sanitation issue, the
fifth time this washroom has been reported."*
**DO:** Click the top row (**case #51**). Let the detail load. Scroll to **"Reports on this
case"**.
**SAY (over the reports):** *"Seven reports, merged into one case. Look at these two — one in
English, 'toilet blocked, water everywhere,' and one in Hindi, 'washroom me pani bhara hua
hai, toilet band hai.' Different languages, the same underlying fault, merged automatically.
No translation — pretrained multilingual embeddings plus a hard location filter."*
**DO:** Scroll up to the **"Why this score"** breakdown table.
**SAY (over the breakdown):** *"And here's why it ranks 84 — severity and safety, people
affected, recurrence, age against the SLA, location criticality. Every factor's points are
shown. The explanation up here is generated only from these numbers — by design it can't cite
a reason the score didn't actually use."*
**DO:** Point the cursor at one report's **"identity withheld by policy"** line.
**SAY:** *"And the reporter's identity is withheld by policy — anonymity is enforced in the
system, not left to trust."*

## SEGMENT 3 — Routing: measured, and configurable (1:20–2:10)

**ON SCREEN:** Terminal running the routing fix.
**SAY (as you switch):** *"Cases route to departments, and we measure that routing against
ground truth."*
**DO:** Alt-tab to the terminal. Run: `.\demo\routing_fix_demo.ps1 -NoPause`
**SAY (over the output):** *"93.7 percent. The misses are one pattern — outdoor water-logging
sent to Housekeeping when it should go to Civil. Routing is configurable per institution, so
I add one rule… and re-route. A hundred percent. To be precise: 93.7 percent measured, and
one config rule closes the gap — not a claim of perfect accuracy."*

## SEGMENT 4 — OPTIONAL: live submission (2:10–3:05) — only if trending under 5:30

**This is the one droppable segment**, and it sits after the routing demo deliberately.
Segment 5 (the dashboard) is the sixth feature and is NOT optional. Check the clock before
starting: if you're past ~2:30 here, skip straight to Segment 5.

**ON SCREEN:** Student app (Expo web), the report form.
**SAY:** *"Reporting itself takes about thirty seconds."*
**DO:** In the student app: type *"Water leaking under the sink in Lab 1"*, Category
**Water supply**, Location **Lab 1**, tap **Submit report**.
**SAY:** *"Submitted — it lands raw, awaiting triage."*

**DO:** Alt-tab to the terminal and run the full five-step rebuild — **~15 s measured**. Run
all five steps: skipping any leaves every case with a blank department and an empty Patterns
view.
```powershell
.\demo\rescore.ps1
```
**SAY WHILE IT RUNS — these two cover the ~15 s. Don't go silent:**

> **(1) Nothing cached.** *"What's running is a full rebuild — every report re-embedded and
> re-scored from scratch, nothing cached."*

> **(2) Batch by design.** *"And clustering is a batch job on purpose. A report isn't merged the
> instant it lands — it's compared against the case centroids in one deterministic pass, so the
> same inputs always produce the same merge, and we can re-run it later and audit why any two
> reports were grouped together. That's the trade: a few seconds of latency for a decision we
> can defend."*

**DO:** Then run the one-liner:
```powershell
& 'C:\Program Files\PostgreSQL\18\bin\psql.exe' -U postgres -h localhost -d campuspulse -c "SELECT sc.input_name, sc.contribution FROM cases c JOIN scoring_components sc ON sc.scoring_record_id=c.current_scoring_record_id WHERE c.id=(SELECT max(id) FROM cases) ORDER BY sc.contribution DESC;"
```
**ON SCREEN:** Terminal showing the new case's factor breakdown — `age_vs_sla` ≈ 0.
**SAY:** *"Once the pipeline scores it, watch the age factor — the report is minutes old, so
'age against SLA' contributes almost nothing, where the historical backlog is all maxed out.
The score reacts to freshness; a brand-new report doesn't jump the queue on age alone."*

## SEGMENT 5 — Admin pattern dashboard (3:05–3:45 with Seg 4 · 2:10–2:50 without)

**ON SCREEN:** Console → Patterns tab → three cards.
**DO:** Switch to the console, click the **Patterns** tab.
**SAY:** *"For administrators, the pattern view. Recurring faults, ranked by how often they've
happened. Locations, by open case volume. And departments, by median time to acknowledge —
one honest note there: the demo has no real acknowledgement history, so those timings are
synthesised to show the view computes. They're a demonstration, not a measured finding. The
other two views are real pipeline output."*

## CLOSE (3:45–3:55 with Seg 4 · 2:50–3:00 without)

**ON SCREEN:** Back to the queue (or a title card).
**DO:** Click **Queue**.
**SAY:** *"Report, cluster, score, explain, route, track — with the reasoning visible at every
step. That's CampusPulse."*

---

## What I cut (and why)

- **The fact-guard demo** (fabricating "9999 rooms" and watching it get rejected). Its point —
  the explanation can't cite a factor the score didn't use — is folded into one line in
  Segment 2. The full demo is still in `WALKTHROUGH.md` for the live session.
- **The provenance gap** (reports outnumber provenance rows by exactly the app-submitted
  reports). True and worth saying live, but too inside-baseball for a short video; the
  "measured against ground truth" idea is already carried by the 93.7%. Never quote fixed
  counts for this — they move every time someone submits a report.
- **Department scoping** (a Housekeeping login seeing only its own queue). Nice, not essential
  on camera.
- **Login flows** — pre-logged-in during pre-flight.
- **Deep scoring math** — trimmed to the one glance at the breakdown table in Segment 2.

**Flex order.** Segment 4 (live submission, ≈55 s including the 15 s rebuild) is the built-in
flex — drop it first if you're long, add it if you're short. If you're *still* under after
including it, the fact-guard is the next add-back (≈20 s): run
`python intelligence\explain_cases.py` and show the bottom two lines.
