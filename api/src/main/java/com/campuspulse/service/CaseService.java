package com.campuspulse.service;

import com.campuspulse.entity.AppUser;
import com.campuspulse.repository.AppUserRepository;
import com.campuspulse.web.CaseDtos;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import java.time.OffsetDateTime;
import java.util.List;

/**
 * Department console operations. Uses JdbcTemplate: a read-optimized dashboard is natural
 * in SQL, and it avoids adding eight JPA entities under ddl-auto=validate.
 *
 * Role scoping is enforced here, not just in the URL rules:
 *   DEPARTMENT -> only cases assigned to that user's department; reporter identity hidden.
 *   ADMIN      -> all cases.
 */
@Service
public class CaseService {

    private final JdbcTemplate jdbc;
    private final AppUserRepository users;

    public CaseService(JdbcTemplate jdbc, AppUserRepository users) {
        this.jdbc = jdbc;
        this.users = users;
    }

    private AppUser me(String email) {
        return users.findByEmail(email)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.UNAUTHORIZED, "Unknown user"));
    }

    // --- queue ---------------------------------------------------------------

    private static final String QUEUE_SELECT = """
        SELECT c.id, c.title, cat.label AS category, l.name AS location,
               c.priority_score, c.status, dep.name AS department,
               c.occurrence_seq, c.sla_due_at, c.resolved_at, sr.explanation_text
        FROM cases c
        JOIN categories cat ON cat.id = c.category_id
        JOIN locations  l   ON l.id   = c.location_id
        LEFT JOIN departments    dep ON dep.id = c.department_id
        LEFT JOIN scoring_records sr ON sr.id  = c.current_scoring_record_id
        """;

    // "Open" means the same thing here as in the pattern dashboard: not resolved, not closed.
    private static final String OPEN_FILTER     = " WHERE c.status NOT IN ('RESOLVED','CLOSED')";
    private static final String RESOLVED_FILTER = " WHERE c.status IN ('RESOLVED','CLOSED')";
    private static final String OPEN_ORDER      = " ORDER BY c.priority_score DESC NULLS LAST, c.id";
    private static final String RESOLVED_ORDER  = " ORDER BY c.resolved_at DESC NULLS LAST, c.id DESC";

    /**
     * The prioritized queue (open cases only) or the resolved list — same row shape and the
     * same department scoping. Resolved/closed cases drop out of the queue so it shows only
     * work still to do.
     */
    public List<CaseDtos.Summary> queue(String email, boolean resolved) {
        AppUser u = me(email);
        String filter = resolved ? RESOLVED_FILTER : OPEN_FILTER;
        String order  = resolved ? RESOLVED_ORDER : OPEN_ORDER;
        if ("ADMIN".equals(u.getRole())) {
            return jdbc.query(QUEUE_SELECT + filter + order, this::mapSummary);
        }
        // DEPARTMENT: only this department's cases — applies to the resolved list too.
        return jdbc.query(QUEUE_SELECT + filter + " AND c.department_id = ?" + order,
                this::mapSummary, u.getDepartmentId());
    }

    private CaseDtos.Summary mapSummary(java.sql.ResultSet rs, int i) throws java.sql.SQLException {
        return new CaseDtos.Summary(
                rs.getLong("id"), rs.getString("title"), rs.getString("category"),
                rs.getString("location"), dbl(rs, "priority_score"),
                rs.getString("status"), rs.getString("department"),
                rs.getInt("occurrence_seq"),
                rs.getObject("sla_due_at", OffsetDateTime.class),
                rs.getObject("resolved_at", OffsetDateTime.class),
                rs.getString("explanation_text"));
    }

    // --- detail --------------------------------------------------------------

    public CaseDtos.Detail detail(long caseId, String email) {
        AppUser u = me(email);
        assertVisible(caseId, u);

        CaseDtos.Detail head = jdbc.query("""
                SELECT c.id, c.title, cat.label AS category, l.name AS location,
                       dep.name AS department, c.status, c.priority_score, c.occurrence_seq,
                       c.reporter_count, c.opened_at, c.sla_due_at, sr.explanation_text
                FROM cases c
                JOIN categories cat ON cat.id = c.category_id
                JOIN locations  l   ON l.id   = c.location_id
                LEFT JOIN departments    dep ON dep.id = c.department_id
                LEFT JOIN scoring_records sr ON sr.id  = c.current_scoring_record_id
                WHERE c.id = ?
                """, rs -> {
            if (!rs.next()) {
                throw new ResponseStatusException(HttpStatus.NOT_FOUND, "No such case");
            }
            return new CaseDtos.Detail(
                    rs.getLong("id"), rs.getString("title"), rs.getString("category"),
                    rs.getString("location"), rs.getString("department"), rs.getString("status"),
                    dbl(rs, "priority_score"), rs.getInt("occurrence_seq"),
                    rs.getInt("reporter_count"),
                    rs.getObject("opened_at", OffsetDateTime.class),
                    rs.getObject("sla_due_at", OffsetDateTime.class),
                    rs.getString("explanation_text"), List.of(), List.of());
        }, caseId);

        List<CaseDtos.Component> components = jdbc.query("""
                SELECT sc.input_name, sc.contribution, sc.normalized_value, sc.weight,
                       sc.raw_value::text AS raw_value
                FROM scoring_components sc
                JOIN cases c ON c.current_scoring_record_id = sc.scoring_record_id
                WHERE c.id = ?
                ORDER BY sc.contribution DESC
                """, (rs, i) -> new CaseDtos.Component(
                rs.getString("input_name"), dbl(rs, "contribution"),
                dbl(rs, "normalized_value"), dbl(rs, "weight"),
                rs.getString("raw_value")), caseId);

        // Reports on the case — text only, NEVER the reporter.
        List<CaseDtos.ReportView> reports = jdbc.query("""
                SELECT id, raw_text, created_at FROM reports
                WHERE case_id = ? ORDER BY created_at
                """, (rs, i) -> new CaseDtos.ReportView(
                rs.getLong("id"), rs.getString("raw_text"),
                rs.getObject("created_at", OffsetDateTime.class)), caseId);

        return new CaseDtos.Detail(
                head.id(), head.title(), head.category(), head.location(), head.department(),
                head.status(), head.priorityScore(), head.occurrenceSeq(), head.reporterCount(),
                head.openedAt(), head.slaDueAt(), head.explanation(), components, reports);
    }

    // --- commands ------------------------------------------------------------

    @Transactional
    public CaseDtos.Detail overrideDepartment(long caseId, Long newDeptId, String email) {
        AppUser u = me(email);
        assertVisible(caseId, u);
        Long oldDept = jdbc.queryForObject("SELECT department_id FROM cases WHERE id = ?",
                Long.class, caseId);
        Integer sla = jdbc.queryForObject("SELECT sla_hours FROM departments WHERE id = ?",
                Integer.class, newDeptId);
        if (sla == null) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "No such department");
        }
        OffsetDateTime opened = jdbc.queryForObject(
                "SELECT opened_at FROM cases WHERE id = ?", OffsetDateTime.class, caseId);
        jdbc.update("UPDATE cases SET department_id = ?, sla_due_at = ? WHERE id = ?",
                newDeptId, opened.plusHours(sla), caseId);
        jdbc.update("""
                INSERT INTO audit_log (actor_id, action, entity_type, entity_id,
                                       before_json, after_json, reason)
                VALUES (?, 'ROUTE_OVERRIDE', 'case', ?, ?::jsonb, ?::jsonb, ?)
                """, u.getId(), caseId,
                "{\"department_id\":" + oldDept + "}",
                "{\"department_id\":" + newDeptId + "}",
                "manual override by " + u.getEmail());
        return detail(caseId, email);
    }

    private static final List<String> STATUSES = List.of(
            "NEW", "TRIAGED", "ASSIGNED", "IN_PROGRESS", "RESOLVED", "CLOSED", "REOPENED");

    @Transactional
    public CaseDtos.Detail updateStatus(long caseId, String status, String note, String email) {
        AppUser u = me(email);
        assertVisible(caseId, u);
        if (!STATUSES.contains(status)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid status");
        }
        String old = jdbc.queryForObject("SELECT status FROM cases WHERE id = ?", String.class, caseId);
        boolean resolved = "RESOLVED".equals(status) || "CLOSED".equals(status);
        jdbc.update("UPDATE cases SET status = ?, resolved_at = "
                + (resolved ? "COALESCE(resolved_at, now())" : "resolved_at") + " WHERE id = ?",
                status, caseId);
        jdbc.update("""
                INSERT INTO case_status_events (case_id, from_status, to_status, changed_by, note)
                VALUES (?, ?, ?, ?, ?)
                """, caseId, old, status, u.getId(), note);

        // Track stage: notify every reporter on the case (in-app; identity used only to
        // address the row, never exposed to the department).
        String payload = "{\"from\":\"" + old + "\",\"to\":\"" + status + "\"}";
        jdbc.update("""
                INSERT INTO notifications (recipient_id, case_id, type, payload)
                SELECT DISTINCT r.reporter_id, ?, 'STATUS_CHANGE', ?::jsonb
                FROM reports r WHERE r.case_id = ?
                """, caseId, payload, caseId);
        jdbc.update("""
                INSERT INTO audit_log (actor_id, action, entity_type, entity_id, after_json, reason)
                VALUES (?, 'STATUS_CHANGE', 'case', ?, ?::jsonb, ?)
                """, u.getId(), caseId,
                "{\"from\":\"" + old + "\",\"to\":\"" + status + "\"}",
                "status " + old + " -> " + status);
        return detail(caseId, email);
    }

    /** Departments for the override dropdown. */
    public List<CaseDtos.Dept> departments() {
        return jdbc.query("SELECT id, name FROM departments WHERE active ORDER BY name",
                (rs, i) -> new CaseDtos.Dept(rs.getLong("id"), rs.getString("name")));
    }

    /** Categories for the student app's category picker. */
    public List<CaseDtos.Category> categories() {
        return jdbc.query("SELECT id, key, label FROM categories WHERE active ORDER BY label",
                (rs, i) -> new CaseDtos.Category(rs.getLong("id"), rs.getString("key"), rs.getString("label")));
    }

    /** Locations for the student app's location picker. */
    public List<CaseDtos.LocationRef> locations() {
        return jdbc.query("SELECT id, name, type FROM locations ORDER BY name",
                (rs, i) -> new CaseDtos.LocationRef(rs.getLong("id"), rs.getString("name"), rs.getString("type")));
    }

    /** Current user's identity + role, for the console's admin gating. */
    public CaseDtos.Me meView(String email) {
        AppUser u = me(email);
        String dept = u.getDepartmentId() == null ? null
                : jdbc.queryForObject("SELECT name FROM departments WHERE id = ?",
                        String.class, u.getDepartmentId());
        return new CaseDtos.Me(u.getEmail(), u.getRole(), dept);
    }

    // --- admin pattern dashboard: three read-only aggregate views ------------

    public CaseDtos.Patterns patterns() {
        // 1) Recurring faults ranked by how many times they've occurred.
        List<CaseDtos.FaultStat> faults = jdbc.query("""
                SELECT l.name AS location, cat.label AS category, f.occurrence_count
                FROM faults f
                JOIN locations  l   ON l.id   = f.location_id
                JOIN categories cat ON cat.id = f.category_id
                WHERE f.occurrence_count > 1
                ORDER BY f.occurrence_count DESC, l.name
                LIMIT 15
                """, (rs, i) -> new CaseDtos.FaultStat(
                rs.getString("location"), rs.getString("category"), rs.getInt("occurrence_count")));

        // 2) Departments ranked by median time to ACKNOWLEDGE (first move off NEW).
        List<CaseDtos.DeptAckStat> ack = jdbc.query("""
                SELECT d.name AS department,
                       round((percentile_cont(0.5) WITHIN GROUP (
                           ORDER BY EXTRACT(EPOCH FROM (e.created_at - c.opened_at)) / 3600.0))::numeric, 1)
                         AS median_hours,
                       count(*) AS acknowledged,
                       (SELECT count(*) FROM cases c2 WHERE c2.department_id = d.id) AS total
                FROM cases c
                JOIN departments d ON d.id = c.department_id
                JOIN case_status_events e ON e.case_id = c.id AND e.from_status = 'NEW'
                GROUP BY d.name, d.id
                ORDER BY median_hours
                """, (rs, i) -> new CaseDtos.DeptAckStat(
                rs.getString("department"), dbl(rs, "median_hours"),
                rs.getInt("acknowledged"), rs.getInt("total")));

        // 3) Locations ranked by OPEN case volume (not resolved/closed).
        List<CaseDtos.LocationVolumeStat> loc = jdbc.query("""
                SELECT l.name AS location, l.type,
                       count(*) FILTER (WHERE c.status NOT IN ('RESOLVED','CLOSED')) AS open_cases
                FROM cases c
                JOIN locations l ON l.id = c.location_id
                GROUP BY l.name, l.type
                HAVING count(*) FILTER (WHERE c.status NOT IN ('RESOLVED','CLOSED')) > 0
                ORDER BY open_cases DESC, l.name
                LIMIT 15
                """, (rs, i) -> new CaseDtos.LocationVolumeStat(
                rs.getString("location"), rs.getString("type"), rs.getInt("open_cases")));

        return new CaseDtos.Patterns(faults, ack, loc);
    }

    // --- scoping -------------------------------------------------------------

    /** NUMERIC columns arrive as BigDecimal from the driver; normalize to Double/null. */
    private static Double dbl(java.sql.ResultSet rs, String col) throws java.sql.SQLException {
        java.math.BigDecimal v = rs.getBigDecimal(col);
        return v == null ? null : v.doubleValue();
    }

    private void assertVisible(long caseId, AppUser u) {
        if ("ADMIN".equals(u.getRole())) {
            return;
        }
        Long dept = jdbc.query("SELECT department_id FROM cases WHERE id = ?",
                rs -> rs.next() ? (Long) rs.getObject("department_id") : null, caseId);
        if (dept == null || !dept.equals(u.getDepartmentId())) {
            // 404 rather than 403 so a department can't probe case ids outside its queue.
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "No such case");
        }
    }
}
