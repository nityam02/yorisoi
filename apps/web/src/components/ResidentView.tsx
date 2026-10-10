import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Bundle, ResidentDetail } from '../api'
import { Busy, DepthChip, ErrorNote, StatusBadge } from './common'
import { HazardStep } from './HazardStep'
import { ConversationStep } from './ConversationStep'
import { PlanStep } from './PlanStep'
import { OutputsStep } from './OutputsStep'

const STEPS = ['Hazard brief', 'Conversation', 'Plan and checks', 'Copies and approval'] as const

const HOUSEHOLD: Record<string, string> = { alone: 'Lives alone', with_family: 'Lives with family' }
const LANG: Record<string, string> = { ja: 'Japanese', vi: 'Vietnamese', en: 'English' }

export function ResidentView({ id, onChanged }: { id: string; onChanged: () => void }) {
  const [detail, setDetail] = useState<ResidentDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [step, setStep] = useState(0)

  useEffect(() => {
    api.resident(id)
      .then((d) => { setDetail(d); setStep(d.plan ? 2 : 0) })
      .catch((e) => setError(`Could not load ${id}: ${(e as Error).message}`))
  }, [id])

  if (error) return <div className="ws"><ErrorNote error={error} /></div>
  if (!detail) return <div className="ws"><Busy text="Loading hazard brief from public map data…" /></div>

  const { resident: r, hazard, plan } = detail
  const setBundle = (b: Bundle | null) => { setDetail({ ...detail, plan: b }); onChanged() }

  return (
    <div className="ws">
      <header className="ws-head">
        <div>
          <div className="ws-name">{r.name}<small>{r.kana}</small><small>{r.name_en}</small></div>
          <div className="ws-facts">
            <span>{r.age} years</span>
            {r.care_level && <span>{r.care_level}</span>}
            {r.disability_certificate && <span>{r.disability_certificate}</span>}
            <span>{r.household ? HOUSEHOLD[r.household] : 'Household not recorded'}</span>
            <span>Prefers {LANG[r.language] ?? r.language}</span>
            {r.guardian && <span>Guardian: {r.guardian}</span>}
          </div>
          <p className="ws-note">{r.address}. Fictional resident placed at a district centre point, not a real home.</p>
        </div>
        <div style={{ display: 'grid', gap: 6, justifyItems: 'end' }}>
          <DepthChip flood={hazard.home.flood} />
          <StatusBadge status={plan?.status ?? 'none'} />
        </div>
      </header>

      <nav className="steps" role="tablist" aria-label="Plan steps">
        {STEPS.map((label, i) => (
          <button key={label} role="tab" className="step" aria-selected={step === i} disabled={i >= 2 && !plan}
            onClick={() => setStep(i)}>
            <span>{i + 1}</span>{label}
          </button>
        ))}
      </nav>

      {step === 0 && <HazardStep brief={hazard} onNext={() => setStep(1)} />}
      {step === 1 && (
        <ConversationStep id={id} sample={detail.sample_interview} existing={plan?.transcript ?? ''}
          onDrafted={(b) => { setBundle(b); setStep(2) }} />
      )}
      {step === 2 && plan && <PlanStep id={id} bundle={plan} brief={hazard} onChange={setBundle} onNext={() => setStep(3)} />}
      {step === 3 && plan && (
        <OutputsStep id={id} resident={r} bundle={plan} onChange={setBundle}
          onReset={() => { setBundle(null); setStep(1) }} />
      )}
    </div>
  )
}
