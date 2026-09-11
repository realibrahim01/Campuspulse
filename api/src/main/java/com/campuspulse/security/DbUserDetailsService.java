package com.campuspulse.security;

import com.campuspulse.entity.AppUser;
import com.campuspulse.repository.AppUserRepository;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

/**
 * Authenticates against the seeded `users` table. Email is the username; the DB stores
 * a bcrypt hash (written by the seed loader), which the BCryptPasswordEncoder verifies.
 * The role column becomes a ROLE_* authority so method/URL rules like hasRole('STUDENT')
 * work directly.
 */
@Service
public class DbUserDetailsService implements UserDetailsService {

    private final AppUserRepository users;

    public DbUserDetailsService(AppUserRepository users) {
        this.users = users;
    }

    @Override
    public UserDetails loadUserByUsername(String email) throws UsernameNotFoundException {
        AppUser u = users.findByEmail(email)
                .orElseThrow(() -> new UsernameNotFoundException("No user: " + email));
        return User.withUsername(u.getEmail())
                .password(u.getPasswordHash())
                .authorities(new SimpleGrantedAuthority("ROLE_" + u.getRole()))
                .build();
    }
}
