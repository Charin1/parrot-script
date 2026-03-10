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

    const baseDuration = meeting.duration_s || 0
    // We don't have a reliable 'started_at' for the *current* recording session in the Meeting model yet,
    // but we can approximate the current slice by checking how long we've been running this effect.
    // Ideally the backend provides a `recording_started_at` timestamp.
    // For now, let's just use a simple local timer if recording.
    const startTick = Date.now()
    const tick = () => setElapsed(baseDuration + Math.max(0, (Date.now() - startTick) / 1000))
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
          {recording ? `LIVE ${formatDuration(elapsed)}` : meeting.status === 'completed' ? 'Completed' : 'Idle'}
        </span>

        <button type="button" disabled={busy || recording} onClick={() => void onStart()}>
          <PlayIcon className="btn-icon" width={14} height={14} />
          <span>{meeting.status === 'completed' ? 'Resume' : 'Start'}</span>
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
