import React, { useEffect, useState } from 'react';
import { api } from './api.js';

export function priorityClass(score) {
  if (score == null) return 'p-none';
  if (score >= 70) return 'p-high';
  if (score >= 40) return 'p-med';
  return 'p-low';
}

function fmtResolved(iso) {
  if (!iso) return 'date unknown';
  return new Date(iso).toLocaleDateString(undefined,
    { day: 'numeric', month: 'short', year: 'numeric' });
}

/**
 * One row, shared by the open queue and the Resolved list — only the meta line differs.
 * The score badge is the priority the case had, which is what you want to see either way.
 */
function CaseRow({ c, resolved, selected, onSelect }) {
  return (
    <li
      className={'queue-item' + (selected ? ' selected' : '')}
      onClick={() => onSelect(c.id)}
    >
      <span className={'score ' + priorityClass(c.priorityScore)}>
        {c.priorityScore == null ? '—' : Math.round(c.priorityScore)}
      </span>
      <span className="qi-body">
        <span className="qi-title">{c.title || '(no title)'}</span>
        <span className="qi-meta muted">
          {resolved
            ? <>{c.department || 'unrouted'} · resolved {fmtResolved(c.resolvedAt)}</>
            : <>{c.category} · {c.location} · <span className="status">{c.status}</span></>}
        </span>
      </span>
    </li>
  );
}

/** mode "open" = the prioritized queue; mode "resolved" = RESOLVED/CLOSED, newest first. */
export default function Queue({ mode = 'open', version, selectedId, onSelect }) {
  const resolved = mode === 'resolved';
  const [cases, setCases] = useState([]);
  const [error, setError] = useState('');
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    setError('');
    setLoaded(false);
    api.cases(resolved)
      .then((rows) => { setCases(rows); setLoaded(true); })
      .catch((e) => setError(e.message));
  }, [version, resolved]);

  return (
    <aside className="queue">
      <div className="queue-head">
        {resolved ? 'Resolved' : 'Priority queue'} <span className="muted">({cases.length})</span>
      </div>
      {error && <div className="error">{error}</div>}
      {loaded && !error && cases.length === 0 && (
        <div className="empty">{resolved ? 'No resolved cases yet.' : 'No open cases.'}</div>
      )}
      <ul className="queue-list">
        {cases.map((c) => (
          <CaseRow
            key={c.id}
            c={c}
            resolved={resolved}
            selected={c.id === selectedId}
            onSelect={onSelect}
          />
        ))}
      </ul>
    </aside>
  );
}
