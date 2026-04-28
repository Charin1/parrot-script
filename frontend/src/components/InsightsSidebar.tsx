import { useEffect, useState, useRef } from 'react'
import type { Summary, SummaryProgress } from '../types/models'
import { SparklesIcon, CheckCircleIcon, ListIcon, ClockIcon, SendIcon } from './icons'
import { LiveParrotAgent } from './LiveParrotAgent'

interface InsightsSidebarProps {
  meetingId: string | null
  summary: Summary | null
  onGenerate: () => void
  busy: boolean
  disabled: boolean
  error?: string | null
  progress?: SummaryProgress | null
}

export function InsightsSidebar({ meetingId, summary, onGenerate, busy, disabled, error, progress }: InsightsSidebarProps) {
  const [activeTab, setActiveTab] = useState<'summary' | 'agent'>('summary')
  const [estimatedSecondsRemaining, setEstimatedSecondsRemaining] = useState<number | null>(null)
  const startTimeRef = useRef<number | null>(null)
  
  const parseJSON = (jsonStr: string | undefined): any[] => {
    if (!jsonStr) return []
    try {
      return JSON.parse(jsonStr)
    } catch (e) {
      return []
    }
  }

  const renderItem = (item: any) => {
    if (typeof item === 'string') return item
    if (typeof item === 'object' && item !== null) {
      const val = item.item || item.task || item.decision || JSON.stringify(item)
      const attr = item.attributed_to || item.owner
      return attr ? `${val} (Owner: ${attr})` : val
    }
    return String(item)
  }

  useEffect(() => {
    if (!progress) {
      startTimeRef.current = null
      setEstimatedSecondsRemaining(null)
      return
    }
    if (progress.current === 0) {
      startTimeRef.current = Date.now()
      return
    }
    if (startTimeRef.current && progress.current > 0) {
      const elapsed = (Date.now() - startTimeRef.current) / 1000
      const secondsPerChunk = elapsed / progress.current
      const remainingChunks = progress.total - progress.current
      setEstimatedSecondsRemaining(Math.round(remainingChunks * secondsPerChunk))
    }
  }, [progress?.current, progress?.total])

  const formatTime = (seconds: number): string => {
    if (seconds < 60) return `${seconds}s`
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins}m ${secs}s`
  }

  const actionItems = parseJSON(summary?.action_items)
  const decisions = parseJSON(summary?.decisions)
  const hasStructuredData = (summary?.summary || actionItems.length > 0 || decisions.length > 0)

  return (
    <div className="workspace-side">
      <div className="panel-header">
        <h3>Meeting Insights</h3>
      </div>

      <div className="tab-switcher">
        <button 
          type="button" 
          className={`tab-btn ${activeTab === 'summary' ? 'active' : 'secondary'}`} 
          onClick={() => setActiveTab('summary')}
        >
          <SparklesIcon width={14} height={14} />
          <span>Summary</span>
        </button>
        <button 
          type="button" 
          className={`tab-btn ${activeTab === 'agent' ? 'active' : 'secondary'}`} 
          onClick={() => setActiveTab('agent')}
        >
          <SendIcon width={14} height={14} />
          <span>Live Parrot</span>
        </button>
      </div>

      {activeTab === 'summary' && (
        <div className="summary-tab-content">
          <button 
            type="button" 
            className={summary ? "secondary" : ""} 
            onClick={() => onGenerate()} 
            disabled={busy || disabled}
            style={{ width: '100%', marginBottom: '1rem' }}
          >
            <SparklesIcon className="btn-icon" width={18} height={18} />
            <span>{summary ? 'Regenerate Insights' : 'Generate Insights'}</span>
          </button>

          {error && (
            <div className="panel error-banner" style={{ margin: '0 0 1rem 0', borderRadius: '8px', fontSize: '0.85rem' }}>
              <strong>Error:</strong> {error}
            </div>
          )}

          {!summary && !busy && (
            <div className="muted" style={{ textAlign: 'center', padding: '2rem 1rem' }}>
              <p>No insights generated yet.</p>
              <p style={{ fontSize: '0.8rem' }}>Click the button above to analyze the transcript.</p>
            </div>
          )}

          {(busy || progress) && (
            <div className="muted" style={{ textAlign: 'center', padding: '1rem 0', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div className="loading-pulse">
                <SparklesIcon width={32} height={32} style={{ color: 'var(--accent)' }} />
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                <p style={{ fontWeight: 500, color: 'var(--text-primary)' }}>
                  {progress ? `Analyzing Meeting...` : 'Starting AI analysis...'}
                </p>
                {progress && <p style={{ fontSize: '0.8rem' }}>Chunk {progress.current} of {progress.total}</p>}
              </div>
              {progress && (
                <div style={{ width: '100%', padding: '0 1rem' }}>
                  <div className="progress-bar-bg">
                    <div className="progress-bar-fill" style={{ width: `${(progress.current / progress.total) * 100}%` }} />
                  </div>
                  {estimatedSecondsRemaining !== null && (
                    <div className="progress-est">
                      <ClockIcon width={14} height={14} />
                      <span>Est. {formatTime(estimatedSecondsRemaining)} remaining</span>
                    </div>
                  )}
                </div>
              )}
              {!progress && <div className="loading-spinner" style={{ margin: '0 auto' }}></div>}
            </div>
          )}

          {summary && !busy && !progress && (
            <>
              <div className="insight-card">
                <h4><SparklesIcon width={16} height={16} />Executive Summary</h4>
                <div style={{ fontSize: '0.95rem', lineHeight: '1.5' }}>{summary.summary || summary.content}</div>
              </div>
              {(actionItems.length > 0 || !hasStructuredData) && (
                <div className="insight-card">
                  <h4><CheckCircleIcon width={16} height={16} />Action Items</h4>
                  {actionItems.length > 0 ? (
                    <ul className="action-items-list">
                      {actionItems.map((item, i) => (
                        <li key={i} className="action-item-row">
                          <div className="action-item-check" />
                          <span>{renderItem(item)}</span>
                        </li>
                      ))}
                    </ul>
                  ) : <div className="muted" style={{ fontSize: '0.85rem' }}>No specific actions identified.</div>}
                </div>
              )}
              {(decisions.length > 0 || !hasStructuredData) && (
                <div className="insight-card">
                  <h4><ListIcon width={16} height={16} />Key Decisions</h4>
                  {decisions.length > 0 ? (
                    <ul className="decisions-list">
                      {decisions.map((item, i) => (
                        <li key={i} className="decision-row">
                          <div className="decision-bullet" />
                          <span>{renderItem(item)}</span>
                        </li>
                      ))}
                    </ul>
                  ) : <div className="muted" style={{ fontSize: '0.85rem' }}>No formal decisions recorded.</div>}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {activeTab === 'agent' && meetingId && (
        <LiveParrotAgent meetingId={meetingId} disabled={disabled} />
      )}
    </div>
  )
}
