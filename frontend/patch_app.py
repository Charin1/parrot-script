import re

with open("src/App.tsx", "r") as f:
    content = f.read()

# 1. Update imports
content = content.replace(
    "import { PlusIcon } from './components/icons'",
    "import { PlusIcon, MenuIcon } from './components/icons'"
)

# 2. Update state
content = content.replace(
    "const [viewMode, setViewMode] = useState<'workspace' | 'dashboard'>('workspace')",
    "const [viewMode, setViewMode] = useState<'workspace' | 'dashboard' | 'config'>('workspace')\n  const [sidebarOpen, setSidebarOpen] = useState(true)"
)


old_return_statement = content[content.find("  return ("):content.find("export default App")].strip()

# Note, old_return_statement contains the outer `}` of `function App() {`
# e.g.
#   )
# }

new_return_statement = """  return (
    <div className={`app-shell ${sidebarOpen ? 'sidebar-open' : 'sidebar-closed'}`}>
      {sidebarOpen && (
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
      )}

      <main className="right-panel">
        <div className="top-bar">
          <button type="button" className="secondary icon-btn" onClick={() => setSidebarOpen(!sidebarOpen)}>
            <MenuIcon width={20} height={20} />
          </button>
          <h2>
            {viewMode === 'workspace' ? 'Live Workspace' : viewMode === 'dashboard' ? 'Past Dashboard' : 'Configuration'}
          </h2>
        </div>

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

        {viewMode === 'config' && (
          <div className="config-view">
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
        )}

        {viewMode === 'dashboard' && (
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
}"""

content = content.replace(old_return_statement, new_return_statement)

with open("src/App.tsx", "w") as f:
    f.write(content)

print("Patched App.tsx!")
