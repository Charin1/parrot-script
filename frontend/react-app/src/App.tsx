import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, clearApiToken, formatApiError, getApiToken, setApiToken } from './api/client'
import { LiveTranscript } from './components/LiveTranscript'
import { MeetingControls } from './components/MeetingControls'
import { PastMeetingsDashboard } from './components/PastMeetingsDashboard'
import { RuntimeStatusPanel } from './components/RuntimeStatusPanel'
import { SearchBar } from './components/SearchBar'
import { SummaryPanel } from './components/SummaryPanel'
import { ThemeSelector } from './components/ThemeSelector'
import { PlusIcon } from './components/icons'
import { useLocalRuntime } from './hooks/useLocalRuntime'
import { useTheme } from './hooks/useTheme'
import { useWebSocket } from './hooks/useWebSocket'
import type { Meeting, Summary } from './types/models'

function App() {
  const [meetings, setMeetings] = useState<Meeting[]>([])
  const [selectedMeetingId, setSelectedMeetingId] = useState<string | null>(null)
  const [newTitle, setNewTitle] = useState('Weekly Sync')
  const [summary, setSummary] = useState<Summary | null>(null)
  const [busy, setBusy] = useState(false)
  const [appError, setAppError] = useState<string | null>(null)
  const [apiTokenInput, setApiTokenInput] = useState(() => getApiToken())
  const [activeApiToken, setActiveApiToken] = useState(() => getApiToken())
  const [viewMode, setViewMode] = useState<'workspace' | 'dashboard'>('workspace')
  const { mode, resolved, setMode } = useTheme()
  const { browserOnline, backendReachability } = useLocalRuntime()
  const previousBackendReachability = useRef(backendReachability)
  const authReady = activeApiToken.trim().length > 0

  const selectedMeeting = useMemo(
    () => meetings.find((meeting) => meeting.id === selectedMeetingId) ?? null,
    [meetings, selectedMeetingId],
  )

  const { segments, status, setSegments, connectionState } = useWebSocket(
    selectedMeetingId,
    activeApiToken,
  )

  const refreshMeetings = useCallback(async (signal?: AbortSignal) => {
    const list = await api.listMeetings(signal)
    setMeetings(list)
    setSelectedMeetingId((current) => {
      if (current && list.some((meeting) => meeting.id === current)) {
        return current
      }
      return list.length > 0 ? list[0].id : null
    })
  }, [])

  useEffect(() => {
    if (!authReady) {
      setMeetings([])
      setSelectedMeetingId(null)
      return
    }

    const controller = new AbortController()
    void refreshMeetings(controller.signal).catch((error) => {
      if (!controller.signal.aborted) {
        setAppError(formatApiError(error))
      }
    })

    return () => controller.abort()
  }, [authReady, refreshMeetings])

  useEffect(() => {
    if (!authReady || !selectedMeetingId) {
      setSummary(null)
      setSegments([])
      return
    }

    const controller = new AbortController()

    void api
      .getTranscript(selectedMeetingId, controller.signal)
      .then((items) => {
        if (!controller.signal.aborted) {
          setSegments(items)
        }
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setAppError(formatApiError(error))
        }
      })

    void api
      .getSummary(selectedMeetingId, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          setSummary(data)
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setSummary(null)
        }
      })

    return () => controller.abort()
  }, [authReady, selectedMeetingId, setSegments])

  useEffect(() => {
    const recovered =
      previousBackendReachability.current !== 'reachable' && backendReachability === 'reachable'

    previousBackendReachability.current = backendReachability

    if (!recovered || !authReady) {
      return
    }

    const controller = new AbortController()
    void refreshMeetings(controller.signal).catch((error) => {
      if (!controller.signal.aborted) {
        setAppError(formatApiError(error))
      }
    })

    return () => controller.abort()
  }, [authReady, backendReachability, refreshMeetings])

  const runBusy = async (action: () => Promise<void>) => {
    setBusy(true)
    setAppError(null)
    try {
      await action()
    } catch (error) {
      setAppError(formatApiError(error))
    } finally {
      setBusy(false)
    }
  }

  const createMeeting = async () => {
    const title = newTitle.trim()
    if (!title) {
      setAppError('Meeting title cannot be empty')
      return
    }

    await runBusy(async () => {
      const created = await api.createMeeting(title)
      await refreshMeetings()
      setSelectedMeetingId(created.id)
      setSummary(null)
      setSegments([])
    })
  }

  const startMeeting = async () => {
    if (!selectedMeetingId) return
    await runBusy(async () => {
      await api.startRecording(selectedMeetingId)
      await refreshMeetings()
    })
  }

  const stopMeeting = async () => {
    if (!selectedMeetingId) return
    await runBusy(async () => {
      await api.stopRecording(selectedMeetingId)
      await refreshMeetings()
    })
  }

  const generateSummary = async () => {
    if (!selectedMeetingId) return
    await runBusy(async () => {
      const data = await api.generateSummary(selectedMeetingId)
      setSummary(data)
    })
  }

  const saveApiToken = async () => {
    const cleanToken = apiTokenInput.trim()

    if (!cleanToken) {
      setApiToken('')
      setActiveApiToken('')
      setMeetings([])
      setSelectedMeetingId(null)
      setSummary(null)
      setSegments([])
      setAppError(null)
      return
    }

    setBusy(true)
    setApiToken(cleanToken)
    setActiveApiToken(cleanToken)
    setAppError(null)

    try {
      await refreshMeetings()
    } catch (error) {
      setAppError(formatApiError(error))
    } finally {
      setBusy(false)
    }
  }

  const removeApiToken = () => {
    clearApiToken()
    setApiTokenInput('')
    setActiveApiToken('')
    setMeetings([])
    setSelectedMeetingId(null)
    setSummary(null)
    setSegments([])
    setAppError(null)
  }

  return (
    <div className="app-shell">
      <aside className="left-panel">
        <header className="brand-panel">
          <div className="brand-top-row">
            <img className="brand-logo" src="/parrot-script-logo.svg" alt="Parrot Script logo" />
            <div className="brand-copy">
              <span className="brand-kicker">Local-first meeting intelligence</span>
              <h1>Parrot Script</h1>
            </div>
          </div>
          <p>
            Capture system audio, transcribe on-device, label speakers, and generate summaries
            without exposing the runtime to your LAN by default.
          </p>
          <p className="mode-caption">
            Active theme: <strong>{resolved}</strong> ({mode === 'system' ? 'auto' : mode})
          </p>
          <ThemeSelector mode={mode} onChange={setMode} />
        </header>

        <div className="panel security-panel">
          <div className="panel-header">
            <h3>Local API Security</h3>
            <span className={`badge ${authReady ? 'badge-ok' : 'badge-failed'}`}>
              {authReady ? 'Token Loaded' : 'Token Missing'}
            </span>
          </div>
          <p className="muted">
            The local API expects a shared token. It stays in this browser and is attached to API
            and live stream requests.
          </p>
          <div className="security-form">
            <input
              type="password"
              value={apiTokenInput}
              onChange={(event) => setApiTokenInput(event.target.value)}
              placeholder="Enter API token"
            />
            <button type="button" onClick={() => void saveApiToken()} disabled={busy}>
              Save Token
            </button>
            <button type="button" className="secondary" onClick={removeApiToken} disabled={busy}>
              Clear
            </button>
          </div>
        </div>

        <RuntimeStatusPanel
          browserOnline={browserOnline}
          backendReachability={backendReachability}
          streamState={connectionState}
        />

        {appError ? (
          <div className="panel error-banner" role="alert">
            {appError}
          </div>
        ) : null}

        <div className="panel create-panel">
          <h3>New Meeting</h3>
          <div className="search-row">
            <input
              value={newTitle}
              onChange={(event) => setNewTitle(event.target.value)}
              placeholder="Meeting title"
              maxLength={200}
            />
            <button type="button" onClick={() => void createMeeting()} disabled={busy || !authReady}>
              <PlusIcon className="btn-icon" width={14} height={14} />
              <span>Create</span>
            </button>
          </div>
        </div>



        <SearchBar
          disabled={!authReady}
          onSearch={(query, signal) => api.search(query, 10, signal)}
          onSelectMeeting={(meetingId) => {
            setAppError(null)
            setSelectedMeetingId(meetingId)
            setViewMode('workspace')
          }}
        />
      </aside>

      <main className="right-panel">
        <div className="panel workspace-switch">
          <button
            type="button"
            className={viewMode === 'workspace' ? '' : 'secondary'}
            onClick={() => setViewMode('workspace')}
          >
            Live Workspace
          </button>
          <button
            type="button"
            className={viewMode === 'dashboard' ? '' : 'secondary'}
            onClick={() => setViewMode('dashboard')}
          >
            Past Dashboard
          </button>
        </div>

        {viewMode === 'dashboard' ? (
          <PastMeetingsDashboard
            meetings={meetings}
            onOpenMeeting={(meetingId) => {
              setSelectedMeetingId(meetingId)
              setViewMode('workspace')
            }}
          />
        ) : (
          <>
            <MeetingControls
              meeting={selectedMeeting}
              onStart={startMeeting}
              onStop={stopMeeting}
              busy={busy || !authReady}
            />
            {status ? (
              <div className="panel status-panel">
                Speakers detected: <strong>{status.speakers_detected}</strong> | Duration:{' '}
                <strong>{Math.round(status.duration_s)}s</strong>
              </div>
            ) : null}
            <LiveTranscript segments={segments} />
            <SummaryPanel
              summary={summary}
              onGenerate={generateSummary}
              busy={busy}
              disabled={!authReady}
            />
          </>
        )}
      </main>
    </div>
  )
}

export default App
