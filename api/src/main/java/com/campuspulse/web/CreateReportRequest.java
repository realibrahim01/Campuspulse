package com.campuspulse.web;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

/**
 * Submit payload. Deliberately thin: the reporter is NOT in the body — it comes from the
 * authenticated principal, so a student cannot report as someone else. No case, score,
 * or cluster fields exist here; those are pipeline-owned, not client-supplied.
 */
public record CreateReportRequest(
        @NotBlank String text,
        @NotNull Long categoryId,
        @NotNull Long locationId,
        String sublocation,   // optional free-text within the location
        String photoUrl       // optional; object-storage key, wired later
) {
}
