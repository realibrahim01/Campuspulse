import React, { useEffect, useState } from 'react';
import { api } from './api.js';

// Admin-only pattern dashboard. Three read-only views, exactly as scoped.
export default function Patterns() {
  const [p, setP] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => { api.patterns().then(setP).catch((e) => setError(e.message)); }, []);

  if (error) return <div className="error" style={{ padding: 24 }}>{error}</div>;
  if (!p) return <div className="empty">Loading…</div>;

  return (
    <div className="patterns">
      <h2 className="patterns-title">Pattern dashboard</h2>
      <div className="pattern-grid">
        <section className="card">
          <h3>Recurring faults <span className="muted">by occurrence count</span></h3>
          <table className="ptable">
            <thead><tr><th>Fault</th><th className="num">Occurrences</th></tr></thead>
            <tbody>
              {p.recurringFaults.map((f, i) => (
                <tr key={i}>
                  <td>{f.location}<span className="muted"> · {f.category}</span></td>
                  <td className="num strong">{f.occurrenceCount}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="card">
          <h3>Departments <span className="muted">by median time to acknowledge</span></h3>
          <table className="ptable">
            <thead><tr><th>Department</th><th className="num">Median</th><th className="num">Ack’d</th></tr></thead>
            <tbody>
              {p.departmentAck.map((d, i) => (
                <tr key={i}>
                  <td>{d.department}</td>
                  <td className="num strong">{d.medianHours == null ? '—' : d.medianHours + 'h'}</td>
                  <td className="num muted">{d.acknowledged}/{d.totalCases}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="card">
          <h3>Locations <span className="muted">by open case volume</span></h3>
          <table className="ptable">
            <thead><tr><th>Location</th><th className="num">Open cases</th></tr></thead>
            <tbody>
              {p.locationVolume.map((l, i) => (
                <tr key={i}>
                  <td>{l.location}<span className="muted"> · {l.type}</span></td>
                  <td className="num strong">{l.openCases}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </div>
  );
}
