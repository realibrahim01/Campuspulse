package com.campuspulse.web;

import java.time.OffsetDateTime;
import java.util.List;

/**
 * DTOs for the department console. Grouped in one file to keep the surface readable.
 * Reporter identity is deliberately absent from every one of these — department views
 * never carry it (anonymity is an institutional policy decision).
 */
public final class CaseDtos {

    /** One row in the prioritized queue. */
    public record Summary(
            long id,
            String title,
            String category,
            String location,
            Double priorityScore,
            String status,
            String department,
            int occurrenceSeq,
            OffsetDateTime slaDueAt,
            OffsetDateTime resolvedAt,   // null while the case is open
            String explanation           // student-facing sentence (no +pts)
    ) {}

    /** A single scoring factor and its contribution — the "why", as a table row. */
    public record Component(
            String inputName,
            Double contribution,
            Double normalizedValue,
            Double weight,
            String rawValue              // JSON text of the raw inputs used
    ) {}

    /** A report on the case — text only, never who filed it. */
    public record ReportView(
            long id,
            String text,
            OffsetDateTime createdAt
    ) {}

    /** Full case detail for the console's case view. */
    public record Detail(
            long id,
            String title,
            String category,
            String location,
            String department,
            String status,
            Double priorityScore,
            int occurrenceSeq,
            int reporterCount,
            OffsetDateTime openedAt,
            OffsetDateTime slaDueAt,
            String explanation,
            List<Component> components,  // the scoring breakdown (dept view = with contributions)
            List<ReportView> reports
    ) {}

    /** Reference row for the override dropdown. */
    public record Dept(long id, String name) {}

    /** Reference rows for the student app's pickers. */
    public record Category(long id, String key, String label) {}
    public record LocationRef(long id, String name, String type) {}

    public record OverrideRequest(Long departmentId) {}

    public record StatusRequest(String status, String note) {}

    /** Who am I — lets the console show the admin dashboard only to admins. */
    public record Me(String email, String role, String department) {}

    // --- admin pattern dashboard (three read-only views) ---
    public record FaultStat(String location, String category, int occurrenceCount) {}
    public record DeptAckStat(String department, Double medianHours, int acknowledged, int totalCases) {}
    public record LocationVolumeStat(String location, String type, int openCases) {}
    public record Patterns(
            List<FaultStat> recurringFaults,
            List<DeptAckStat> departmentAck,
            List<LocationVolumeStat> locationVolume) {}

    private CaseDtos() {}
}
