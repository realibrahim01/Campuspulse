package com.campuspulse.repository;

import com.campuspulse.entity.Report;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface ReportRepository extends JpaRepository<Report, Long> {

    /** Newest first — the natural order for a reports feed. */
    List<Report> findAllByOrderByCreatedAtDesc();

    /** A single student's own reports, newest first. */
    List<Report> findByReporterIdOrderByCreatedAtDesc(Long reporterId);
}
