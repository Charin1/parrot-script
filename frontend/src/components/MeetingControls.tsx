import { useEffect, useRef, useState } from 'react'
import type { CaptureMode, Meeting, RecordingType, StartRecordingOptions, VideoResolution } from '../types/models'
import { PlayIcon, StopIcon } from './icons'

interface Props {
  meeting: Meeting | null
  liveDurationS?: number
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

const RESOLUTION_OPTIONS: { value: VideoResolution; label: string }[] = [
  { value: '1280x720', label: '720p (1280×720) — Default' },
  { value: '854x480',  label: '480p (854×480) — Low bandwidth' },
  { value: '1920x1080', label: '1080p (1920×1080) — High quality' },
  { value: '2560x1440', label: '1440p (2560×1440) — Ultra quality' },
]

function readStoredAnchor(anchorKey: string): number | null {
  try {
    const raw = sessionStorage.getItem(anchorKey)
    if (!raw) {
      return null
    }
    const parsed = Number(raw)
    if (!Number.isFinite(parsed) || parsed <= 0) {
      return null
    }
    return parsed
  } catch {
    return null
  }
}

function writeStoredAnchor(anchorKey: string, anchor: number): void {
  try {
    sessionStorage.setItem(anchorKey, String(anchor))
  } catch {
    // ignore storage write failures
  }
}

function clearStoredAnchor(anchorKey: string): void {
  try {
    sessionStorage.removeItem(anchorKey)
  } catch {
    // ignore storage clear failures
  }
}

export function MeetingControls({ meeting, liveDurationS = 0, onStart, onStop, busy = false }: Props) {
  const [elapsed, setElapsed] = useState(0)
  const anchorRef = useRef<number | null>(null)
  const [captureMode, setCaptureMode] = useState<CaptureMode>('private')
  const [meetingUrl, setMeetingUrl] = useState('')
  const [assistantVisibleName, setAssistantVisibleName] = useState('Parrot Script Assistant')
  const [recordingType, setRecordingType] = useState<RecordingType>('audio')
  const [videoResolution, setVideoResolution] = useState<VideoResolution>('1280x720')

  useEffect(() => {
    if (!meeting) {
      anchorRef.current = null
      setElapsed(0)
      return
    }

    const seedDuration = Math.max(0, liveDurationS, meeting.duration_s || 0)
    const anchorKey = `parrot-live-anchor-${meeting.id}`

    if (meeting.status !== 'recording') {
      anchorRef.current = null
      clearStoredAnchor(anchorKey)
      setElapsed(seedDuration)
      return
    }

    const now = Date.now()
    const stored = readStoredAnchor(anchorKey)
    let anchor = anchorRef.current ?? stored ?? now - seedDuration * 1000
    const elapsedFromAnchor = Math.max(0, (now - anchor) / 1000)
    if (seedDuration > elapsedFromAnchor + 0.75) {
      anchor = now - seedDuration * 1000
    }
    anchorRef.current = anchor
    writeStoredAnchor(anchorKey, anchor)

    const tick = () => {
      if (anchorRef.current == null) {
        return
      }
      const next = Math.max(seedDuration, Math.max(0, (Date.now() - anchorRef.current) / 1000))
      setElapsed(next)
    }
    tick()

    const id = window.setInterval(tick, 1000)
    return () => window.clearInterval(id)
  }, [meeting?.id, meeting?.status, meeting?.duration_s, liveDurationS])

  useEffect(() => {
    if (!meeting) {
      setCaptureMode('private')
      setMeetingUrl('')
      setAssistantVisibleName('Parrot Script Assistant')
      setRecordingType('audio')
      setVideoResolution('1280x720')
      return
    }

    setCaptureMode(meeting.capture_mode || 'private')
    setMeetingUrl(meeting.meeting_url || '')
    setAssistantVisibleName(meeting.assistant_visible_name || 'Parrot Script Assistant')
    // Restore saved recording type and resolution if the meeting was already configured
    if (meeting.recording_type) setRecordingType(meeting.recording_type)
    if (meeting.video_resolution) {
      const saved = meeting.video_resolution as VideoResolution
      if (RESOLUTION_OPTIONS.some((o) => o.value === saved)) setVideoResolution(saved)
    }
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

  // All config controls are disabled once the session is active
  const controlsLocked = busy || sessionActive
  let providerMetadata: Record<string, unknown> | null = null
  if (meeting.provider_metadata) {
    try {
      const parsed = JSON.parse(meeting.provider_metadata) as Record<string, unknown>
      providerMetadata = parsed && typeof parsed === 'object' ? parsed : null
    } catch {
      providerMetadata = null
    }
  }
  const rawSpeakerIdentityLevel = providerMetadata?.speaker_identity_level
  const speakerIdentityLevel =
    typeof rawSpeakerIdentityLevel === 'string' ? rawSpeakerIdentityLevel : null
  const assistantModeSpeakerHint =
    captureMode === 'assistant' || meeting.capture_mode === 'assistant'
      ? speakerIdentityLevel === 'participant-aware'
        ? 'Speaker attribution: participant-aware (uses meeting participant metadata).'
        : speakerIdentityLevel === 'stream-aware'
          ? 'Speaker attribution: stream-aware (near per-participant audio attribution).'
          : 'Speaker attribution: heuristic from mixed local audio (best-effort; speaker names may need manual rename).'
      : null

  return (
    <div className="controls-panel">
      <div className="controls-title-row">
        <div className="controls-title">
          <h2>{meeting.title}</h2>
          <span className="muted" style={{ fontSize: '0.82rem' }}>Status: {meeting.status}</span>
        </div>
        <div className="controls-actions">
          <span className={`badge ${recording ? 'badge-live' : assistantActive ? 'badge-ok' : 'badge-idle'}`}>
            {statusBadgeLabel}
          </span>
          <button
            type="button"
            disabled={busy || (sessionActive && recordingType === meeting.recording_type)}
            onClick={() =>
              void onStart({
                capture_mode: captureMode,
                ghost_mode: ghostModeEnabled,
                meeting_url: captureMode === 'assistant' ? meetingUrl : null,
                assistant_visible_name: captureMode === 'assistant' ? assistantVisibleName : null,
                recording_type: recordingType,
                video_resolution: recordingType === 'video_audio' ? videoResolution : null,
              })
            }
          >
            <PlayIcon className="btn-icon" width={14} height={14} />
            <span>{sessionActive ? 'Switch' : meeting.status === 'completed' ? 'Resume' : 'Start'}</span>
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

      <div className="start-config">
        {/* ── Ghost Mode ── */}
        <div className="field-group">
          <label htmlFor="ghost-mode-select">Ghost Mode</label>
          <select
            id="ghost-mode-select"
            value={captureMode}
            disabled={sessionActive || busy}
            onChange={(event) => setCaptureMode(event.target.value as CaptureMode)}
          >
            <option value="private">ON: Private on-device capture</option>
            <option value="assistant">OFF: Visible meeting assistant</option>
          </select>
        </div>

        <p className="muted">
          {ghostModeEnabled
            ? 'Ghost mode ON keeps capture fully on this device and invisible to other participants.'
            : 'Ghost mode OFF opens the meeting link on this device and starts visible, real-time capture.'}
        </p>
        {assistantModeSpeakerHint ? (
          <p className="muted">{assistantModeSpeakerHint}</p>
        ) : null}

        {captureMode === 'assistant' ? (
            <div className="field-group">
              <label htmlFor="meeting-url">Meeting URL</label>
              <input
                id="meeting-url"
                value={meetingUrl}
                disabled={sessionActive || busy}
                onChange={(event) => setMeetingUrl(event.target.value)}
                placeholder="https://meet.google.com/... or https://zoom.us/..."
              />
            </div>
        ) : null}

        {/* ── Recording Type ── */}
        <div className="field-group">
          <label htmlFor="recording-type-select">Recording Type</label>
          <select
            id="recording-type-select"
            value={recordingType}
            disabled={busy || (sessionActive && meeting.recording_type === 'video_audio')}
            onChange={(event) => setRecordingType(event.target.value as RecordingType)}
          >
            <option value="audio">Audio Only</option>
            <option value="video_audio">Video + Audio (screen recording)</option>
          </select>
        </div>

        {/* ── Resolution — only shown when video+audio selected ── */}
        {recordingType === 'video_audio' ? (
          <div className="field-group resolution-field">
            <label htmlFor="resolution-select">Resolution</label>
            <select
              id="resolution-select"
              value={videoResolution}
              disabled={busy}
              onChange={(event) => setVideoResolution(event.target.value as VideoResolution)}
            >
              {RESOLUTION_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
            <p className="muted resolution-hint">
              {ghostModeEnabled
                ? 'Full screen will be recorded.'
                : 'The meeting window screen area will be recorded.'}
              {' '}15 fps · H.264 · MP4
            </p>
          </div>
        ) : null}

        <div className="mode-summary">
          <span className={`badge ${ghostModeEnabled ? 'badge-idle' : 'badge-ok'}`}>
            {modeBadgeLabel}
          </span>
          {recordingType === 'video_audio' ? (
            <span className="badge badge-video">🎬 Video</span>
          ) : null}
          {joinState ? <span className="muted">Assistant state: {joinState.replace(/_/g, ' ')}</span> : null}
        </div>
      </div>
    </div>
  )
}
