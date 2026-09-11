import React, { useState } from 'react';
import { api, setAuth, clearAuth } from './api.js';

export default function Login({ onLogin }) {
  const [email, setEmail] = useState('house@campus.edu');
  const [password, setPassword] = useState('campus123');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError('');
    setAuth(email, password);
    try {
      await api.cases(); // validate the credentials
      onLogin();
    } catch (err) {
      clearAuth();
      setError(err.message === 'Unauthorized' ? 'Wrong email or password.' : 'Sign-in failed: ' + err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="login" onSubmit={submit}>
        <h1>CampusPulse</h1>
        <p className="muted">Department Console — sign in</p>
        <label>Email
          <input value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
        </label>
        <label>Password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        {error && <div className="error">{error}</div>}
        <button disabled={busy} type="submit">{busy ? 'Signing in…' : 'Sign in'}</button>
        <p className="hint muted">Try house@campus.edu, it@campus.edu, or admin@campus.edu · password campus123</p>
      </form>
    </div>
  );
}
