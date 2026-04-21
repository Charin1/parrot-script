import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, formatApiError } from './api/client'
import { LiveTranscript } from './components/LiveTranscript'
import { MeetingControls } from './components/MeetingControls'
import { PastMeetingsDashboard } from './components/PastMeetingsDashboard'
import { RuntimeStatusPanel } from './components/RuntimeStatusPanel'
import { SearchBar } from './components/SearchBar'
import { InsightsSidebar } from './components/InsightsSidebar'
import { ThemeSelector } from './components/ThemeSelector'
import { useMeetings } from './hooks/useMeetings'
import { useLowBandwidth } from './hooks/useLowBandwidth'
import { PlusIcon, MenuIcon } from './components/icons'
import { useAuth } from './hooks/useAuth'
import { useTheme } from './hooks/useTheme'
import { useWebSocket, type StreamConnectionState } from './hooks/useWebSocket'
import type { MeetingStatus, PlaybackSyncSource, Segment, SummaryProgress, TranscriptProgress } from './types/models'
import { VideoPlayer } from './components/VideoPlayer'
import { UploadMeetingView } from './components/UploadMeetingView'

function App() {
  const [busy, setBusy] = useState(false)
  const [appError, setAppError] = useState<string | null>(null)
  const [appNotice, setAppNotice] = useState<string | null>(null)
  const [newTitle, setNewTitle] = useState('Weekly Sync')
  const [viewMode, setViewMode] = useState<'workspace' | 'dashboard' | 'upload' | 'config'>('workspace')
  const [dashboardTab, setDashboardTab] = useState<'search' | 'list'>('list')
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [videoExpanded, setVideoExpanded] = useState(false)
  const [playbackTime, setPlaybackTime] = useState(0)
  const [playbackPlaying, setPlaybackPlaying] = useState(false)
  const [playbackSource, setPlaybackSource] = useState<PlaybackSyncSource>('system')
  
  // WebSocket and Transcription State
  const [segments, setSegments] = useState<Segment[]>([])
  const [status, setStatus] = useState<MeetingStatus | undefined>(undefined)
  const [summaryProgress, setSummaryProgress] = useState<SummaryProgress | null>(null)
  const [summaryProcessing, setSummaryProcessing] = useState(false)
  const [transcriptProgress, setTranscriptProgress] = useState<TranscriptProgress | null>(null)
  const [connectionState, setConnectionState] = useState<StreamConnectionState>('idle')

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
  } = useMeetings(authReady, setAppError, setAppNotice, setBusy, setSegments, setSummaryProcessing)

  useWebSocket(
    selectedMeetingId,
    activeApiToken,
    setSegments,
    setStatus,
    setSummaryProgress,
    setTranscriptProgress,
    setConnectionState,
    (data) => {
      setSummaryProcessing(false)
      setAppError(null)
      setSummary(data)
    },
    (payload) => {
      // Only surface the error if it applies to the active meeting.
      if (payload.meeting_id && payload.meeting_id !== selectedMeetingId) {
        return
      }
      setSummaryProcessing(false)
      setAppError(payload.error ? `Summary generation failed: ${payload.error}` : 'Summary generation failed')
    }
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
    // Immediately clear state when switching meetings to prevent ghosting
    setSummary(null)
    setSummaryProcessing(false)
    setSegments([])
    setSummaryProgress(null)
    setTranscriptProgress(null)

    if (!authReady || !selectedMeetingId) {
      return
    }

    const controller = new AbortController()
    setSummaryProcessing(false)

    void api
      .getTranscript(selectedMeetingId, controller.signal)
      .then((items) => {
        if (!controller.signal.aborted) {
          console.info(`[api] transcript loaded meeting=${selectedMeetingId} segments=${items.length}`)
          setSegments(items)
        }
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          console.warn(`[api] transcript load failed meeting=${selectedMeetingId}`, error)
          setAppError(formatApiError(error))
        }
      })

    void api
      .getSummary(selectedMeetingId, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          if ((data as any).status === 'processing') {
            setSummary(null)
            setSummaryProcessing(true)
            return
          }
          setSummaryProcessing(false)
          setSummary(data)
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setSummary(null)
          setSummaryProcessing(false)
        }
      })

    return () => controller.abort()
  }, [authReady, selectedMeetingId, setSegments, setSummary, setSummaryProcessing, setSummaryProgress, setTranscriptProgress])

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
    <div className="app-wrapper">
      <header className="global-top-bar">
        <div className={`sidebar-header-proxy ${sidebarOpen ? '' : 'collapsed'}`}>
          <button type="button" className="icon-btn header-menu-btn" onClick={() => setSidebarOpen(!sidebarOpen)}>
            <MenuIcon width={24} height={24} />
          </button>
        </div>
        <div className="brand-top-row">
          <img className="brand-logo" src="/parrot-script-logo.svg" alt="Parrot Script logo" />
          <div className="brand-copy">
            <h1>Parrot Script</h1>
            <span className="brand-kicker">Local-first meeting intelligence</span>
          </div>
        </div>
      </header>

      <div className={`app-shell ${sidebarOpen ? 'sidebar-open' : 'sidebar-closed'}`}>
        {sidebarOpen && (
          <aside className="left-panel">
            <div className="panel nav-panel">
            <button
              type="button"
              className={`nav-btn ${viewMode === 'workspace' ? '' : 'secondary'}`}
              onClick={() => setViewMode('workspace')}
            >
              Current Meeting
            </button>
	            <button
	              type="button"
	              className={`nav-btn ${viewMode === 'dashboard' ? '' : 'secondary'}`}
	              onClick={() => setViewMode('dashboard')}
	            >
	              Past Dashboard
	            </button>
	            <button
	              type="button"
	              className={`nav-btn ${viewMode === 'upload' ? '' : 'secondary'}`}
	              onClick={() => setViewMode('upload')}
	            >
	              Upload Meeting
	            </button>
	            <button
	              type="button"
	              className={`nav-btn ${viewMode === 'config' ? '' : 'secondary'}`}
	              onClick={() => setViewMode('config')}
	            >
              Configuration
            </button>
          </div>

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

        </aside>
      )}

        <main className="right-panel">
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

          {viewMode === 'config' ? (
            <div className="config-view">
              <div className="panel appearance-panel">
                <div className="panel-header">
                  <h3>Appearance</h3>
                </div>
                <p className="muted" style={{ marginBottom: '0.5rem' }}>
                  Active theme: <strong>{resolved}</strong> ({mode === 'system' ? 'auto' : mode})
                </p>
                <ThemeSelector mode={mode} onChange={setMode} />
              </div>

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
            </div>
          ) : (
            <div className={`workspace-layout ${viewMode !== 'workspace' || !selectedMeetingId ? 'no-sidebar' : ''}`}>
              <div className="workspace-main">
                  {viewMode === 'dashboard' && (
                    <div className="dashboard-panel">
                      <div className="panel nav-panel" style={{ flexDirection: 'row', gap: '0.8rem', padding: '0.5rem 1rem' }}>
                        <button
                          type="button"
                          className={`nav-btn ${dashboardTab === 'search' ? '' : 'secondary'}`}
                          onClick={() => setDashboardTab('search')}
                        >
                          Semantic Search
                        </button>
                        <button
                          type="button"
                          className={`nav-btn ${dashboardTab === 'list' ? '' : 'secondary'}`}
                          onClick={() => setDashboardTab('list')}
                        >
                          Past Meetings
                        </button>
                      </div>

                      {dashboardTab === 'search' ? (
                        <SearchBar
                          disabled={!authReady}
                          onSearch={(query, signal) => api.search(query, 10, signal)}
                          onSelectMeeting={(meetingId) => {
                            setAppError(null)
                            setSelectedMeetingId(meetingId)
                            setViewMode('workspace')
                          }}
                        />
                      ) : (
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
                      )}
                    </div>
                  )}

                  {viewMode === 'workspace' && (
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
                    </>
                  )}

	                {viewMode === 'upload' && (
	                  <UploadMeetingView
	                    disabled={!authReady || busy}
	                    activeMeetingId={selectedMeetingId}
	                    transcriptProgress={transcriptProgress}
	                    onImported={(meetingId) => {
	                      setSelectedMeetingId(meetingId)
	                      void refreshMeetings()
	                    }}
	                    onSelectMeeting={(meetingId) => {
	                      setSelectedMeetingId(meetingId)
	                      setViewMode('workspace')
	                    }}
	                  />
	                )}
	              </div>
              
              {viewMode === 'workspace' && selectedMeetingId && (
                <InsightsSidebar
                  summary={summary}
                  onGenerate={() => void generateSummary()}
                  busy={busy || summaryProcessing}
                  disabled={!authReady}
                  error={appError}
                  progress={summaryProgress}
                />
              )}
            </div>
          )}
        </main>
      </div>
    </div>
  )
}


export default App
