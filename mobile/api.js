// Minimal API client for the student app. Targets the Spring API. On Expo web the base
// is localhost; for a device build it would be the machine's LAN IP.
const BASE = 'http://localhost:8080';

function b64(s) {
  if (typeof btoa === 'function') return btoa(s); // Expo web / browser
  // tiny fallback so native builds don't crash
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  let out = '';
  for (let i = 0; i < s.length; ) {
    const a = s.charCodeAt(i++), b = s.charCodeAt(i++), c = s.charCodeAt(i++);
    const t = (a << 16) | ((isNaN(b) ? 0 : b) << 8) | (isNaN(c) ? 0 : c);
    out += chars[(t >> 18) & 63] + chars[(t >> 12) & 63]
         + (isNaN(b) ? '=' : chars[(t >> 6) & 63]) + (isNaN(c) ? '=' : chars[t & 63]);
  }
  return out;
}

let auth = null;
let email = null;

export function setCreds(e, p) { email = e; auth = 'Basic ' + b64(e + ':' + p); }
export function getEmail() { return email; }

async function req(path, opts = {}) {
  const res = await fetch(BASE + path, {
    ...opts,
    headers: { 'Content-Type': 'application/json', Authorization: auth, ...(opts.headers || {}) },
  });
  if (res.status === 401) throw new Error('Unauthorized');
  if (!res.ok) throw new Error('HTTP ' + res.status);
  const t = await res.text();
  return t ? JSON.parse(t) : null;
}

export const api = {
  categories: () => req('/categories'),
  locations: () => req('/locations'),
  myReports: () => req('/reports'),
  submit: (body) => req('/reports', { method: 'POST', body: JSON.stringify(body) }),
};
