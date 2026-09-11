# CampusPulse

Campus Problem Intelligence — students report campus problems; the platform clusters
near-duplicate reports into cases, scores each case with a transparent weighted
function, explains the score from its own inputs, routes it to a department, and tracks
resolution back to every reporter.

Built for Campusathon 2026 (PS5). Everything here is written fresh during the
8–11 Sep 2026 build window.

## Architecture (at a glance)

| Layer | Stack | Owns |
|---|---|---|
| Student app | React Native (Expo) + TypeScript | 30-second reporting |
| Dept console / admin | React | Case queues, scoring inspection, dashboard |
| API | Java 17 + Spring Boot 3.3 | Case lifecycle, auth (student/department/admin) |
| Intelligence service | Python + FastAPI | Embeddings, clustering, scoring, recurrence — and the FAISS similarity index |
| Data | PostgreSQL 18 | Case graph, audit log; embeddings as `REAL[]` |

**Why the similarity index is in the Python service, not Postgres:** pgvector is not
available on a standard native Windows Postgres install, and we agreed to a single
install attempt rather than building it from source mid-sprint. Embeddings are stored
in Postgres as `REAL[]`; the intelligence service loads them and runs the index (FAISS)
in memory. The intelligence service already owns embedding generation, so owning its
index is coherent — not a workaround. On a machine with pgvector, swapping back is a
two-line migration change (see `V2__vectors.sql`).

## Environment (reproduce this exactly — we do not use Docker)

Verified toolchain on the build machine (9 Sep 2026):

| Tool | Version | Notes |
|---|---|---|
| PostgreSQL | 18.6 (x64, Windows) | Service `postgresql-x64-18` |
| Java (Temurin) | 17.0.18 | Spring Boot 3.3.5 targets 17 |
| Maven | 3.9.15 | On PATH; no Gradle used |
| Node | pin LTS (20/22) via nvm | Only for the Expo client; set up on client day |

### 1. Install PostgreSQL (once, per machine)

```powershell
winget install -e --id PostgreSQL.PostgreSQL.17   # winget currently resolves to 18.x
```

The installer asks for a **superuser (`postgres`) password**. Choose one and remember
it — you will export it below. This is a local dev DB; the password never leaves your
machine and is never committed.

### 2. Create the database

```powershell
$env:PGPASSWORD='<your-postgres-password>'
& 'C:\Program Files\PostgreSQL\18\bin\psql.exe' -U postgres -h localhost -d postgres -c "CREATE DATABASE campuspulse;"
```

### 3. Put your password in a local `.env` (never committed)

Nothing sensitive lives in the repo. The app, the Flyway plugin, and the demo scripts all
read `CAMPUSPULSE_DB_PASSWORD` from the environment; the demo scripts load it from a
**gitignored `.env` at the project root** when it isn't already set. Create it once:

```
# CampusPulse/.env   (this file is in .gitignore — do not commit it)
CAMPUSPULSE_DB_PASSWORD=your-postgres-password
```

The scripts also mirror it to `PGPASSWORD` so `psql` never prompts. If you prefer, set the
env var by hand instead (`$env:CAMPUSPULSE_DB_PASSWORD='...'`) — either works.

### 4. Apply the schema

```powershell
mvn -f api/pom.xml flyway:migrate      # applies V1 (baseline) + V2 (vectors)
```

Verify:

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\psql.exe' -U postgres -h localhost -d campuspulse -c "SELECT version, description, success FROM flyway_schema_history ORDER BY installed_rank;"
```

You should see V1 `baseline` and V2 `vectors`, both `success = t`, and 15 domain tables.

### Rebuilding from scratch

The schema is rebuildable at any time (Flyway owns it; Hibernate is `ddl-auto: validate`
and never alters it). To wipe and rebuild the database:

```powershell
mvn -f api/pom.xml flyway:clean flyway:migrate
```

(The seed **data** is reloaded separately by the idempotent seed loader — see
`seed/` once it lands.)

## Running the API

```powershell
$env:CAMPUSPULSE_DB_PASSWORD='<your-postgres-password>'
mvn -f api/pom.xml -DskipTests package
java -jar api/target/api-0.1.0.jar          # starts on http://localhost:8080
```

The app runs Flyway on boot (so a fresh clone is migrated automatically) and Hibernate
validates every entity against the schema — a mismatch fails startup on purpose.

### Endpoints (Day 1 — reporting only)

Auth is stateless HTTP Basic against seeded users (password `campus123`). Reports land
**raw**: no case, no score, no embedding — `caseId` is null until the pipeline runs.

| Method | Path | Who | Body |
|---|---|---|---|
| `POST` | `/reports` | STUDENT | `{text, categoryId, locationId, sublocation?, photoUrl?}` |
| `GET`  | `/reports` | any authenticated user | — |

Submit a report (reporter comes from the login, never the body):

```bash
curl -s -u student01@campus.edu:campus123 -H "Content-Type: application/json" \
  -d '{"text":"Ceiling fan not working in room 210","categoryId":1,"locationId":2,"sublocation":"Room 210"}' \
  http://localhost:8080/reports
```

List reports (newest first):

```bash
curl -s -u it@campus.edu:campus123 http://localhost:8080/reports
```

Access control is real: an anonymous `GET` returns 401, and a non-student `POST`
returns 403.

## Seed data (synthetic, with ground truth)

The demo runs on a synthetic dataset because recurrence detection needs history — we
state this openly. `seed/generate_campus_reports.py` emits `campus_reports.json`:
a self-contained campus plus ~318 reports across **22 faults / 59 occurrences**, each
report labelled with `fault_key` (dedup), `occurrence_id` (recurrence) and
`department_true` (routing). It deliberately builds in three test structures:
code-mixed English/Hindi phrasings that must merge, near-miss pairs (same words,
different location) that must not, and singletons that must stay unmerged. The RNG is
seeded, so the dataset — and every metric we compute on it — is reproducible.

`seed/load_seed.py` is the idempotent loader: it TRUNCATEs all data tables and rebuilds
from the JSON, so we can rebuild the DB repeatedly before the demo. Ground truth goes
only into `report_provenance`, never onto `reports`. Reports load raw (no clustering,
no embeddings — that is the intelligence service's job).

```powershell
$env:CAMPUSPULSE_DB_PASSWORD='<your-postgres-password>'
& 'C:\Users\ibrah\miniconda3\python.exe' -m pip install -r seed/requirements.txt
python seed/generate_campus_reports.py -o seed/campus_reports.json   # regenerate JSON
python seed/load_seed.py --json seed/campus_reports.json             # (re)load DB
```

All seed users share the demo password `campus123` (e.g. `student01@campus.edu`,
`it@campus.edu`, `admin@campus.edu`) so anyone can log in as any role during the demo.

## Repository layout

```
CampusPulse/
  api/                         # Spring Boot API (Java) — case lifecycle + auth
    pom.xml
    src/main/java/com/campuspulse/
    src/main/resources/
      application.yml
      db/migration/            # Flyway migrations (single source of truth for schema)
        V1__baseline.sql
        V2__vectors.sql
  intelligence/                # FastAPI service (Python) — embeddings, clustering, scoring  [later]
  seed/
    generate_campus_reports.py # synthetic dataset generator (ground-truth labelled)
    load_seed.py               # idempotent loader (TRUNCATE + rebuild from JSON)
    campus_reports.json        # generated dataset (~318 reports, 22 faults, 59 occ)
    requirements.txt
  README.md
```

## Data model — the three levels that matter

The ground-truth labels imply three levels; conflating them breaks scoring:

- **report** (`reports`) — one student submission.
- **case** (`cases`) — one *occurrence* of a fault, from first report to resolution.
  A case IS an occurrence; `occurrence_seq` = 1st/2nd/3rd failure.
- **fault** (`faults`) — the recurring identity behind occurrences (e.g. "Water cooler
  #2, Lab Wing 2F"). Recurrence is counted here.

Ground-truth / provenance labels live in `report_provenance` (never on `reports`), so
the running pipeline cannot read the answer key it is measured against.

The scoring guarantee — *an explanation cannot cite an input the score did not use* —
is enforced by schema: the explanation layer renders only from `scoring_components`
rows, and a row exists only if that factor contributed to the total.

## Bring up the whole stack (demo)

With `.env` in place and Postgres running, one command starts the API, the department
console, and the Expo student app, each in its own window:

```powershell
cd CampusPulse
.\demo\stack_up.ps1     # API :8080 · console :5173 · Expo web :8081
.\demo\stack_down.ps1   # stops all three
```

Logins (all password `campus123`): `student01@campus.edu` (student app), `house@campus.edu`
/ `it@campus.edu` (department console), `admin@campus.edu` (console + pattern dashboard).

To rebuild the intelligence outputs from the current reports (clusters, routes, scores,
explanations, and synthetic acknowledgement activity):

```powershell
.\demo\rescore.ps1      # persist_cases -> route_cases -> score_cases -> explain_cases -> seed_activity
```

The full click-by-click demo script is in **`demo/WALKTHROUGH.md`** (with a marked 5-minute
cut). Known limitations are stated openly there and in `docs/` — notably: the demo runs on a
synthetic dataset, and the pattern dashboard's "median time to acknowledge" is computed from
**synthetic** acknowledgement activity (a demonstration that the view computes, not a
measured finding).

## Third-party dependencies & licences

Per Campusathon rule 9 we disclose the significant third-party components below, and per
rule 15 each remains subject to its own licence (all permissive; none modified):

| Component | Used for | Licence |
|---|---|---|
| Spring Boot 3.3 | Java REST API, security | Apache-2.0 |
| Flyway (Community) | DB migrations | Apache-2.0 |
| PostgreSQL 18 | database | PostgreSQL License (BSD-style) |
| Hibernate / JPA | persistence | LGPL-2.1 |
| PostgreSQL JDBC driver | DB connectivity | BSD-2-Clause |
| sentence-transformers | text embeddings | Apache-2.0 |
| **all-MiniLM-L6-v2** (pretrained model) | the embedding model itself | Apache-2.0 |
| PyTorch (`torch`) | embedding runtime | BSD-3-Clause |
| FAISS (`faiss-cpu`) | similarity index | MIT |
| NumPy | vector math | BSD-3-Clause |
| psycopg2 | Python → Postgres | LGPL-3.0-with-exceptions |
| bcrypt (Python) | password hashing in the seed loader | Apache-2.0 |
| React + Vite | department console | MIT |
| Expo / React Native | student app | MIT |
| @react-native-picker/picker | form pickers | MIT |

Pretrained embeddings only — **no model training or fine-tuning**. The model weights are
downloaded from Hugging Face at first run and cached outside the repo.
