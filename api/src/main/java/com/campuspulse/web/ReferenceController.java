package com.campuspulse.web;

import com.campuspulse.service.CaseService;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/** Small reference-data endpoints for the console (e.g. the override dropdown). */
@RestController
public class ReferenceController {

    private final CaseService cases;

    public ReferenceController(CaseService cases) {
        this.cases = cases;
    }

    @GetMapping("/departments")
    public List<CaseDtos.Dept> departments() {
        return cases.departments();
    }

    @GetMapping("/categories")
    public List<CaseDtos.Category> categories() {
        return cases.categories();
    }

    @GetMapping("/locations")
    public List<CaseDtos.LocationRef> locations() {
        return cases.locations();
    }

    /** Identity of the caller — the console uses the role to show/hide the admin dashboard. */
    @GetMapping("/me")
    public CaseDtos.Me me(Authentication auth) {
        return cases.meView(auth.getName());
    }
}
