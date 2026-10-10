import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import type { ResidentRow, Stats } from './api'
import { DepthChip, ErrorNote, StatusBadge } from './components/common'
import { ResidentView } from './components/ResidentView'

const idFromHash = () => window.location.hash.replace(/^#\/?/, '') || null

export default function App() {
  const [rows, setRows] = useState<ResidentRow[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [selected, setSelected] = useState<string | null>(idFromHash())
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const [r, s] = await Promise.all([api.residents(), api.stats()])
      setRows(r.residents)
      setStats(s)
      setError(null)
    } catch (e) {
      setError(`Could not load residents: ${(e as Error).message}`)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])
  useEffect(() => {
    const onHash = () => setSelected(idFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  return (
    <div className="shell">
      <aside className="rail" aria-label="Residents on the register">
        <div className="brand">
          <svg className="brand-mark" viewBox="0 0 64 64" aria-hidden>
            <circle cx="32" cy="32" r="28" fill="none" stroke="var(--shu)" strokeWidth="4" />
            <text x="32" y="43" textAnchor="middle" fontSize="30" fontFamily="var(--mincho)" fill="var(--shu)">寄</text>
          </svg>
          <div>
            <h1>Yorisoi 寄り添い</h1>
            <p>Individual evacuation plans, Mabi district (demo)</p>
          </div>
        </div>
        {stats && (
          <div className="coverage">
            <div className="coverage-line">
              <span>Plans approved</span>
              <span><strong>{stats.approved_plans}</strong> of {stats.registered}</span>
            </div>
            <div className="coverage-bar" aria-hidden>
              <span style={{ width: `${stats.coverage * 100}%` }} />
              <i style={{ left: `${stats.national_reference.coverage * 100}%` }} title="National coverage" />
            </div>
            <small>Black mark: Japan's national coverage, {(stats.national_reference.coverage * 100).toFixed(1)}% of {(stats.national_reference.registered / 1e6).toFixed(2)}M people ({stats.national_reference.source}, {stats.national_reference.as_of})</small>
          </div>
        )}
        <div className="worklist-head">Highest risk first</div>
        <ul className="worklist">
          {rows.map((r) => (
            <li key={r.id}>
              <button className="wl-item" aria-current={selected === r.id} onClick={() => { window.location.hash = `/${r.id}` }}>
                <span className="wl-name">{r.name} <span className="muted small">{r.age}</span></span>
                <span className="wl-score" title={r.priority.parts.map((p) => `${p.label}: ${p.points}`).join('\n')}>
                  <b>{r.priority.score}</b>risk
                </span>
                <span className="wl-meta">
                  <DepthChip flood={r.flood} />
                  <StatusBadge status={r.plan_status} />
                </span>
              </button>
            </li>
          ))}
        </ul>
        <p className="disclaimer">All residents are fictional. Hazard and shelter data are real public data from GSI and the Hazard Map Portal.</p>
      </aside>
      <main className="main">
        <ErrorNote error={error} />
        {selected ? (
          <ResidentView key={selected} id={selected} onChanged={refresh} />
        ) : (
          <div className="empty">
            <div>
              <h2>Choose a resident to start a plan</h2>
              <p>The list is ordered by risk: flood depth at home, living alone, mobility and medical devices.<br />Missing information counts as risk, so unknowns rise to the top.</p>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
