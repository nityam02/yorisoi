import { useState } from 'react'
import Markdown from 'react-markdown'
import { api } from '../api'
import type { Bundle, Resident } from '../api'
import { Busy, ErrorNote, metres } from './common'

type Tab = 'official' | 'easy_read' | 'supporter_card' | 'translation'

// Plans belong to Japanese municipalities: show Japan time.
const jst = (iso: string) => new Date(iso).toLocaleString('ja-JP', { timeZone: 'Asia/Tokyo', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
const jstDate = (iso: string) => jst(iso).slice(0, 10).replace(/\//g, '.')

function Hanko({ date, name, animate }: { date: string; name: string; animate: boolean }) {
  // A date seal (日付印): approval word, date, approver. The human sign-off made visible.
  return (
    <svg className={`hanko ${animate ? 'stamp' : 'still'}`} viewBox="0 0 120 120" role="img" aria-label={`Approved on ${date} by ${name}`}>
      <circle cx="60" cy="60" r="55" fill="none" stroke="#c4382c" strokeWidth="5" />
      <line x1="10" y1="45" x2="110" y2="45" stroke="#c4382c" strokeWidth="3" />
      <line x1="10" y1="77" x2="110" y2="77" stroke="#c4382c" strokeWidth="3" />
      <text x="60" y="36" textAnchor="middle" fontSize="22" fontFamily="var(--mincho)" fill="#c4382c" fontWeight="700">承認</text>
      <text x="60" y="68" textAnchor="middle" fontSize="15" fontFamily="var(--gothic)" fill="#c4382c">{date}</text>
      <text x="60" y="100" textAnchor="middle" fontSize="17" fontFamily="var(--mincho)" fill="#c4382c">{name}</text>
    </svg>
  )
}

function OfficialPlan({ b, r, stamp }: { b: Bundle; r: Resident; stamp: { animate: boolean } | null }) {
  const p = b.plan
  const approved = [...b.audit].reverse().find((a) => a.action === 'status:approved')
  const reviewed = [...b.audit].reverse().find((a) => a.action === 'status:reviewed_with_resident')
  const sup = [...p.supporters, null, null].slice(0, Math.max(2, p.supporters.length))
  const con = [...p.emergency_contacts, null, null].slice(0, Math.max(2, p.emergency_contacts.length))
  return (
    <div className="doc" lang="ja">
      <div className="doc-head">
        <h1>個別避難計画</h1>
        <table className="sealbox">
          <thead><tr><th>作成</th><th>承認</th></tr></thead>
          <tbody>
            <tr>
              <td>{reviewed ? reviewed.actor.split(' ')[0] : ''}</td>
              <td>{stamp && approved && <Hanko animate={stamp.animate} date={jstDate(approved.at)} name={approved.actor.split(' ')[0]} />}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <table>
        <tbody>
          <tr><th>氏名</th><td>{r.name}（{r.kana}）{r.guardian ? `　保護者: ${r.guardian}` : ''}</td></tr>
          <tr><th>生年月日・年齢</th><td>{r.birth_date}　{r.age}歳　性別: {r.sex}</td></tr>
          <tr><th>住所又は居所</th><td>{r.address}　電話: {r.phone}</td></tr>
          <tr><th>同居家族等</th><td>{p.household.text}</td></tr>
          <tr><th>避難場所</th><td>{p.shelter.name}（{p.shelter.address}）　自宅から{metres(p.shelter.distance_m)}</td></tr>
          <tr><th>避難のタイミング</th><td>{p.evacuation_timing.label}</td></tr>
          <tr><th>避難方法</th><td>{p.transport.text}</td></tr>
          {con.map((c, i) => <tr key={`c${i}`}><th>緊急時連絡先{'①②③④'[i]}</th><td>{c ? `${c.name}（${c.relation}）　${c.phone ?? '電話番号未確認'}` : ''}</td></tr>)}
          {sup.map((s, i) => <tr key={`s${i}`}><th>避難支援等実施者{'①②③④'[i]}</th><td>{s ? `${s.name}（${s.relation}）　${s.phone ?? '電話番号未確認'}` : ''}</td></tr>)}
          <tr><th>避難時に配慮しなくてはならない事項</th><td>{p.considerations.map((c) => <div key={c.key}>☑ {c.label.split(' / ')[0]}{c.detail ? `：${c.detail}` : ''}</div>)}</td></tr>
          <tr><th>特記事項</th><td>{[p.home_hazard, ...p.special_notes].map((n, i) => <div key={i}>・{n.text}</div>)}</td></tr>
          <tr><th>避難支援時の留意事項</th><td>{p.support_notes.map((n, i) => <div key={i}>・{n.text}</div>)}</td></tr>
          <tr><th>持ち出し品</th><td>{p.items_to_take.map((n) => n.text).join('、')}</td></tr>
          <tr><th>情報提供への同意</th><td>{p.consent.share_with_supporters === 'yes' ? '同意あり' : p.consent.share_with_supporters === 'no' ? '同意なし' : '未確認'}</td></tr>
        </tbody>
      </table>
      <p style={{ fontSize: 12, marginTop: 12 }}>様式は内閣府「避難行動要支援者の避難行動支援に関する取組指針」の様式例に準拠。想定浸水深は想定最大規模（ハザードマップポータルサイト）。</p>
    </div>
  )
}

export function OutputsStep({ id, resident, bundle, onChange, onReset }: {
  id: string; resident: Resident; bundle: Bundle; onChange: (b: Bundle) => void; onReset: () => void
}) {
  const [tab, setTab] = useState<Tab>('official')
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [justApproved, setJustApproved] = useState(false)
  const [careManager, setCareManager] = useState('佐藤 (care manager)')
  const [supervisor, setSupervisor] = useState('高橋 (supervisor)')
  const o = bundle.outputs
  const critical = bundle.flags.filter((f) => f.severity === 'critical')
  const status = bundle.status

  const run = async (label: string, fn: () => Promise<Bundle>, after?: () => void) => {
    setBusy(label)
    setError(null)
    try {
      onChange(await fn())
      after?.()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  const generate = () => run('Writing the easy-read copy, the helper card and the translation…',
    () => api.outputs(id, ['easy_read', 'supporter_card', 'translation']))

  const tabs: [Tab, string][] = [
    ['official', 'Official plan'],
    ['easy_read', 'Easy-read (やさしい日本語)'],
    ['supporter_card', 'Helper card'],
    ['translation', o.translation ? `Translation (${o.translation.language})` : 'Translation'],
  ]

  return (
    <div className="outwrap">
      <div>
        <div className="tabs no-print" role="tablist">
          {tabs.map(([k, label]) => (
            <button key={k} role="tab" className="tab" aria-selected={tab === k} onClick={() => setTab(k)}>{label}</button>
          ))}
        </div>
        {tab === 'official' && <OfficialPlan b={bundle} r={resident} stamp={status === 'approved' ? { animate: justApproved } : null} />}
        {tab !== 'official' && (() => {
          const text = tab === 'translation' ? o.translation?.text : o[tab]
          return text
            ? <div className={`doc md${tab === 'easy_read' ? ' easy' : ''}`}><Markdown>{text}</Markdown></div>
            : (
              <div className="doc md" style={{ display: 'grid', placeItems: 'center' }}>
                <div style={{ textAlign: 'center' }}>
                  <p className="muted" style={{ marginBottom: 12 }}>These copies are written by Gemini from the plan above, adding nothing new.</p>
                  {busy ? <Busy text={busy} /> : <button className="btn primary" onClick={generate}>Write the copies</button>}
                </div>
              </div>
            )
        })()}
      </div>

      <aside className="panel panel-pad approval">
        <h2 className="section-title">Approval</h2>
        <ol>
          <li className="done"><span className="dot" />Drafted from the conversation</li>
          <li className={status === 'draft' ? 'current' : 'done'}><span className="dot" />Read back to the resident and confirmed</li>
          <li className={status === 'approved' ? 'done' : status === 'reviewed_with_resident' ? 'current' : ''}><span className="dot" />Approved by a supervisor</li>
        </ol>
        {status === 'draft' && (
          <div className="stack">
            <label className="small">Care worker<input className="field" value={careManager} onChange={(e) => setCareManager(e.target.value)} /></label>
            <button className="btn primary" disabled={!!busy}
              onClick={() => run('Recording the review…', () => api.status(id, 'reviewed_with_resident', careManager))}>
              Mark as reviewed with resident
            </button>
          </div>
        )}
        {status === 'reviewed_with_resident' && (
          <div className="stack">
            <label className="small">Supervisor<input className="field" value={supervisor} onChange={(e) => setSupervisor(e.target.value)} /></label>
            <button className="btn seal" disabled={!!busy || critical.length > 0}
              onClick={() => run('Approving…', () => api.status(id, 'approved', supervisor), () => { setJustApproved(true); setTab('official') })}>
              Approve plan
            </button>
            {critical.length > 0 && <p className="small" style={{ color: '#8d241b' }}>Resolve {critical.length} must-fix check{critical.length > 1 ? 's' : ''} on the plan before approval.</p>}
            <button className="btn quiet small" onClick={() => run('Reopening…', () => api.status(id, 'draft', careManager))}>Back to draft</button>
          </div>
        )}
        {status === 'approved' && (
          <div className="stack">
            <p className="small">Plan approved. Share the helper card only with the people the resident agreed to.</p>
            <button className="btn quiet small" onClick={() => run('Reopening…', () => api.status(id, 'draft', supervisor))}>Reopen for changes</button>
          </div>
        )}
        <ErrorNote error={error} />
        {busy && tab === 'official' && <Busy text={busy} />}
        <div className="actions" style={{ margin: '16px 0' }}>
          <button className="btn" onClick={() => { setTab('official'); setTimeout(() => window.print(), 50) }}>Print plan</button>
          <a className="btn" href={api.csvUrl(id)}>Download CSV</a>
          {!o.easy_read && tab === 'official' && <button className="btn" onClick={generate} disabled={!!busy}>Write the copies</button>}
        </div>
        <h3 className="section-title" style={{ fontSize: 14 }}>History</h3>
        <ul className="audit">
          {[...bundle.audit].reverse().map((a, i) => (
            <li key={i}>{jst(a.at)} {a.actor}: {a.action.replace('status:', 'status ')}{a.detail ? `, ${a.detail}` : ''}</li>
          ))}
        </ul>
        <button className="btn quiet small" style={{ marginTop: 12 }} onClick={async () => { await api.reset(id); onReset() }}>Discard plan and start over</button>
      </aside>
    </div>
  )
}
