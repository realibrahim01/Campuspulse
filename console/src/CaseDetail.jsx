import React, { useEffect, useState } from 'react';
import { api, STATUSES } from './api.js';
import { priorityClass } from './Queue.jsx';

const LABELS = {
  severity: 'Severity / safety',
  people_affected: 'People affected',
  recurrence: 'Recurrence',
  age_vs_sla: 'Age vs SLA',
  location_criticality: 'Location criticality',
};

export default function CaseDetail({ id, onChanged }) {
  const [c, setC] = useState(null);
  const [depts, setDepts] = useState([]);
  const [error, setError] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [deptError, setDeptError] = useState(false);

  function load() {
    setError('');
    api.case(id).then(setC).catch((e) => setError(e.message));
  }
  useEffect(() => { load(); setNote(''); }, [id]);
  useEffect(() => { api.departments().then(setDepts).catch(() => setDeptError(true)); }, []);

  async function changeStatus(status) {
    setBusy(true);
    try { setC(await api.setStatus(id, status, note || null)); setNote(''); onChanged(); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  async function reassign(departmentId) {
    if (!departmentId) return;
    setBusy(true);
    try { setC(await api.override(id, Number(departmentId))); onChanged(); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  if (error) return <div className="error">{error}</div>;
  if (!c) return <div className="empty">Loading…</div>;

  return (
    <div className="detail">
      <div className="detail-head">
        <span className={'score big ' + priorityClass(c.priorityScore)}>
          {c.priorityScore == null ? '—' : Math.round(c.priorityScore)}
        </span>
        <div>
          <h2>Case #{c.id} — {c.category}</h2>
          <div className="muted">
            {c.location} · {c.department || 'unrouted'} · <span className="status">{c.status}</span>
            {' '}· occurrence {c.occurrenceSeq} · {c.reporterCount} reporters
          </div>
        </div>
      </div>

      {c.explanation && <p className="explanation">{c.explanation}</p>}

      <h3>Why this score</h3>
      <table className="breakdown">
        <thead>
          <tr><th>Factor</th><th className="num">Contribution</th><th className="num">Normalized</th><th className="num">Weight</th></tr>
        </thead>
        <tbody>
          {c.components.map((k) => (
            <tr key={k.inputName}>
              <td>{LABELS[k.inputName] || k.inputName}</td>
              <td className="num strong">+{Math.round(k.contribution)}</td>
              <td className="num muted">{k.normalizedValue?.toFixed(2)}</td>
              <td className="num muted">{k.weight?.toFixed(2)}</td>
            </tr>
          ))}
          <tr className="total-row">
            <td>Total priority</td>
            <td className="num strong">{Math.round(c.priorityScore)}</td>
            <td /><td />
          </tr>
        </tbody>
      </table>

      <div className="controls">
        <div className="control">
          <label>Status</label>
          <select value={c.status} onChange={(e) => changeStatus(e.target.value)} disabled={busy}>
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <input
            className="note"
            placeholder="note (optional)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </div>
        <div className="control">
          <label>Reassign to</label>
          {deptError ? (
            <span className="error">Couldn't load departments — reassign unavailable.</span>
          ) : (
            <select value="" onChange={(e) => reassign(e.target.value)} disabled={busy}>
              <option value="">choose department…</option>
              {depts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          )}
        </div>
      </div>

      <h3>Reports on this case <span className="muted">({c.reports.length})</span></h3>
      <ul className="reports">
        {c.reports.map((r) => (
          <li key={r.id} className="report">
            <div className="report-text">{r.text}</div>
            <div className="report-meta withheld">
              Reported anonymously · identity withheld by policy
              <span className="muted"> · {new Date(r.createdAt).toLocaleDateString()}</span>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
