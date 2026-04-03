import { useEffect, useState } from 'react'
import type { CaptureMode, Meeting, StartRecordingOptions } from '../types/models'
import { PlayIcon, StopIcon } from './icons'

interface Props {
  meeting: Meeting | null
  onStart: (options: StartRecordingOptions) => Promise<void>
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
  const [captureMode, setCaptureMode] = useState<CaptureMode>('private')
  const [meetingUrl, setMeetingUrl] = useState('')
  const [assistantVisibleName, setAssistantVisibleName] = useState('Parrot Script Assistant')

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

  useEffect(() => {
    if (!meeting) {
      setCaptureMode('private')
      setMeetingUrl('')
      setAssistantVisibleName('Parrot Script Assistant')
      return
    }

    setCaptureMode(meeting.capture_mode || 'private')
    setMeetingUrl(meeting.meeting_url || '')
    setAssistantVisibleName(meeting.assistant_visible_name || 'Parrot Script Assistant')
  }, [meeting])

  if (!meeting) {
    return <div className="controls-panel">Select or create a meeting to begin.</div>
  }

  const recording = meeting.status === 'recording'
  const assistantActive = meeting.status === 'active' && meeting.capture_mode === 'assistant'
  const sessionActive = recording || assistantActive
  const ghostModeEnabled = captureMode === 'private'
  const joinState = (captureMode === 'assistant' || meeting.capture_mode === 'assistant')
    ? meeting.assistant_join_status
    : null
  const modeBadgeLabel = ghostModeEnabled ? 'Private Mode' : 'Assistant Mode'
  const statusBadgeLabel = recording
    ? `LIVE ${formatDuration(elapsed)}`
    : assistantActive
      ? `ASSISTANT ${joinState ? joinState.replace(/_/g, ' ').toUpperCase() : 'ACTIVE'}`
      : meeting.status === 'completed'
        ? 'Completed'
        : 'Idle'

  return (
    <div className="controls-panel">
      <div className="controls-content">
        <h2>{meeting.title}</h2>
        <p className="muted">Status: {meeting.status}</p>
        {!sessionActive ? (
          <div className="start-config">
            <div className="field-group">
              <label htmlFor="ghost-mode-select">Ghost Mode</label>
              <select
                id="ghost-mode-select"
                value={captureMode}
                disabled={busy || recording}
                onChange={(event) => setCaptureMode(event.target.value as CaptureMode)}
              >
                <option value="private">ON: Private on-device capture</option>
                <option value="assistant">OFF: Visible meeting assistant</option>
              </select>
            </div>

            <p className="muted">
              {ghostModeEnabled
                ? 'Ghost mode ON keeps capture fully on this device and invisible to other participants.'
                : 'Ghost mode OFF opens the meeting link on this device and starts visible, real-time capture. Provider join prompts and visible name rules still come from Meet, Zoom, or Teams.'}
            </p>

            {captureMode === 'assistant' ? (
              <div className="start-config-row">
                <div className="field-group">
                  <label htmlFor="meeting-url">Meeting URL</label>
                  <input
                    id="meeting-url"
                    value={meetingUrl}
                    disabled={busy || recording}
                    onChange={(event) => setMeetingUrl(event.target.value)}
                    placeholder="https://meet.google.com/... or https://zoom.us/..."
                  />
                </div>
                <div className="field-group">
                  <label htmlFor="assistant-name">Assistant Name</label>
                  <input
                    id="assistant-name"
                    value={assistantVisibleName}
                    disabled={busy || recording}
                    onChange={(event) => setAssistantVisibleName(event.target.value)}
                    placeholder="Parrot Script Assistant"
                  />
                </div>
              </div>
            ) : null}

            <div className="mode-summary">
              <span className={`badge ${ghostModeEnabled ? 'badge-idle' : 'badge-ok'}`}>
                {modeBadgeLabel}
              </span>
              {joinState ? <span className="muted">Assistant state: {joinState.replace(/_/g, ' ')}</span> : null}
            </div>
          </div>
        ) : (
          <div className="mode-summary">
            <span className={`badge ${ghostModeEnabled ? 'badge-idle' : 'badge-ok'}`}>
              {modeBadgeLabel}
            </span>
            <span className="muted">
              {ghostModeEnabled
                ? 'Ghost mode ON'
                : `Assistant state: ${joinState ? joinState.replace(/_/g, ' ') : 'pending'}`}
            </span>
          </div>
        )}
      </div>

      <div className="controls-actions">
        <span className={`badge ${recording ? 'badge-live' : assistantActive ? 'badge-ok' : 'badge-idle'}`}>
          {statusBadgeLabel}
        </span>

        <button
          type="button"
          disabled={busy || sessionActive}
          onClick={() =>
            void onStart({
              capture_mode: captureMode,
              ghost_mode: ghostModeEnabled,
              meeting_url: captureMode === 'assistant' ? meetingUrl : null,
              assistant_visible_name: captureMode === 'assistant' ? assistantVisibleName : null,
            })
          }
        >
          <PlayIcon className="btn-icon" width={14} height={14} />
          <span>{meeting.status === 'completed' ? 'Resume' : 'Start'}</span>
        </button>
        <button
          type="button"
          className="secondary"
          disabled={busy || !sessionActive}
          onClick={() => void onStop()}
        >
          <StopIcon className="btn-icon" width={14} height={14} />
          <span>Stop</span>
        </button>
      </div>
    </div>
  )
}
