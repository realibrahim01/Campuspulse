package com.campuspulse.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

import java.util.List;

/**
 * Stateless HTTP Basic for the REST API. Decisions worth defending:
 *  - CSRF disabled: there is no browser session/cookie to protect; every request
 *    carries its own credentials. CSRF guards cookie-based sessions, which we don't use.
 *  - Stateless: no server session is created; each call authenticates fresh. Keeps the
 *    API horizontally trivial and matches how the mobile/console clients will call it.
 *  - Only STUDENTs may POST a report; any authenticated role may GET the feed. This is
 *    the role-based access the brief asks for, kept minimal for the walking skeleton.
 */
@Configuration
public class SecurityConfig {

    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .csrf(AbstractHttpConfigurer::disable)
            .cors(org.springframework.security.config.Customizer.withDefaults())
            .sessionManagement(sm -> sm.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.POST, "/reports").hasRole("STUDENT")
                .requestMatchers(HttpMethod.GET, "/reports").authenticated()
                // Admin pattern dashboard: admins only.
                .requestMatchers("/admin/**").hasRole("ADMIN")
                // Department console: only department staff and admins.
                .requestMatchers("/cases/**").hasAnyRole("DEPARTMENT", "ADMIN")
                .anyRequest().authenticated())
            .httpBasic(org.springframework.security.config.Customizer.withDefaults());
        return http.build();
    }

    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    /**
     * CORS for the React console dev servers (Vite 5173, CRA 3000). Basic-auth headers are
     * allowed; this is a dev-time convenience, tightened per deployment.
     */
    @Bean
    public CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cfg = new CorsConfiguration();
        // Any localhost port (console on 5173, Expo web on 8081/19006). Dev-only; tighten
        // to explicit origins per deployment. Patterns are required alongside credentials.
        cfg.setAllowedOriginPatterns(List.of("http://localhost:*"));
        cfg.setAllowedMethods(List.of("GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"));
        cfg.setAllowedHeaders(List.of("*"));
        cfg.setAllowCredentials(true);
        UrlBasedCorsConfigurationSource src = new UrlBasedCorsConfigurationSource();
        src.registerCorsConfiguration("/**", cfg);
        return src;
    }
}
