import { useRef, useState } from 'react'
import { api } from '../api'
import type { Bundle } from '../api'
import { Busy, ErrorNote } from './common'

// Items the Cabinet Office form needs; the conversation should touch each one.
const TOPICS = [
  'Who lives with them, and who is home in the daytime',
  'Where they sleep, and whether they can climb stairs',
  'How far they can walk; wheelchair or cane',
  'Medical devices and whether they need power',
  'Medicines and where they are kept',
  'Hearing, sight, understanding and judging danger',
  'Two people who can help on the day, with phone numbers',
  'Family to contact, with phone numbers',
  'Pets and things to take',
  'Consent to make the plan and share it with helpers',
]

export function ConversationStep({ id, sample, existing, onDrafted }: {
  id: string; sample: string | null; existing: string; onDrafted: (b: Bundle) => void
}) {
  const [text, setText] = useState(existing)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [recording, setRecording] = useState(false)
  const recorder = useRef<MediaRecorder | null>(null)
  const chunks = useRef<Blob[]>([])

  const transcribe = async (blob: Blob) => {
    setBusy('Transcribing the recording with Gemini…')
    setError(null)
    try {
      const { transcript } = await api.transcribe(id, blob)
      setText((t) => (t ? `${t}\n${transcript}` : transcript))
    } catch (e) {
      setError(`Transcription failed: ${(e as Error).message}`)
    } finally {
      setBusy(null)
    }
  }

  const toggleRecording = async () => {
    if (recording) {
      recorder.current?.stop()
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const rec = new MediaRecorder(stream)
      chunks.current = []
      rec.ondataavailable = (e) => chunks.current.push(e.data)
      rec.onstop = () => {
        stream.getTracks().forEach((t) => t.stop())
        setRecording(false)
        transcribe(new Blob(chunks.current, { type: rec.mimeType || 'audio/webm' }))
      }
      recorder.current = rec
      rec.start()
      setRecording(true)
    } catch (e) {
      setError(`Microphone unavailable: ${(e as Error).message}. You can upload a recording or type the conversation instead.`)
    }
  }

  const draft = async () => {
    setBusy('Extracting facts with their quotes, checking hazards, drafting the plan and running safety checks. This takes about 15 seconds.')
    setError(null)
    try {
      onDrafted(await api.draft(id, text))
    } catch (e) {
      setError(`Could not draft the plan: ${(e as Error).message}`)
      setBusy(null)
    }
  }

  return (
    <div className="conv">
      <div className="stack">
        <div className="actions">
          {sample && <button className="btn" onClick={() => setText(sample)} disabled={!!busy}>Use sample conversation</button>}
          <button className="btn" onClick={toggleRecording} disabled={!!busy && !recording}>
            {recording ? <><span className="rec-dot" aria-hidden />Stop and transcribe</> : 'Record conversation'}
          </button>
          <label className="btn" style={{ cursor: busy ? 'not-allowed' : 'pointer' }}>
            Upload recording
            <input type="file" accept="audio/*" hidden disabled={!!busy}
              onChange={(e) => { const f = e.target.files?.[0]; if (f) transcribe(f); e.target.value = '' }} />
          </label>
        </div>
        <label htmlFor="transcript" className="small muted">
          Conversation transcript (Japanese). Ask for consent before recording. Every fact in the plan must quote these words.
        </label>
        <textarea id="transcript" className="transcript" value={text} onChange={(e) => setText(e.target.value)}
          placeholder="ケアマネ: …&#10;本人: …" lang="ja" />
        <ErrorNote error={error} />
        {busy ? <Busy text={busy} /> : (
          <div className="actions">
            <button className="btn primary" onClick={draft} disabled={text.trim().length < 20}>Draft plan</button>
            <span className="small muted">Gemini drafts; you review and approve.</span>
          </div>
        )}
      </div>
      <aside className="panel panel-pad">
        <h2 className="section-title">Topics the plan needs</h2>
        <ul className="small" style={{ paddingLeft: '1.1em', margin: 0, display: 'grid', gap: 6 }}>
          {TOPICS.map((t) => <li key={t}>{t}</li>)}
        </ul>
        <p className="small muted" style={{ marginTop: 12 }}>
          Taken from the Cabinet Office sample form (個別避難計画 様式例). Anything not said in the conversation stays blank in the draft.
        </p>
      </aside>
    </div>
  )
}
