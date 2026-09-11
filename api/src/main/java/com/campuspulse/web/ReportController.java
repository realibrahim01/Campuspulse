package com.campuspulse.web;

import com.campuspulse.entity.AppUser;
import com.campuspulse.entity.Report;
import com.campuspulse.repository.AppUserRepository;
import com.campuspulse.repository.ReportRepository;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;

/**
 * Thin reporting surface. POST creates a RAW report (no clustering, no scoring, no case
 * assignment) — exactly what the seed loader leaves behind. GET returns the feed.
 */
@RestController
@RequestMapping("/reports")
public class ReportController {

    private final ReportRepository reports;
    private final AppUserRepository users;

    public ReportController(ReportRepository reports, AppUserRepository users) {
        this.reports = reports;
        this.users = users;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ReportResponse submit(@Valid @RequestBody CreateReportRequest req, Authentication auth) {
        // Reporter is the authenticated user, never the client's choice.
        AppUser me = users.findByEmail(auth.getName())
                .orElseThrow(() -> new IllegalStateException("Authenticated user not found"));

        Report r = new Report();
        r.setReporterId(me.getId());
        r.setRawText(req.text());
        r.setCategoryId(req.categoryId());
        r.setLocationId(req.locationId());
        r.setSublocation(req.sublocation());
        r.setPhotoUrl(req.photoUrl());
        r.setSource("app");
        r.setCaseId(null);                                   // raw: clustering happens later
        r.setCreatedAt(OffsetDateTime.now(ZoneOffset.UTC));  // store UTC

        return ReportResponse.from(reports.save(r));
    }

    /**
     * A STUDENT sees only their own reports (the student app's "my reports" list);
     * DEPARTMENT/ADMIN see the full feed.
     */
    @GetMapping
    public List<ReportResponse> list(Authentication auth) {
        AppUser me = users.findByEmail(auth.getName())
                .orElseThrow(() -> new IllegalStateException("Authenticated user not found"));
        List<Report> rows = "STUDENT".equals(me.getRole())
                ? reports.findByReporterIdOrderByCreatedAtDesc(me.getId())
                : reports.findAllByOrderByCreatedAtDesc();
        return rows.stream().map(ReportResponse::from).toList();
    }
}
