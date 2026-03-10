import type { BackendReachability } from '../hooks/useLocalRuntime'
import type { StreamConnectionState } from '../hooks/useWebSocket'

interface Props {
  browserOnline: boolean
  backendReachability: BackendReachability
  streamState: StreamConnectionState
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

export function RuntimeStatusPanel({ browserOnline, backendReachability, streamState }: Props) {
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
      </div>
    </div>
  )
}
