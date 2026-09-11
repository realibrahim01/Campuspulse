package com.campuspulse.web;

import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.Map;

/**
 * Turns an FK violation (e.g. a category_id or location_id that doesn't exist) into a
 * clean 400 rather than a 500. The DB is still the enforcer — we just report it honestly.
 */
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(DataIntegrityViolationException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public Map<String, String> onIntegrity(DataIntegrityViolationException e) {
        return Map.of("error", "Invalid reference: category_id or location_id does not exist");
    }
}
