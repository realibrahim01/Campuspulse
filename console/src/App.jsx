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

  useEffect(() => {
    if (authed) api.me().then(setMe).catch(() => {});
  }, [authed]);

  if (!authed) {
    return <Login onLogin={() => setAuthed(true)} />;
  }

  const isAdmin = me?.role === 'ADMIN';

  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-left">
          <strong>CampusPulse</strong> <span className="muted">Console</span>
          <nav className="nav">
            <button className={'tab' + (view === 'queue' ? ' active' : '')}
              onClick={() => setView('queue')}>Queue</button>
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
          <Queue version={queueVersion} selectedId={selectedId} onSelect={setSelectedId} />
          <main className="detail-pane">
            {selectedId ? (
              <CaseDetail id={selectedId} onChanged={refreshQueue} />
            ) : (
              <div className="empty">Select a case from the queue.</div>
            )}
          </main>
        </div>
      )}
    </div>
  );
}
