package com.campuspulse.web;

import com.campuspulse.service.CaseService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Admin-only pattern dashboard. Access is restricted to ADMIN in SecurityConfig. */
@RestController
@RequestMapping("/admin")
public class AdminController {

    private final CaseService cases;

    public AdminController(CaseService cases) {
        this.cases = cases;
    }

    @GetMapping("/patterns")
    public CaseDtos.Patterns patterns() {
        return cases.patterns();
    }
}
