import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, formatApiError } from './api/client'
import { LiveTranscript } from './components/LiveTranscript'
import { MeetingControls } from './components/MeetingControls'
import { PastMeetingsDashboard } from './components/PastMeetingsDashboard'
import { RuntimeStatusPanel } from './components/RuntimeStatusPanel'
import { SearchBar } from './components/SearchBar'
import { SummaryPanel } from './components/SummaryPanel'
import { ThemeSelector } from './components/ThemeSelector'
import { useMeetings } from './hooks/useMeetings'
import { useLowBandwidth } from './hooks/useLowBandwidth'
import { PlusIcon } from './components/icons'
import { useAuth } from './hooks/useAuth'
import { useTheme } from './hooks/useTheme'
import { useWebSocket } from './hooks/useWebSocket'
import type { MeetingStatus, PlaybackSyncSource } from './types/models'
import { VideoPlayer } from './components/VideoPlayer'

function App() {
  const [busy, setBusy] = useState(false)
  const [appError, setAppError] = useState<string | null>(null)
  const [appNotice, setAppNotice] = useState<string | null>(null)
  const [newTitle, setNewTitle] = useState('Weekly Sync')
  const [viewMode, setViewMode] = useState<'workspace' | 'dashboard'>('workspace')
  const [videoExpanded, setVideoExpanded] = useState(false)
  const [playbackTime, setPlaybackTime] = useState(0)
  const [playbackPlaying, setPlaybackPlaying] = useState(false)
  const [playbackSource, setPlaybackSource] = useState<PlaybackSyncSource>('system')
  const { mode, resolved, setMode } = useTheme()
  const { lowBandwidth, toggleLowBandwidth } = useLowBandwidth()

  const {
    browserOnline,
    backendReachability,
    authRequired,
    authReady,
    apiTokenInput,
    setApiTokenInput,
    activeApiToken,
    authBadgeClass,
    authBadgeLabel,
    authDescription,
    saveApiToken: hookSaveApiToken,
    removeApiToken: hookRemoveApiToken,
  } = useAuth()
  
  const previousBackendReachability = useRef(backendReachability)

  const {
    meetings,
    setMeetings,
    selectedMeetingId,
    setSelectedMeetingId,
    summary,
    setSummary,
    clearMeetingsState,
    refreshMeetings,
    createMeeting,
    startMeeting,
    stopMeeting,
    generateSummary,
    deleteMeeting,
  } = useMeetings(authReady, setAppError, setAppNotice, setBusy, (segments) => setSegments(segments))

  const { segments, status, setSegments, connectionState } = useWebSocket(
    selectedMeetingId,
    activeApiToken,
  )

  const selectedMeeting = useMemo(
    () => meetings.find((meeting) => meeting.id === selectedMeetingId) ?? null,
    [meetings, selectedMeetingId],
  )
  const speakerCountLabel = 'Estimated speakers'
  const videoEnabled = Boolean(
    selectedMeeting && (selectedMeeting.recording_type === 'video_audio' || selectedMeeting.has_video),
  )
  const videoStatusHint =
    selectedMeeting?.status === 'recording'
      ? 'Recording in video mode. Click to expand or minimize.'
      : selectedMeeting?.has_video
        ? 'Recording complete. Click to open or minimize playback.'
        : 'Video mode is enabled.'
  const videoSrc = useMemo(() => {
    if (!selectedMeeting || !videoEnabled || !videoExpanded || lowBandwidth) {
      return null
    }
    return api.getVideoUrl(selectedMeeting.id)
  }, [activeApiToken, lowBandwidth, selectedMeeting?.id, videoEnabled, videoExpanded])

  const effectiveStatus = useMemo<MeetingStatus | undefined>(() => {
    if (!selectedMeetingId) {
      return undefined
    }

    const derivedDuration = segments.length > 0 ? segments[segments.length - 1].end_time : 0
    const fallbackSpeakerCount =
      segments.length > 0 ? new Set(segments.map((segment) => segment.speaker)).size : 0

    if (status) {
      return {
        ...status,
        speakers_detected:
          status.speakers_detected > 0 ? status.speakers_detected : fallbackSpeakerCount,
        duration_s: Math.max(status.duration_s, derivedDuration),
      }
    }

    if (selectedMeeting?.status === 'recording' && (derivedDuration > 0 || fallbackSpeakerCount > 0)) {
      return {
        meeting_id: selectedMeetingId,
        recording: true,
        speakers_detected: fallbackSpeakerCount,
        duration_s: derivedDuration,
      }
    }

    return undefined
  }, [segments, selectedMeeting?.status, selectedMeetingId, status])

  const handleDashboardFiltersChange = useCallback((filters: {
    q?: string
    status?: string
    from_date?: string
    to_date?: string
  }) => {
    void refreshMeetings(undefined, filters)
  }, [refreshMeetings])


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
    if (!authReady || !selectedMeetingId || selectedMeeting?.status !== 'recording') {
      return
    }

    let disposed = false
    let inFlight = false

    const pollLiveMeeting = async () => {
      if (disposed || inFlight) {
        return
      }

      inFlight = true
      try {
        const [meeting, items] = await Promise.all([
          api.getMeeting(selectedMeetingId),
          api.getTranscript(selectedMeetingId),
        ])

        if (disposed) {
          return
        }

        setMeetings((current) =>
          current.map((existing) => (existing.id === meeting.id ? meeting : existing)),
        )
        setSegments(items)
      } catch {
        // Keep websocket as the primary live path. Polling is a silent fallback.
      } finally {
        inFlight = false
      }
    }

    void pollLiveMeeting()
    // Adaptive interval: double the poll frequency on low-bandwidth to reduce HTTP overhead
    const pollInterval = lowBandwidth ? 8000 : 4000
    const intervalId = window.setInterval(() => {
      void pollLiveMeeting()
    }, pollInterval)

    return () => {
      disposed = true
      window.clearInterval(intervalId)
    }
  }, [authReady, selectedMeetingId, selectedMeeting?.status, setSegments, lowBandwidth])

  useEffect(() => {
    setVideoExpanded(false)
  }, [selectedMeetingId])

  useEffect(() => {
    setPlaybackTime(0)
    setPlaybackPlaying(false)
    setPlaybackSource('system')
  }, [selectedMeetingId])

  useEffect(() => {
    if (!videoEnabled) {
      setVideoExpanded(false)
    }
  }, [videoEnabled])

  useEffect(() => {
    if (!videoExpanded && playbackSource === 'video') {
      setPlaybackSource('system')
    }
  }, [videoExpanded, playbackSource])

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

  const onCreateMeetingClick = () => {
    const title = newTitle.trim()
    if (!title) {
      setAppError('Meeting title cannot be empty')
      return
    }
    void createMeeting(title)
  }

  const handleSaveToken = async () => {
    const saved = hookSaveApiToken(apiTokenInput)
    if (!saved) {
      if (authRequired !== false) {
        clearMeetingsState()
      }
      return
    }
    setBusy(true)
    setAppError(null)
    try {
      await refreshMeetings()
    } catch (error) {
      setAppError(formatApiError(error))
    } finally {
      setBusy(false)
    }
  }

  const handleRemoveToken = () => {
    hookRemoveApiToken()
    setAppError(null)
    if (authRequired !== false) {
      clearMeetingsState()
    }
  }

  const handlePlaybackTimeChange = useCallback((time: number, source: PlaybackSyncSource) => {
    if (!Number.isFinite(time) || time < 0) {
      return
    }
    setPlaybackSource(source)
    setPlaybackTime(time)
  }, [])

  const handlePlaybackPlayStateChange = useCallback((isPlaying: boolean, source: PlaybackSyncSource) => {
    setPlaybackSource(source)
    setPlaybackPlaying(isPlaying)
  }, [])

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
            <span className={`badge ${authBadgeClass}`}>
              {authBadgeLabel}
            </span>
          </div>
          <p className="muted">
            {authDescription}
          </p>
          <div className="security-form">
            <input
              type="password"
              value={apiTokenInput}
              onChange={(event) => setApiTokenInput(event.target.value)}
              placeholder="Enter API token"
            />
            <button type="button" onClick={() => void handleSaveToken()} disabled={busy}>
              Save Token
            </button>
            <button type="button" className="secondary" onClick={handleRemoveToken} disabled={busy}>
              Clear
            </button>
          </div>
        </div>

        <RuntimeStatusPanel
          browserOnline={browserOnline}
          backendReachability={backendReachability}
          streamState={connectionState}
          lowBandwidth={lowBandwidth}
          onToggleLowBandwidth={toggleLowBandwidth}
        />

        {appError ? (
          <div className="panel error-banner" role="alert">
            {appError}
          </div>
        ) : null}

        {!appError && appNotice ? (
          <div className="panel info-banner" role="status">
            {appNotice}
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
            <button type="button" onClick={onCreateMeetingClick} disabled={busy || !authReady}>
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
            onDeleteMeeting={(id) => {
              const m = meetings.find((x) => x.id === id)
              void deleteMeeting(id, m?.title || 'this meeting')
            }}
            onFiltersChange={handleDashboardFiltersChange}
          />

        ) : (
          <>
            <MeetingControls
              meeting={selectedMeeting}
              liveDurationS={effectiveStatus?.duration_s ?? 0}
              onStart={startMeeting}
              onStop={stopMeeting}
              busy={busy || !authReady}
            />
            {effectiveStatus ? (
              <div className="panel status-panel">
                {speakerCountLabel}: <strong>{effectiveStatus.speakers_detected}</strong> | Duration:{' '}
                <strong>{Math.round(effectiveStatus.duration_s)}s</strong>
              </div>
            ) : null}
            {videoEnabled ? (
              <div className="panel video-toggle-panel">
                <button
                  type="button"
                  className={videoExpanded ? '' : 'secondary'}
                  onClick={() => setVideoExpanded((current) => !current)}
                >
                  {videoExpanded ? 'Minimize Video' : 'Video'}
                </button>
                <span className="muted">{videoStatusHint}</span>
              </div>
            ) : null}
            {videoEnabled && videoExpanded ? (
              lowBandwidth ? (
                <div className="panel video-low-bandwidth-panel">
                  <span className="badge badge-idle">Video Ready</span>
                  <span className="muted">Low Bandwidth Mode is on, so video loading is paused.</span>
                  <button type="button" className="secondary" onClick={toggleLowBandwidth}>
                    Load Video
                  </button>
                </div>
              ) : videoSrc && selectedMeeting ? (
                <VideoPlayer
                  src={videoSrc}
                  meetingTitle={selectedMeeting.title}
                  onDownload={
                    selectedMeeting.has_video ? () => void api.downloadVideo(selectedMeeting.id) : undefined
                  }
                  onTimeUpdate={(time) => handlePlaybackTimeChange(time, 'video')}
                  onPlayStateChange={(isPlaying) => handlePlaybackPlayStateChange(isPlaying, 'video')}
                  syncTime={playbackTime}
                  syncPlaying={playbackPlaying}
                  syncSource={playbackSource}
                />
              ) : null
            ) : null}
            <LiveTranscript
              segments={segments}
              meetingId={selectedMeetingId}
              playbackTime={playbackTime}
              playbackPlaying={playbackPlaying}
              playbackSource={playbackSource}
              onPlaybackTimeChange={handlePlaybackTimeChange}
              onPlaybackPlayStateChange={handlePlaybackPlayStateChange}
            />
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
