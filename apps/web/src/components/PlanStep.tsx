import { useState } from 'react'
import type { ReactNode } from 'react'
import { api } from '../api'
import type { Brief, Bundle, Cited, Flag, Person, Plan } from '../api'
import { Busy, DepthChip, ErrorNote, Evidence, metres } from './common'

const CONSIDERATIONS: [string, string][] = [
  ['long_term_care', '介護保険の認定 / long-term care certified'],
  ['disability_certificate', '手帳所持 / disability certificate'],
  ['intractable_disease', '難病等の認定 / intractable disease'],
  ['medical_device', '医療機器の装着等 / medical device'],
  ['cannot_stand_or_walk', '立つことや歩行ができない / cannot stand or walk'],
  ['hearing', '音が聞こえない / hearing'],
  ['vision', '物が見えない / sight'],
  ['understanding', '言葉や文字の理解が難しい / understanding'],
  ['judgement', '危険なことを判断できない / judging danger'],
  ['recognition', '顔を見ても分からない / recognising people'],
  ['other', 'その他 / other'],
]

const SEVERITY_ORDER = { critical: 0, warning: 1, info: 2 } as const
// Flags about the route or home hazard live on the shelter and notes rows.
const ROW_FOR: Record<string, string> = { route: 'shelter', home_hazard: 'special_notes', extraction: 'person', plan: 'person' }
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x))

/** Keep evidence on lines the user did not change; changed or new lines are staff-entered. */
function relist(before: Cited[], text: string): Cited[] {
  return text.split('\n').map((t) => t.trim()).filter(Boolean)
    .map((t) => before.find((b) => b.text === t) ?? { text: t, evidence: ['STAFF'] })
}

function Row({ k, title, en, flags, onEdit, editing, children, editor }: {
  k: string; title: string; en: string; flags: Flag[]; onEdit?: () => void; editing: boolean; children: ReactNode; editor?: ReactNode
}) {
  const worst = flags.reduce<Flag['severity'] | null>((w, f) => (w === null || SEVERITY_ORDER[f.severity] < SEVERITY_ORDER[w] ? f.severity : w), null)
  const cls = worst === 'critical' ? ' flagged-critical' : worst === 'warning' ? ' flagged' : ''
  return (
    <div className={`row${cls}`} id={`row-${k}`}>
      <div className="k"><b lang="ja">{title}</b>{en}</div>
      <div className="v">
        {editing ? editor : children}
        {onEdit && !editing && <button className="btn quiet small no-print" onClick={onEdit}>Edit</button>}
      </div>
    </div>
  )
}

function Lines({ items, ev }: { items: Cited[]; ev: Record<string, string> }) {
  if (!items.length) return <div className="line empty">Nothing recorded</div>
  return <>{items.map((c, i) => <div className="line" key={i}><span className="t">{c.text}</span><Evidence ids={c.evidence} catalogue={ev} /></div>)}</>
}

function People({ people, ev }: { people: Person[]; ev: Record<string, string> }) {
  if (!people.length) return <div className="line empty">Nobody named</div>
  return (
    <>
      {people.map((p, i) => (
        <div className="person" key={p.id}>
          <b>{['①', '②', '③', '④'][i] ?? ''} {p.name}</b> <span className="muted">（{p.relation}）</span>
          <span style={{ marginLeft: 8 }}>{p.phone ?? <span className="muted">phone not recorded</span>}</span>
          <Evidence ids={[p.id.startsWith('PS') ? 'STAFF' : p.id]} catalogue={ev} />
        </div>
      ))}
    </>
  )
}

function Editor({ children, onSave, onCancel, busy }: { children: ReactNode; onSave: () => void; onCancel: () => void; busy: boolean }) {
  return (
    <div className="inline-edit">
      {children}
      <div className="actions">
        <button className="btn" onClick={onCancel} disabled={busy}>Cancel</button>
        <button className="btn primary" onClick={onSave} disabled={busy}>Save change</button>
      </div>
    </div>
  )
}

function PeopleEditor({ value, onChange, role }: { value: Person[]; onChange: (p: Person[]) => void; role: Person['role'] }) {
  const set = (i: number, patch: Partial<Person>) => onChange(value.map((p, j) => (j === i ? { ...p, ...patch } : p)))
  return (
    <div style={{ display: 'grid', gap: 8 }}>
      {value.map((p, i) => (
        <div key={p.id} style={{ display: 'grid', gridTemplateColumns: '1fr 110px 150px auto', gap: 6 }}>
          <input aria-label="Name" value={p.name} onChange={(e) => set(i, { name: e.target.value })} />
          <input aria-label="Relationship" value={p.relation} onChange={(e) => set(i, { relation: e.target.value })} />
          <input aria-label="Phone" value={p.phone ?? ''} placeholder="Phone" onChange={(e) => set(i, { phone: e.target.value || null })} />
          <button className="btn quiet" onClick={() => onChange(value.filter((_, j) => j !== i))}>Remove</button>
        </div>
      ))}
      <button className="btn quiet" style={{ justifySelf: 'start' }} onClick={() => onChange([...value, {
        id: `PS${Date.now() % 100000}`, role, name: '', relation: '', phone: null, address: null, notes: 'entered by staff', quote: '',
      }])}>Add person</button>
    </div>
  )
}

export function PlanStep({ id, bundle, brief, onChange, onNext }: {
  id: string; bundle: Bundle; brief: Brief; onChange: (b: Bundle) => void; onNext: () => void
}) {
  const plan = bundle.plan
  const ev = bundle.evidence
  const [editing, setEditing] = useState<string | null>(null)
  const [draft, setDraft] = useState<Plan>(clone(plan))
  const [listText, setListText] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const locked = bundle.status === 'approved'

  const flagsFor = (k: string) => bundle.flags.filter((f) => f.field === k)
  const start = (k: string, text = '') => { setDraft(clone(plan)); setListText(text); setEditing(k); setError(null) }
  const save = async (next: Plan, note: string) => {
    setBusy('Saving and re-running the safety rules…')
    try {
      onChange(await api.edit(id, next, note))
      setEditing(null)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }
  const review = async () => {
    setBusy('Gemini is reviewing the whole plan for contradictions and gaps…')
    setError(null)
    try { onChange(await api.review(id)) } catch (e) { setError((e as Error).message) } finally { setBusy(null) }
  }
  const editable = (k: string, text = '') => (locked ? undefined : () => start(k, text))
  const cancel = () => setEditing(null)
  const flags = [...bundle.flags].sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity])
  const count = (s: Flag['severity']) => bundle.flags.filter((f) => f.severity === s).length
  const s = plan.shelter

  return (
    <div className="planwrap">
      <div className="form">
        <div className="form-title">
          <h2 lang="ja">個別避難計画（下書き）</h2>
          <span className="small muted">Draft by Gemini from the conversation. Click a chip to see its source.</span>
        </div>

        <Row k="person" title="本人" en="Resident" flags={flagsFor('person')} editing={false}>
          <div><b>{plan.person.name}</b> （{plan.person.kana}） {plan.person.sex} {plan.person.age}歳 <Evidence ids={['R:name']} catalogue={ev} /></div>
          <div className="small muted">{plan.person.address} ・ {plan.person.phone}{plan.person.guardian ? ` ・ 保護者: ${plan.person.guardian}` : ''}</div>
        </Row>

        <Row k="household" title="同居家族等" en="Household" flags={flagsFor('household')} editing={editing === 'household'}
          onEdit={editable('household', plan.household.text)}
          editor={<Editor busy={!!busy} onCancel={cancel} onSave={() => save({ ...draft, household: { text: listText, evidence: ['STAFF'] } }, 'household')}>
            <textarea rows={2} value={listText} onChange={(e) => setListText(e.target.value)} />
          </Editor>}>
          <Lines items={[plan.household]} ev={ev} />
        </Row>

        <Row k="shelter" title="避難場所" en="Evacuation destination" flags={flagsFor('shelter').concat(flagsFor('route'))}
          editing={editing === 'shelter'} onEdit={editable('shelter', plan.shelter.reason.text)}
          editor={<Editor busy={!!busy} onCancel={cancel} onSave={() => save({ ...draft, shelter: { ...draft.shelter, reason: { text: listText, evidence: ['STAFF', draft.shelter.id ?? ''] } } }, `shelter → ${draft.shelter.id}`)}>
            <select value={draft.shelter.id ?? ''} onChange={(e) => setDraft({ ...draft, shelter: { ...draft.shelter, id: e.target.value } })}>
              {brief.shelters.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.id} {x.name}, {metres(x.distance_m)}, {x.certified_for_flood ? 'flood-designated' : 'NOT flood-designated'}, site: {x.flood_at_site?.label_en ?? 'unknown'}
                </option>
              ))}
            </select>
            <textarea rows={2} value={listText} onChange={(e) => setListText(e.target.value)} aria-label="Reason" />
          </Editor>}>
          <div><b>{s.name}</b> <span className="muted small">{s.address}</span></div>
          <div className="small" style={{ display: 'flex', gap: 12, flexWrap: 'wrap', margin: '2px 0 4px' }}>
            <span>{s.certified_for_flood ? 'Designated for floods' : 'Not designated for floods'}</span>
            <span>{metres(s.distance_m)} away</span>
            <span>Site: <DepthChip flood={s.flood_at_site} /></span>
          </div>
          <Lines items={[plan.shelter.reason]} ev={ev} />
        </Row>

        <Row k="evacuation_timing" title="避難のタイミング" en="When to leave" flags={flagsFor('evacuation_timing')}
          editing={editing === 'evacuation_timing'} onEdit={editable('evacuation_timing', plan.evacuation_timing.reason.text)}
          editor={<Editor busy={!!busy} onCancel={cancel} onSave={() => save({
            ...draft, evacuation_timing: {
              level: draft.evacuation_timing.level,
              label: draft.evacuation_timing.level === 'level3' ? '警戒レベル3（高齢者等避難）で避難開始' : '警戒レベル4（避難指示）で避難開始',
              reason: { text: listText, evidence: ['STAFF'] },
            },
          }, 'timing')}>
            <select value={draft.evacuation_timing.level}
              onChange={(e) => setDraft({ ...draft, evacuation_timing: { ...draft.evacuation_timing, level: e.target.value as 'level3' | 'level4' } })}>
              <option value="level3">Alert Level 3: older people and those needing help evacuate (高齢者等避難)</option>
              <option value="level4">Alert Level 4: evacuation order (避難指示)</option>
            </select>
            <textarea rows={2} value={listText} onChange={(e) => setListText(e.target.value)} aria-label="Reason" />
          </Editor>}>
          <div><b lang="ja">{plan.evacuation_timing.label}</b></div>
          <Lines items={[plan.evacuation_timing.reason]} ev={ev} />
        </Row>

        <Row k="transport" title="避難方法" en="Transport" flags={flagsFor('transport')} editing={editing === 'transport'}
          onEdit={editable('transport', plan.transport.text)}
          editor={<Editor busy={!!busy} onCancel={cancel} onSave={() => {
            const helper = (document.getElementById('transport-helper') as HTMLSelectElement | null)?.value
            save({ ...draft, transport: { text: listText, evidence: ['STAFF', ...(helper ? [helper] : [])] } }, 'transport')
          }}>
            <textarea rows={2} value={listText} onChange={(e) => setListText(e.target.value)} />
            <select id="transport-helper" defaultValue="">
              <option value="">No named driver or helper yet</option>
              {plan.supporters.map((p) => <option key={p.id} value={p.id}>{p.name}（{p.relation}）</option>)}
            </select>
          </Editor>}>
          <Lines items={[plan.transport]} ev={ev} />
        </Row>

        <Row k="supporters" title="避難支援等実施者" en="Helpers on the day" flags={flagsFor('supporters')} editing={editing === 'supporters'}
          onEdit={editable('supporters')}
          editor={<Editor busy={!!busy} onCancel={cancel} onSave={() => save(draft, 'supporters')}>
            <PeopleEditor role="supporter" value={draft.supporters} onChange={(p) => setDraft({ ...draft, supporters: p })} />
          </Editor>}>
          <People people={plan.supporters} ev={ev} />
        </Row>

        <Row k="emergency_contacts" title="緊急時連絡先" en="Emergency contacts" flags={flagsFor('emergency_contacts')}
          editing={editing === 'emergency_contacts'} onEdit={editable('emergency_contacts')}
          editor={<Editor busy={!!busy} onCancel={cancel} onSave={() => save(draft, 'emergency contacts')}>
            <PeopleEditor role="emergency_contact" value={draft.emergency_contacts} onChange={(p) => setDraft({ ...draft, emergency_contacts: p })} />
          </Editor>}>
          <People people={plan.emergency_contacts} ev={ev} />
        </Row>

        <Row k="considerations" title="避難時に配慮しなくてはならない事項" en="Needs during evacuation" flags={flagsFor('considerations')}
          editing={editing === 'considerations'} onEdit={editable('considerations')}
          editor={<Editor busy={!!busy} onCancel={cancel} onSave={() => save(draft, 'considerations')}>
            <div className="checks">
              {CONSIDERATIONS.map(([key, label]) => {
                const on = draft.considerations.some((c) => c.key === key)
                return (
                  <label key={key}>
                    <input type="checkbox" checked={on} onChange={() => setDraft({
                      ...draft,
                      considerations: on ? draft.considerations.filter((c) => c.key !== key)
                        : [...draft.considerations, { key, label, detail: '', evidence: ['STAFF'] }],
                    })} />
                    {label}
                  </label>
                )
              })}
            </div>
          </Editor>}>
          <div className="checks">
            {CONSIDERATIONS.map(([key, label]) => {
              const c = plan.considerations.find((x) => x.key === key)
              return (
                <div key={key} className={c ? 'on' : 'muted'}>
                  {c ? '☑' : '☐'} {label.split(' / ')[0]}
                  {c && <><span className="small" style={{ fontWeight: 400 }}>：{c.detail}</span> <Evidence ids={c.evidence} catalogue={ev} /></>}
                </div>
              )
            })}
          </div>
        </Row>

        <Row k="special_notes" title="特記事項" en="Facts a helper must know" flags={flagsFor('special_notes').concat(flagsFor('home_hazard'))}
          editing={editing === 'special_notes'} onEdit={editable('special_notes', plan.special_notes.map((c) => c.text).join('\n'))}
          editor={<Editor busy={!!busy} onCancel={cancel} onSave={() => save({ ...draft, special_notes: relist(plan.special_notes, listText) }, 'special notes')}>
            <textarea rows={6} value={listText} onChange={(e) => setListText(e.target.value)} aria-label="One note per line" />
          </Editor>}>
          <Lines items={[plan.home_hazard, ...plan.special_notes]} ev={ev} />
        </Row>

        <Row k="support_notes" title="避難支援時の留意事項" en="How to help on the day" flags={flagsFor('support_notes')}
          editing={editing === 'support_notes'} onEdit={editable('support_notes', plan.support_notes.map((c) => c.text).join('\n'))}
          editor={<Editor busy={!!busy} onCancel={cancel} onSave={() => save({ ...draft, support_notes: relist(plan.support_notes, listText) }, 'support notes')}>
            <textarea rows={6} value={listText} onChange={(e) => setListText(e.target.value)} aria-label="One note per line" />
          </Editor>}>
          <Lines items={plan.support_notes} ev={ev} />
        </Row>

        <Row k="items_to_take" title="持ち出し品" en="Things to take" flags={flagsFor('items_to_take')}
          editing={editing === 'items_to_take'} onEdit={editable('items_to_take', plan.items_to_take.map((c) => c.text).join('\n'))}
          editor={<Editor busy={!!busy} onCancel={cancel} onSave={() => save({ ...draft, items_to_take: relist(plan.items_to_take, listText) }, 'items')}>
            <textarea rows={5} value={listText} onChange={(e) => setListText(e.target.value)} aria-label="One item per line" />
          </Editor>}>
          <Lines items={plan.items_to_take} ev={ev} />
        </Row>

        <Row k="consent" title="同意" en="Consent" flags={flagsFor('consent')} editing={editing === 'consent'} onEdit={editable('consent')}
          editor={<Editor busy={!!busy} onCancel={cancel} onSave={() => save({ ...draft, consent: { ...draft.consent, quote: '（職員が本人に確認）' } }, 'consent')}>
            <label className="small">Consent to share with helpers
              <select value={draft.consent.share_with_supporters}
                onChange={(e) => setDraft({ ...draft, consent: { ...draft.consent, share_with_supporters: e.target.value } })}>
                <option value="yes">Yes</option><option value="no">No</option><option value="unclear">Unclear</option>
              </select>
            </label>
          </Editor>}>
          <div>計画作成: <b>{plan.consent.plan_creation}</b>　支援者への情報提供: <b>{plan.consent.share_with_supporters}</b> <Evidence ids={['K1']} catalogue={ev} /></div>
          {plan.consent.quote && <div className="small muted" lang="ja">「{plan.consent.quote.replace(/\n/g, ' ')}」</div>}
        </Row>
      </div>

      <aside className="flags">
        <div className="panel panel-pad">
          <h2 className="section-title">Checks</h2>
          <div className="flag-counts">
            <div className="flag-count critical"><b>{count('critical')}</b>must fix</div>
            <div className="flag-count warning"><b>{count('warning')}</b>check</div>
            <div className="flag-count info"><b>{count('info')}</b>notes</div>
          </div>
          {flags.map((f) => (
            <div key={f.id} className={`flag ${f.severity}`}>
              <div className="flag-meta">
                <a href={`#row-${ROW_FOR[f.field] ?? f.field}`} onClick={(e) => { e.preventDefault(); document.getElementById(`row-${ROW_FOR[f.field] ?? f.field}`)?.scrollIntoView({ behavior: 'smooth' }) }}>
                  {f.field.replace(/_/g, ' ')}
                </a>
                <span>{f.source === 'rule' ? 'Safety rule' : 'Gemini review'}</span>
              </div>
              {f.message}
            </div>
          ))}
          <ErrorNote error={error} />
          {busy ? <Busy text={busy} /> : (
            <div className="actions" style={{ marginTop: 8 }}>
              <button className="btn" onClick={review} disabled={locked}>Check again with Gemini</button>
              <button className="btn primary" onClick={onNext}>Copies and approval</button>
            </div>
          )}
          <p className="small muted" style={{ marginTop: 12 }}>
            Safety rules run on every save. Gemini's review can add notes but cannot change the plan or clear a rule.
            {bundle.rejected.length > 0 && ` ${bundle.rejected.length} extracted item(s) were dropped for lacking a quote.`}
          </p>
        </div>
      </aside>
    </div>
  )
}
