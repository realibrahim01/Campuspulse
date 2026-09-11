package com.campuspulse.web;

import com.campuspulse.service.CaseService;
import jakarta.validation.Valid;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * Department console API. Access is DEPARTMENT or ADMIN (enforced in SecurityConfig);
 * per-department scoping and reporter-identity hiding are enforced in CaseService.
 */
@RestController
@RequestMapping("/cases")
public class CaseController {

    private final CaseService cases;

    public CaseController(CaseService cases) {
        this.cases = cases;
    }

    /** Prioritized queue (this department's cases, or all for admin). */
    @GetMapping
    public List<CaseDtos.Summary> queue(Authentication auth) {
        return cases.queue(auth.getName());
    }

    /** Full case detail: scoring breakdown + explanation + reports (no reporter identity). */
    @GetMapping("/{id}")
    public CaseDtos.Detail detail(@PathVariable long id, Authentication auth) {
        return cases.detail(id, auth.getName());
    }

    /** Manual routing override -> logged as ROUTE_OVERRIDE. */
    @PatchMapping("/{id}/department")
    public CaseDtos.Detail override(@PathVariable long id,
                                    @Valid @RequestBody CaseDtos.OverrideRequest req,
                                    Authentication auth) {
        return cases.overrideDepartment(id, req.departmentId(), auth.getName());
    }

    /** Status change -> status event + reporter notifications (Track) + STATUS_CHANGE audit. */
    @PatchMapping("/{id}/status")
    public CaseDtos.Detail status(@PathVariable long id,
                                  @Valid @RequestBody CaseDtos.StatusRequest req,
                                  Authentication auth) {
        return cases.updateStatus(id, req.status(), req.note(), auth.getName());
    }
}
