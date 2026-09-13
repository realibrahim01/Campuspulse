import React, { useState, useEffect, useCallback } from 'react';
import { api, isAuthed, currentEmail, clearAuth } from './api.js';
import Login from './Login.jsx';
import Queue from './Queue.jsx';
import CaseDetail from './CaseDetail.jsx';
import Patterns from './Patterns.jsx';

export default function App() {
  const [authed, setAuthed] = useState(isAuthed());
  const [me, setMe] = useState(null);
  const [view, setView] = useState('queue');       // 'queue' | 'patterns'
  const [selectedId, setSelectedId] = useState(null);
  const [queueVersion, setQueueVersion] = useState(0);

  const refreshQueue = useCallback(() => setQueueVersion((v) => v + 1), []);

  // Fetch identity (drives the admin-only Patterns tab). Retry on failure: under stack_up
  // the console can load before the API has finished starting, and a silently-swallowed
  // /me failure would leave an admin without the Patterns tab and no clue why.
  useEffect(() => {
    if (!authed) return;
    let cancelled = false;
    let attempts = 0;
    const tryMe = () => {
      api.me()
        .then((m) => { if (!cancelled) setMe(m); })
        .catch(() => { if (!cancelled && attempts++ < 6) setTimeout(tryMe, 1500); });
    };
    tryMe();
    return () => { cancelled = true; };
  }, [authed]);

  if (!authed) {
    return <Login onLogin={() => setAuthed(true)} />;
  }

  const isAdmin = me?.role === 'ADMIN';

  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-left">
          <span className="brand"><strong>CampusPulse</strong> <span className="brand-sub">Console</span></span>
          <nav className="nav">
            <button className={'tab' + (view === 'queue' ? ' active' : '')}
              onClick={() => setView('queue')}>Queue</button>
            <button className={'tab' + (view === 'resolved' ? ' active' : '')}
              onClick={() => setView('resolved')}>Resolved</button>
            {isAdmin && (
              <button className={'tab' + (view === 'patterns' ? ' active' : '')}
                onClick={() => setView('patterns')}>Patterns</button>
            )}
          </nav>
        </div>
        <div className="muted">
          {currentEmail()}{me ? ` · ${me.role}` : ''}{' '}
          <button className="link" onClick={() => { clearAuth(); setAuthed(false); setMe(null); }}>
            sign out
          </button>
        </div>
      </header>

      {view === 'patterns' && isAdmin ? (
        <Patterns />
      ) : (
        <div className="layout">
          <Queue
            mode={view === 'resolved' ? 'resolved' : 'open'}
            version={queueVersion}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
          <main className="detail-pane">
            {selectedId ? (
              <CaseDetail id={selectedId} onChanged={refreshQueue} />
            ) : (
              <div className="empty">
                Select a case from the {view === 'resolved' ? 'list' : 'queue'}.
              </div>
            )}
          </main>
        </div>
      )}
    </div>
  );
}
