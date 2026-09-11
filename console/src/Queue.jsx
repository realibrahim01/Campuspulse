import React, { useEffect, useState } from 'react';
import { api } from './api.js';

export function priorityClass(score) {
  if (score == null) return 'p-none';
  if (score >= 70) return 'p-high';
  if (score >= 40) return 'p-med';
  return 'p-low';
}

export default function Queue({ version, selectedId, onSelect }) {
  const [cases, setCases] = useState([]);
  const [error, setError] = useState('');

  useEffect(() => {
    api.cases().then(setCases).catch((e) => setError(e.message));
  }, [version]);

  return (
    <aside className="queue">
      <div className="queue-head">Priority queue <span className="muted">({cases.length})</span></div>
      {error && <div className="error">{error}</div>}
      <ul className="queue-list">
        {cases.map((c) => (
          <li
            key={c.id}
            className={'queue-item' + (c.id === selectedId ? ' selected' : '')}
            onClick={() => onSelect(c.id)}
          >
            <span className={'score ' + priorityClass(c.priorityScore)}>
              {c.priorityScore == null ? '—' : Math.round(c.priorityScore)}
            </span>
            <span className="qi-body">
              <span className="qi-title">{c.title || '(no title)'}</span>
              <span className="qi-meta muted">
                {c.category} · {c.location} · <span className="status">{c.status}</span>
              </span>
            </span>
          </li>
        ))}
      </ul>
    </aside>
  );
}
