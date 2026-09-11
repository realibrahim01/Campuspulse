package com.campuspulse.web;

import com.campuspulse.entity.Report;

import java.time.OffsetDateTime;

/**
 * Read view of a report. caseId is included precisely so a verifier can SEE that fresh
 * reports land raw (caseId == null, i.e. clustered=0) until the pipeline runs.
 */
public record ReportResponse(
        Long id,
        String text,
        Long categoryId,
        Long locationId,
        String sublocation,
        String photoUrl,
        Long reporterId,
        Long caseId,
        String source,
        OffsetDateTime createdAt
) {
    public static ReportResponse from(Report r) {
        return new ReportResponse(
                r.getId(), r.getRawText(), r.getCategoryId(), r.getLocationId(),
                r.getSublocation(), r.getPhotoUrl(), r.getReporterId(), r.getCaseId(),
                r.getSource(), r.getCreatedAt());
    }
}
