import { useEffect, useRef, useState } from 'react'
import { api, formatApiError } from '../api/client'
import type { TranscriptProgress } from '../types/models'

interface Props {
  disabled: boolean
  activeMeetingId: string | null
  transcriptProgress: TranscriptProgress | null
  onImported: (meetingId: string) => void
  onSelectMeeting: (meetingId: string) => void
}

function formatTime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${mins}m ${secs}s`
}

export function UploadMeetingView({ disabled, activeMeetingId, transcriptProgress, onImported, onSelectMeeting }: Props) {
  const [title, setTitle] = useState('Uploaded Meeting')
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [estimatedSecondsRemaining, setEstimatedSecondsRemaining] = useState<number | null>(null)
  const startTimeRef = useRef<number | null>(null)

  useEffect(() => {
    if (!transcriptProgress) {
      startTimeRef.current = null
      setEstimatedSecondsRemaining(null)
      return
    }
    if (transcriptProgress.current <= 1) {
      startTimeRef.current = Date.now()
      setEstimatedSecondsRemaining(null)
      return
    }
    if (startTimeRef.current && transcriptProgress.current > 0) {
      const elapsed = (Date.now() - startTimeRef.current) / 1000
      const secondsPerChunk = elapsed / transcriptProgress.current
      const remaining = transcriptProgress.total - transcriptProgress.current
      setEstimatedSecondsRemaining(Math.max(0, Math.round(remaining * secondsPerChunk)))
    }
  }, [transcriptProgress?.current, transcriptProgress?.total])

  const startImport = async () => {
    setError(null)
    setNotice(null)
    const cleanTitle = title.trim()
    if (!cleanTitle) {
      setError('Meeting name is required.')
      return
    }
    if (!file) {
      setError('Select an audio or video file to upload.')
      return
    }

    setBusy(true)
    try {
      const meeting = await api.importMeeting(cleanTitle, file)
      setNotice(`Import started: ${meeting.title}`)
      onImported(meeting.id)
    } catch (e) {
      setError(formatApiError(e))
    } finally {
      setBusy(false)
    }
  }

  const percent =
    transcriptProgress && transcriptProgress.total > 0
      ? Math.min(100, Math.round((transcriptProgress.current / transcriptProgress.total) * 100))
      : null

  return (
    <div className="panel" style={{ padding: '1.2rem' }}>
      <div className="panel-header">
        <h3>Upload Meeting</h3>
      </div>

      <p className="muted" style={{ marginTop: '-0.2rem' }}>
        Upload an audio/video file and Parrot Script will transcribe it in the background.
      </p>

      {error ? (
        <div className="panel error-banner" style={{ margin: '0.8rem 0' }}>
          {error}
        </div>
      ) : null}

      {notice ? (
        <div className="panel info-banner" style={{ margin: '0.8rem 0' }}>
          {notice}
        </div>
      ) : null}

      <div className="field-group" style={{ marginTop: '0.8rem' }}>
        <label htmlFor="upload-meeting-title">Meeting Name</label>
        <input
          id="upload-meeting-title"
          value={title}
          disabled={disabled || busy}
          onChange={(e) => setTitle(e.target.value)}
          maxLength={200}
          placeholder="e.g. Customer Call – April 19"
        />
      </div>

      <div className="field-group" style={{ marginTop: '0.8rem' }}>
        <label htmlFor="upload-meeting-file">Audio/Video File</label>
        <input
          id="upload-meeting-file"
          type="file"
          disabled={disabled || busy}
          accept="audio/*,video/*"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        {file ? (
          <div className="muted" style={{ fontSize: '0.8rem', marginTop: '0.3rem' }}>
            Selected: <strong>{file.name}</strong> ({Math.round(file.size / 1024 / 1024)} MB)
          </div>
        ) : null}
      </div>

      <div style={{ display: 'flex', gap: '0.6rem', marginTop: '1rem', alignItems: 'center' }}>
        <button type="button" onClick={() => void startImport()} disabled={disabled || busy}>
          {busy ? 'Uploading…' : 'Start Import'}
        </button>
        {activeMeetingId ? (
          <button type="button" className="secondary" onClick={() => onSelectMeeting(activeMeetingId)} disabled={busy}>
            Open Current Meeting
          </button>
        ) : null}
      </div>

      {transcriptProgress ? (
        <div className="panel" style={{ marginTop: '1rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.6rem' }}>
            <strong>Transcription Progress</strong>
            {percent !== null ? <span className="muted">{percent}%</span> : null}
          </div>
          <div className="muted" style={{ fontSize: '0.85rem', marginTop: '0.3rem' }}>
            Chunk {transcriptProgress.current} of {transcriptProgress.total}
            {estimatedSecondsRemaining !== null ? ` · Est. ${formatTime(estimatedSecondsRemaining)} left` : ''}
          </div>
          <div style={{ marginTop: '0.6rem', width: '100%' }}>
            <div
              style={{
                width: '100%',
                height: '8px',
                backgroundColor: 'rgba(var(--accent-rgb), 0.1)',
                borderRadius: '4px',
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  width: `${percent ?? 0}%`,
                  height: '100%',
                  backgroundColor: 'var(--accent)',
                  transition: 'width 0.5s ease-out',
                }}
              />
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}

