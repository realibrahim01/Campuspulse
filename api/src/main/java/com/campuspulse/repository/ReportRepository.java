package com.campuspulse.repository;

import com.campuspulse.entity.Report;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface ReportRepository extends JpaRepository<Report, Long> {

    /** A caller's own reports, newest first — the only reports feed exposed by the API. */
    List<Report> findByReporterIdOrderByCreatedAtDesc(Long reporterId);
}
