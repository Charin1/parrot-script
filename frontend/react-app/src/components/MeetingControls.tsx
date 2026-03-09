import { useEffect, useState } from 'react'
import type { Meeting } from '../types/models'
import { PlayIcon, StopIcon } from './icons'

interface Props {
  meeting: Meeting | null
  onStart: () => Promise<void>
  onStop: () => Promise<void>
  busy?: boolean
}

function formatDuration(seconds: number): string {
  const hrs = Math.floor(seconds / 3600)
  const mins = Math.floor((seconds % 3600) / 60)
  const secs = Math.floor(seconds % 60)
  return [hrs, mins, secs].map((n) => n.toString().padStart(2, '0')).join(':')
}

export function MeetingControls({ meeting, onStart, onStop, busy = false }: Props) {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    if (!meeting || meeting.status !== 'recording') {
      setElapsed(0)
      return
    }

    const started = new Date(meeting.created_at).getTime()
    const tick = () => setElapsed(Math.max(0, (Date.now() - started) / 1000))
    tick()

    const id = window.setInterval(tick, 1000)
    return () => window.clearInterval(id)
  }, [meeting])

  if (!meeting) {
    return <div className="controls-panel">Select or create a meeting to begin.</div>
  }

  const recording = meeting.status === 'recording'

  return (
    <div className="controls-panel">
      <div>
        <h2>{meeting.title}</h2>
        <p className="muted">Status: {meeting.status}</p>
      </div>

      <div className="controls-actions">
        <span className={`badge ${recording ? 'badge-live' : 'badge-idle'}`}>
          {recording ? `LIVE ${formatDuration(elapsed)}` : 'Idle'}
        </span>

        <button type="button" disabled={busy || recording} onClick={() => void onStart()}>
          <PlayIcon className="btn-icon" width={14} height={14} />
          <span>Start</span>
        </button>
        <button
          type="button"
          className="secondary"
          disabled={busy || !recording}
          onClick={() => void onStop()}
        >
          <StopIcon className="btn-icon" width={14} height={14} />
          <span>Stop</span>
        </button>
      </div>
    </div>
  )
}
