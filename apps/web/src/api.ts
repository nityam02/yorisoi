export type Flood = {
  status: 'in_zone' | 'no_mapped_zone' | 'unknown_colour' | 'error'
  class_id: number
  label_ja: string
  label_en: string
  min_m: number | null
  max_m: number | null
}

export type Shelter = {
  id: string
  name: string
  address: string
  lat: number
  lon: number
  distance_m: number
  hazards: string[]
  certified_for_flood: boolean
  flood_at_site: Flood | null
}

export type Route = {
  method: 'google_routes_walk' | 'straight_line'
  note?: string
  distance_m: number
  duration_s: number | null
  path: [number, number][]
  worst_flood_on_path: Flood
}

export type Brief = {
  home: { lat: number; lon: number; flood: Flood }
  shelters: Shelter[]
  suggested_shelter_id: string | null
  route_to_suggested: Route | null
  attributions: { label: string; url: string }[]
}

export type Priority = { score: number; parts: { label: string; points: number }[] }

export type Resident = {
  id: string
  name: string
  kana: string
  name_en: string
  birth_date: string
  age: number
  sex: string
  address: string
  lat: number
  lon: number
  phone: string
  household: 'alone' | 'with_family' | null
  household_detail: string
  care_level: string | null
  disability_certificate: string | null
  mobility: string | null
  medical_device: boolean | null
  language: string
  guardian: string | null
  register_notes: string
}

export type ResidentRow = Pick<Resident, 'id' | 'name' | 'name_en' | 'age' | 'address' | 'care_level' | 'household' | 'language'> & {
  flood: Flood
  priority: Priority
  plan_status: PlanStatus | 'none'
  open_flags: number
  has_sample_interview: boolean
}

export type Cited = { text: string; evidence: string[] }
export type Person = { id: string; role: 'supporter' | 'emergency_contact'; name: string; relation: string; phone: string | null; address: string | null; notes: string | null; quote: string }
export type Consideration = { key: string; label: string; detail: string; evidence: string[] }
export type Fact = { id: string; topic: string; value: string; quote: string }

export type Plan = {
  person: Partial<Resident>
  household: Cited
  shelter: {
    id: string | null; name: string; address: string; lat: number | null; lon: number | null
    certified_for_flood: boolean; flood_at_site: Flood | null; distance_m: number | null; reason: Cited; overridden_by_code: boolean
  }
  route: Route | null
  evacuation_timing: { level: 'level3' | 'level4'; label: string; reason: Cited }
  transport: Cited
  emergency_contacts: Person[]
  supporters: Person[]
  considerations: Consideration[]
  home_hazard: Cited
  special_notes: Cited[]
  support_notes: Cited[]
  items_to_take: Cited[]
  consent: { id: string; plan_creation: string; share_with_supporters: string; quote: string }
}

export type Flag = { id: string; severity: 'critical' | 'warning' | 'info'; source: 'rule' | 'ai_review'; field: string; message: string }
export type PlanStatus = 'draft' | 'reviewed_with_resident' | 'approved'

export type Bundle = {
  resident_id: string
  status: PlanStatus
  created_at: string
  updated_at: string
  transcript: string
  extraction: { facts: Fact[]; people: Person[]; considerations: (Consideration & { id: string; quote: string })[]; consent: Plan['consent'] }
  rejected: { id: string; quote?: string }[]
  evidence: Record<string, string>
  plan: Plan
  flags: Flag[]
  outputs: { easy_read?: string; supporter_card?: string; translation?: { language: string; text: string } }
  models: Record<string, string>
  audit: { at: string; actor: string; action: string; detail: string }[]
}

export type ResidentDetail = { resident: Resident; hazard: Brief; priority: Priority; plan: Bundle | null; sample_interview: string | null }

export type Stats = {
  registered: number
  approved_plans: number
  coverage: number
  national_reference: { registered: number; with_plans: number; coverage: number; as_of: string; source: string }
}

// Each browser gets its own private sandbox on the shared demo, so visitors never see or overwrite each other's plans.
function sandboxId(): string {
  const make = () => (crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`).replace(/[^A-Za-z0-9-]/g, '')
  try {
    let id = localStorage.getItem('yorisoi-sandbox')
    if (!id) {
      id = make()
      localStorage.setItem('yorisoi-sandbox', id)
    }
    return id
  } catch {
    return (window as unknown as { __yorisoiSandbox?: string }).__yorisoiSandbox ??= make()
  }
}
const SANDBOX = sandboxId()

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  headers.set('X-Yorisoi-Session', SANDBOX)
  const res = await fetch(`/api${path}`, { ...init, headers })
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch { /* body was not JSON */ }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  residents: () => call<{ residents: ResidentRow[] }>('/residents'),
  stats: () => call<Stats>('/stats'),
  resident: (id: string) => call<ResidentDetail>(`/residents/${id}`),
  draft: (id: string, transcript: string) => call<Bundle>(`/residents/${id}/draft`, json('POST', { transcript, actor: 'care_manager' })),
  review: (id: string) => call<Bundle>(`/residents/${id}/plan/review`, { method: 'POST' }),
  edit: (id: string, plan: Plan, note: string) => call<Bundle>(`/residents/${id}/plan`, json('PUT', { plan, note, actor: 'care_manager' })),
  status: (id: string, status: PlanStatus, actor: string) => call<Bundle>(`/residents/${id}/plan/status`, json('POST', { status, actor })),
  outputs: (id: string, kinds: string[]) => call<Bundle>(`/residents/${id}/plan/outputs`, json('POST', { kinds })),
  reset: (id: string) => call<{ ok: boolean }>(`/residents/${id}/plan`, { method: 'DELETE' }),
  transcribe: (id: string, audio: Blob) => {
    const form = new FormData()
    form.append('audio', audio, 'conversation.webm')
    return call<{ transcript: string }>(`/residents/${id}/transcribe`, { method: 'POST', body: form })
  },
  csvUrl: (id: string) => `/api/residents/${id}/plan/export.csv?sid=${SANDBOX}`,
}

export const LEGEND: { id: number; ja: string; en: string; color: string }[] = [
  { id: 1, ja: '0.5m未満', en: 'under 0.5 m', color: '#F7F5A9' },
  { id: 2, ja: '0.5〜3m', en: '0.5–3 m', color: '#FFD8C0' },
  { id: 3, ja: '3〜5m', en: '3–5 m', color: '#FFB7B7' },
  { id: 4, ja: '5〜10m', en: '5–10 m', color: '#FF9191' },
  { id: 5, ja: '10〜20m', en: '10–20 m', color: '#F285C9' },
  { id: 6, ja: '20m以上', en: '20 m or more', color: '#DC7ADC' },
]

export const floodColor = (f: Flood | null | undefined) =>
  f && f.status === 'in_zone' ? LEGEND.find((l) => l.id === f.class_id)?.color ?? '#ccc' : 'transparent'
