// Thin API client. Stateless HTTP Basic against the Spring API; the token lives in
// sessionStorage so a page refresh during the demo doesn't log you out.
const BASE = 'http://localhost:8080';

export function setAuth(email, password) {
  sessionStorage.setItem('cp_auth', 'Basic ' + btoa(email + ':' + password));
  sessionStorage.setItem('cp_email', email);
}
export function clearAuth() {
  sessionStorage.removeItem('cp_auth');
  sessionStorage.removeItem('cp_email');
}
export function currentEmail() {
  return sessionStorage.getItem('cp_email');
}
export function isAuthed() {
  return !!sessionStorage.getItem('cp_auth');
}

async function req(path, opts = {}) {
  const auth = sessionStorage.getItem('cp_auth');
  let res;
  try {
    res = await fetch(BASE + path, {
      ...opts,
      headers: { 'Content-Type': 'application/json', Authorization: auth, ...(opts.headers || {}) },
    });
  } catch {
    // Network-level failure (server down, wrong port, CORS) — make it legible, not "Failed to fetch".
    throw new Error(`Can't reach the API at ${BASE}. Is it running?`);
  }
  if (res.status === 401) {
    clearAuth();
    throw new Error('Unauthorized');
  }
  if (!res.ok) throw new Error('HTTP ' + res.status);
  const txt = await res.text();
  return txt ? JSON.parse(txt) : null;
}

export const api = {
  me: () => req('/me'),
  patterns: () => req('/admin/patterns'),
  // resolved=false -> open queue; resolved=true -> RESOLVED/CLOSED list (same endpoint).
  cases: (resolved = false) => req('/cases' + (resolved ? '?resolved=true' : '')),
  case: (id) => req('/cases/' + id),
  departments: () => req('/departments'),
  setStatus: (id, status, note) =>
    req('/cases/' + id + '/status', { method: 'PATCH', body: JSON.stringify({ status, note }) }),
  override: (id, departmentId) =>
    req('/cases/' + id + '/department', { method: 'PATCH', body: JSON.stringify({ departmentId }) }),
};

export const STATUSES = ['NEW', 'TRIAGED', 'ASSIGNED', 'IN_PROGRESS', 'RESOLVED', 'CLOSED', 'REOPENED'];
