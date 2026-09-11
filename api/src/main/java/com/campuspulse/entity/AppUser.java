package com.campuspulse.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

/**
 * Read-mostly view of a platform user, backing authentication and the "reporter is the
 * authenticated user" rule. Named AppUser to avoid clashing with Spring Security's User.
 */
@Entity
@Table(name = "users")
public class AppUser {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String email;

    @Column(name = "password_hash", nullable = false)
    private String passwordHash;

    /** STUDENT | DEPARTMENT | ADMIN (a DB CHECK constraint enforces the set). */
    @Column(nullable = false)
    private String role;

    @Column(name = "department_id")
    private Long departmentId;

    @Column(name = "display_name")
    private String displayName;

    public Long getId() { return id; }
    public String getEmail() { return email; }
    public String getPasswordHash() { return passwordHash; }
    public String getRole() { return role; }
    public Long getDepartmentId() { return departmentId; }
    public String getDisplayName() { return displayName; }
}
