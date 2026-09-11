-- CampusPulse — V1 baseline schema (relational only; no vector dependency).
--
-- Design notes for the team (we must defend every decision to judges):
--
--  * IDs are BIGINT GENERATED ALWAYS AS IDENTITY, not UUIDs. During a live demo
--    it is far nicer to say "look at case 42" than to read a UUID aloud. Sequential
--    IDs also make the audit timeline human-readable. No external-exposure concern
--    at hackathon scope.
--
--  * Enumerations use TEXT + CHECK constraints, not native Postgres ENUM types.
--    Reason: a CHECK is trivial to read and to widen ("add a status") without the
--    ceremony ENUM types require, and the allowed set is visible right here in the
--    schema for a judge reading the DDL. Per-campus tuning stays a data concern.
--
--  * Every timestamp is TIMESTAMPTZ. "Age against SLA" is a scoring input measured
--    in real hours; storing naive timestamps would make that arithmetic wrong the
--    moment anyone changes timezone. Store UTC, compute deltas honestly.
--
--  * Ground-truth labels are NOT columns on `reports` — they live in their own
--    table (report_ground_truth) so the running pipeline physically cannot read the
--    answer key it is being measured against. See that table's comment.
--
--  * Vector columns are deliberately absent here and added in V2, so pgvector
--    availability cannot block the core schema. See V2.

-- ---------------------------------------------------------------------------
-- Reference / configuration tables (seeded per campus, tunable)
-- ---------------------------------------------------------------------------

CREATE TABLE departments (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        TEXT    NOT NULL UNIQUE,
    -- Target response time. This is a DEPARTMENT property, not a global constant,
    -- because "age against department SLA" is a scoring input: re-scoring after an
    -- SLA change is just re-reading this column.
    sla_hours   INTEGER NOT NULL CHECK (sla_hours > 0),
    active      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- FUTURE: multi-campus is out of scope for the build, but our limitations slide says
-- routing is "configurable per institution". When that day comes, add campus_id here
-- and change `name UNIQUE` -> `UNIQUE (campus_id, name)`. That is a plain migration,
-- not a rewrite, precisely because nothing below assumes a single global namespace.
CREATE TABLE locations (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name               TEXT NOT NULL UNIQUE,
    -- Location type feeds "location criticality" and gives clustering a categorical
    -- signal. Widen this set per campus as needed.
    type               TEXT NOT NULL CHECK (type IN
                         ('HOSTEL','LAB','CORRIDOR','GROUNDS','CLASSROOM','WASHROOM',
                          'LIBRARY','CANTEEN','OFFICE','OTHER')),
    -- Load-bearing for scoring: "people affected" reads population, and
    -- "location criticality" reads criticality_weight. Two scoring inputs, one table.
    population         INTEGER NOT NULL DEFAULT 0 CHECK (population >= 0),
    criticality_weight NUMERIC(6,3) NOT NULL DEFAULT 1.0 CHECK (criticality_weight >= 0),
    parent_id          BIGINT REFERENCES locations(id),  -- block -> floor hierarchy
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE categories (
    id                    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    key                   TEXT NOT NULL UNIQUE,          -- stable machine key
    label                 TEXT NOT NULL,                 -- human label
    -- "Severity is category-derived with a health/safety flag" maps directly here.
    -- Weights are DATA, not code constants, so "tunable per campus" is an UPDATE,
    -- not a redeploy — and we can show a judge the tuning happen live.
    severity_weight       NUMERIC(6,3) NOT NULL CHECK (severity_weight >= 0),
    safety_flag           BOOLEAN NOT NULL DEFAULT FALSE,
    default_department_id BIGINT REFERENCES departments(id),
    active                BOOLEAN NOT NULL DEFAULT TRUE
);

-- ---------------------------------------------------------------------------
-- Identity / auth
-- ---------------------------------------------------------------------------

CREATE TABLE users (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('STUDENT','DEPARTMENT','ADMIN')),
    -- Department users are scoped to exactly one department. That scoping is what
    -- hides other departments' queues AND (per our stated limitation) hides reporter
    -- identity: department-facing queries simply never select reporter columns.
    department_id BIGINT REFERENCES departments(id),
    display_name  TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- A DEPARTMENT user must belong to a department; others need not.
    CONSTRAINT dept_user_has_department
        CHECK (role <> 'DEPARTMENT' OR department_id IS NOT NULL)
);

-- ---------------------------------------------------------------------------
-- Fault lineage (recurrence identity) and cases (occurrences)
-- ---------------------------------------------------------------------------

-- A fault is the RECURRING identity behind episodes: "Water cooler #2, Lab Wing 2F".
-- It is a real runtime table, not just an eval label, because recurrence detection
-- is a DECISION ("this new case is the 3rd failure of fault F") that must be
-- auditable. The seed label `fault_key` exists only to MEASURE this linkage.
CREATE TABLE faults (
    id                   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    representative_label TEXT,
    location_id          BIGINT NOT NULL REFERENCES locations(id),
    category_id          BIGINT NOT NULL REFERENCES categories(id),
    first_seen_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Denormalized so recurrence scoring is a single column read, not a COUNT.
    occurrence_count     INTEGER NOT NULL DEFAULT 0,
    status               TEXT NOT NULL DEFAULT 'ACTIVE'
                             CHECK (status IN ('ACTIVE','RETIRED')),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- A case IS an occurrence: one episode of a fault, from first report to resolution.
-- We deliberately do NOT keep a separate `occurrences` table — that would be a
-- redundant level. occurrence_seq (1st, 2nd, 3rd...) is what makes "the third
-- failure scores differently from the first" a one-line lookup.
CREATE TABLE cases (
    id                       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fault_id                 BIGINT NOT NULL REFERENCES faults(id),
    occurrence_seq           INTEGER NOT NULL CHECK (occurrence_seq >= 1),
    location_id              BIGINT NOT NULL REFERENCES locations(id),
    category_id              BIGINT NOT NULL REFERENCES categories(id), -- canonical
    department_id            BIGINT REFERENCES departments(id),          -- null until routed
    status                   TEXT NOT NULL DEFAULT 'NEW' CHECK (status IN
                               ('NEW','TRIAGED','ASSIGNED','IN_PROGRESS',
                                'RESOLVED','CLOSED','REOPENED')),
    priority_score           NUMERIC(8,3),                               -- denormalized latest
    -- FK to scoring_records is added by ALTER at the bottom of this file:
    -- cases <-> scoring_records reference each other, so one side must come second.
    current_scoring_record_id BIGINT,
    title                    TEXT,
    reporter_count           INTEGER NOT NULL DEFAULT 0,
    opened_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    sla_due_at               TIMESTAMPTZ,
    resolved_at              TIMESTAMPTZ,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (fault_id, occurrence_seq)
);

-- ---------------------------------------------------------------------------
-- Reports (raw submissions) and their eval labels
-- ---------------------------------------------------------------------------

CREATE TABLE reports (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- NOT NULL: login is required to report. Identity is stored but hidden from
    -- department views at the query layer, never at the storage layer.
    reporter_id BIGINT NOT NULL REFERENCES users(id),
    raw_text    TEXT NOT NULL,
    category_id BIGINT NOT NULL REFERENCES categories(id),  -- student-picked; case holds canonical
    location_id BIGINT NOT NULL REFERENCES locations(id),   -- picked from seeded registry
    photo_url   TEXT,                                       -- object-storage key, null if none
    source      TEXT NOT NULL DEFAULT 'app',
    -- A report belongs to at most one case; on a merge, reports repoint (and the
    -- repoint is logged in audit_log). This single FK IS the clustering link —
    -- no join table needed.
    case_id     BIGINT REFERENCES cases(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_reports_case ON reports(case_id);

-- Provenance + eval labels for SEED reports. Two jobs in one table, both honest:
--   1) Provenance: marks a report as synthetic and records which generator run made
--      it. This is what lets the idempotent seed loader find and rebuild exactly the
--      seed rows without touching any real report a demo user might have submitted.
--   2) Ground truth: the dedup / recurrence / routing labels we measure against.
-- It lives HERE, not on `reports`, on purpose: the production pipeline never joins
-- this table, so it cannot cheat by reading the answer key. Real (app-submitted)
-- reports simply have no row here.
CREATE TABLE report_provenance (
    report_id        BIGINT PRIMARY KEY REFERENCES reports(id),
    is_synthetic     BOOLEAN NOT NULL DEFAULT TRUE,
    source           TEXT,   -- e.g. 'generate_campus_reports.py'
    seed_batch       TEXT,   -- generator run id, so a rebuild targets one batch
    gt_fault_key     TEXT,   -- dedup ground truth
    gt_occurrence_id TEXT,   -- recurrence ground truth
    gt_department    TEXT     -- routing ground truth
);

-- ---------------------------------------------------------------------------
-- Scoring: weights (versioned) -> records (append-only) -> components (inspectable)
-- ---------------------------------------------------------------------------

-- Versioned weight sets. Every score records WHICH version produced it, so
-- historical re-scoring is reproducible and honest ("this case was scored under
-- weights v1; under v2 it would rank differently").
CREATE TABLE scoring_weights (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    version_label  TEXT NOT NULL,
    active         BOOLEAN NOT NULL DEFAULT FALSE,
    w_severity     NUMERIC(6,3) NOT NULL,
    w_people       NUMERIC(6,3) NOT NULL,
    w_recurrence   NUMERIC(6,3) NOT NULL,
    w_age_sla      NUMERIC(6,3) NOT NULL,
    w_location     NUMERIC(6,3) NOT NULL,
    -- Normalization params (min/max/caps per input) kept as jsonb so tuning the
    -- shape of an input doesn't need a migration.
    norm_params    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Append-only. A re-score writes a NEW row; it never mutates an old one. This is
-- the audit trail for scoring.
CREATE TABLE scoring_records (
    id                          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    case_id                     BIGINT NOT NULL REFERENCES cases(id),
    weights_version_id          BIGINT NOT NULL REFERENCES scoring_weights(id),
    total_score                 NUMERIC(8,3) NOT NULL,
    explanation_text            TEXT,           -- rendered from scoring_components only
    explanation_template_version TEXT,
    computed_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_scoring_records_case ON scoring_records(case_id);

-- The heart of the "explanation cannot cite an unused input" guarantee.
-- The explanation layer iterates THESE rows and nothing else. A row exists only if
-- the factor contributed to total_score, so the explanation literally cannot name a
-- reason the score didn't use. Generic rows (not fixed columns) also mean adding a
-- 6th factor is a data change, not a migration.
CREATE TABLE scoring_components (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scoring_record_id BIGINT NOT NULL REFERENCES scoring_records(id),
    input_name        TEXT NOT NULL,           -- 'severity','people_affected',...
    raw_value         JSONB,                   -- the raw inputs (cluster_size, hours_open, ...)
    normalized_value  NUMERIC(8,4),            -- input after normalization to [0,1]-ish
    weight            NUMERIC(6,3),            -- weight applied (snapshot from scoring_weights)
    contribution      NUMERIC(8,4),            -- weight * normalized_value; sums to total_score
    UNIQUE (scoring_record_id, input_name)
);

-- Now close the cases <-> scoring_records cycle.
ALTER TABLE cases
    ADD CONSTRAINT fk_cases_current_scoring_record
    FOREIGN KEY (current_scoring_record_id) REFERENCES scoring_records(id);

-- ---------------------------------------------------------------------------
-- Routing
-- ---------------------------------------------------------------------------

-- Rules evaluated in rule_order; classification is the fallback; manual override
-- writes cases.department_id and logs who did it in audit_log.
-- FUTURE (per-institution routing): add campus_id here and scope rule evaluation by
-- it. rule_order stays per-campus. No single-campus assumption is baked in today.
CREATE TABLE routing_rules (
    id                   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    rule_order           INTEGER NOT NULL,
    match_category_id    BIGINT REFERENCES categories(id),
    match_location_type  TEXT,
    match_keyword        TEXT,
    target_department_id BIGINT NOT NULL REFERENCES departments(id),
    active               BOOLEAN NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Lifecycle: status events -> notifications, plus the cross-cutting audit spine
-- ---------------------------------------------------------------------------

-- Every status change. This is what fans updates back to every reporter on a case
-- (the Track step) and feeds recurrence detection when a case resolves.
CREATE TABLE case_status_events (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    case_id    BIGINT NOT NULL REFERENCES cases(id),
    from_status TEXT,
    to_status  TEXT NOT NULL,
    changed_by BIGINT REFERENCES users(id),   -- null = system
    note       TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_status_events_case ON case_status_events(case_id);

-- Step 7, the Track stage: in-app status notifications to every reporter on a case.
-- These are IN SCOPE and in the demo. Only mobile PUSH *infrastructure* (APNs/FCM
-- device delivery) is out of scope — the notification rows themselves are the point.
CREATE TABLE notifications (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    recipient_id BIGINT NOT NULL REFERENCES users(id),
    case_id      BIGINT NOT NULL REFERENCES cases(id),
    type         TEXT,
    payload      JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    read_at      TIMESTAMPTZ
);
CREATE INDEX idx_notifications_recipient ON notifications(recipient_id);

-- Append-only spine: one uniform "who did what to this case" trail. scoring_records
-- and case_status_events are the TYPED, heavy records; this is the single
-- chronological narrative a judge can read end-to-end. We accept the overlap
-- deliberately: typed tables give FK integrity and fast queries; the log guarantees
-- no decision is left without a trace.
CREATE TABLE audit_log (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_id    BIGINT REFERENCES users(id),  -- null = system action
    action      TEXT NOT NULL CHECK (action IN
                  ('CLUSTER_MERGE','CLUSTER_ASSIGN','RECURRENCE_LINK','SCORE_COMPUTED',
                   'ROUTE_ASSIGNED','ROUTE_OVERRIDE','STATUS_CHANGE','REPORT_SUBMITTED')),
    entity_type TEXT NOT NULL,
    entity_id   BIGINT,
    before_json JSONB,
    after_json  JSONB,
    reason      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_entity ON audit_log(entity_type, entity_id);
