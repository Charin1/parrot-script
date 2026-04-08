import type { BackendReachability } from '../hooks/useLocalRuntime'
import type { StreamConnectionState } from '../hooks/useWebSocket'

interface Props {
  browserOnline: boolean
  backendReachability: BackendReachability
  streamState: StreamConnectionState
  lowBandwidth: boolean
  onToggleLowBandwidth: () => void
}

function backendLabel(state: BackendReachability): string {
  if (state === 'reachable') {
    return 'Local API ready'
  }
  if (state === 'unreachable') {
    return 'Local API unreachable'
  }
  return 'Checking local API'
}

function backendBadge(state: BackendReachability): string {
  if (state === 'reachable') {
    return 'badge-ok'
  }
  if (state === 'unreachable') {
    return 'badge-failed'
  }
  return 'badge-idle'
}

function streamLabel(state: StreamConnectionState): string {
  switch (state) {
    case 'connected':
      return 'Live stream linked'
    case 'connecting':
      return 'Connecting stream'
    case 'reconnecting':
      return 'Reconnecting stream'
    case 'unauthorized':
      return 'Stream auth failed'
    case 'disconnected':
      return 'Stream disconnected'
    default:
      return 'Stream idle'
  }
}

function streamBadge(state: StreamConnectionState): string {
  if (state === 'connected') {
    return 'badge-ok'
  }
  if (state === 'unauthorized' || state === 'disconnected') {
    return 'badge-failed'
  }
  return 'badge-idle'
}

export function RuntimeStatusPanel({ browserOnline, backendReachability, streamState, lowBandwidth, onToggleLowBandwidth }: Props) {
  return (
    <div className="panel runtime-panel">
      <div className="panel-header">
        <h3>Local Runtime</h3>
        <span className={`badge ${browserOnline ? 'badge-ok' : 'badge-failed'}`}>
          {browserOnline ? 'Browser Online' : 'Browser Offline'}
        </span>
      </div>
      <p className="muted">
        Core runtime stays on loopback. Internet is not required after setup if the backend and
        Ollama are running locally.
      </p>
      <div className="runtime-grid">
        <article className="runtime-card">
          <span className={`badge ${backendBadge(backendReachability)}`}>
            {backendLabel(backendReachability)}
          </span>
          <p className="muted">
            Expected bind: <code>127.0.0.1:8000</code>
          </p>
        </article>
        <article className="runtime-card">
          <span className={`badge ${streamBadge(streamState)}`}>{streamLabel(streamState)}</span>
          <p className="muted">Socket retries back off automatically after disconnects.</p>
        </article>
        <article className="runtime-card">
          <span className={`badge ${lowBandwidth ? 'badge-idle' : 'badge-ok'}`}>
            {lowBandwidth ? 'Low Bandwidth' : 'Full Quality'}
          </span>
          <p className="muted">
            {lowBandwidth
              ? 'Audio player and video preload disabled to save bandwidth.'
              : 'All media features active. Enable low-bandwidth mode on slow networks.'}
          </p>
          <button
            type="button"
            className="secondary"
            onClick={onToggleLowBandwidth}
            style={{ marginTop: '0.4rem', fontSize: '0.75rem', padding: '0.25rem 0.6rem' }}
          >
            {lowBandwidth ? 'Disable Low Bandwidth' : 'Enable Low Bandwidth'}
          </button>
        </article>
      </div>
    </div>
  )
}
