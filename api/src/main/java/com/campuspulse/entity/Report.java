package com.campuspulse.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.time.OffsetDateTime;

/**
 * A raw student report. FK columns are mapped as scalar Longs on purpose: this is a
 * thin write/read surface, so we avoid dragging in Category/Location/User entity graphs.
 * The `embedding` column is intentionally NOT mapped here — it is owned and written by
 * the Python intelligence service; the API treats it as opaque. Hibernate's schema
 * validation ignores unmapped columns, so leaving it out is safe.
 */
@Entity
@Table(name = "reports")
public class Report {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "reporter_id", nullable = false)
    private Long reporterId;

    @Column(name = "raw_text", nullable = false)
    private String rawText;

    @Column(name = "category_id", nullable = false)
    private Long categoryId;

    @Column(name = "location_id", nullable = false)
    private Long locationId;

    @Column(name = "sublocation")
    private String sublocation;

    @Column(name = "photo_url")
    private String photoUrl;

    @Column(name = "source", nullable = false)
    private String source;

    /** Null until clustering assigns this report to a case. Reports land raw. */
    @Column(name = "case_id")
    private Long caseId;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public Long getReporterId() { return reporterId; }
    public void setReporterId(Long reporterId) { this.reporterId = reporterId; }

    public String getRawText() { return rawText; }
    public void setRawText(String rawText) { this.rawText = rawText; }

    public Long getCategoryId() { return categoryId; }
    public void setCategoryId(Long categoryId) { this.categoryId = categoryId; }

    public Long getLocationId() { return locationId; }
    public void setLocationId(Long locationId) { this.locationId = locationId; }

    public String getSublocation() { return sublocation; }
    public void setSublocation(String sublocation) { this.sublocation = sublocation; }

    public String getPhotoUrl() { return photoUrl; }
    public void setPhotoUrl(String photoUrl) { this.photoUrl = photoUrl; }

    public String getSource() { return source; }
    public void setSource(String source) { this.source = source; }

    public Long getCaseId() { return caseId; }
    public void setCaseId(Long caseId) { this.caseId = caseId; }

    public OffsetDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(OffsetDateTime createdAt) { this.createdAt = createdAt; }
}
