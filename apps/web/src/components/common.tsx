import { useEffect, useRef, useState } from 'react'
import type { Flood, PlanStatus } from '../api'
import { LEGEND } from '../api'

export function DepthChip({ flood, lang = 'en' }: { flood: Flood | null | undefined; lang?: 'en' | 'ja' }) {
  if (!flood) return null
  if (flood.status !== 'in_zone') {
    return <span className="depth none" title="Not proof of safety: prefectural-river data is partial">{flood.status === 'no_mapped_zone' ? 'No mapped flood zone' : 'Depth unknown'}</span>
  }
  const row = LEGEND.find((l) => l.id === flood.class_id)
  return (
    <span className="depth" style={{ ['--swatch' as string]: row?.color }}>
      {lang === 'ja' ? flood.label_ja : `Flood depth ${flood.label_en}`}
    </span>
  )
}

const STATUS_TEXT: Record<PlanStatus | 'none', string> = {
  none: 'No plan',
  draft: 'Draft',
  reviewed_with_resident: 'Reviewed with resident',
  approved: 'Approved',
}

export function StatusBadge({ status }: { status: PlanStatus | 'none' }) {
  return <span className={`status ${status}`}>{STATUS_TEXT[status]}</span>
}

/** Evidence chip: shows where a plan line came from (interview quote, register, hazard tool, staff edit). */
export function Evidence({ ids, catalogue }: { ids: string[]; catalogue: Record<string, string> }) {
  return (
    <>
      {ids.map((id) => (
        <EvidenceChip key={id} id={id} text={id === 'STAFF' ? 'Entered or changed by staff' : catalogue[id] ?? 'Unknown source'} />
      ))}
    </>
  )
}

function EvidenceChip({ id, text }: { id: string; text: string }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLSpanElement>(null)
  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === 'Escape' : !ref.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', close)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', close)
    }
  }, [open])
  const kind = id === 'STAFF' ? 'Staff' : id.startsWith('R:') ? 'Register' : id.startsWith('H') || id.startsWith('RT') ? 'Hazard tool'
    : id.startsWith('S') ? 'Shelter data' : id.startsWith('K') ? 'Consent' : 'Conversation'
  return (
    <span ref={ref} style={{ position: 'relative' }}>
      <button type="button" className={`ev${id === 'STAFF' ? ' staff' : ''}`} aria-expanded={open} onClick={() => setOpen(!open)}
        aria-label={`Evidence ${id}`}>
        {id === 'STAFF' ? 'staff' : id}
      </button>
      {open && (
        <span className="ev-pop" role="tooltip" style={{ left: 0, top: '1.8em', width: 340 }}>
          <b>{kind} ({id})</b>
          {text}
        </span>
      )}
    </span>
  )
}

export function Busy({ text }: { text: string }) {
  return (
    <div className="busy" role="status">
      <span className="spinner" aria-hidden /> {text}
    </div>
  )
}

export function ErrorNote({ error }: { error: string | null }) {
  return error ? <div className="error" role="alert">{error}</div> : null
}

export const metres = (m: number | null | undefined) =>
  m == null ? '—' : m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${Math.round(m)} m`
