import { useEffect, useState, useRef } from 'react'
import type { Summary, SummaryProgress } from '../types/models'
import { SparklesIcon, CheckCircleIcon, ListIcon, ClockIcon } from './icons'

interface InsightsSidebarProps {
  summary: Summary | null
  onGenerate: () => void
  busy: boolean
  disabled: boolean
  error?: string | null
  progress?: SummaryProgress | null
}

export function InsightsSidebar({ summary, onGenerate, busy, disabled, error, progress }: InsightsSidebarProps) {
  const [estimatedSecondsRemaining, setEstimatedSecondsRemaining] = useState<number | null>(null)
  const startTimeRef = useRef<number | null>(null)
  
  // Parse structured data safely
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
      // Handle {item, attributed_to} or similar
      const val = item.item || item.task || item.decision || JSON.stringify(item)
      const attr = item.attributed_to || item.owner
      return attr ? `${val} (Owner: ${attr})` : val
    }
    return String(item)
  }

  // Effect to handle time estimation
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

      {!summary && !busy && (
        <div className="muted" style={{ textAlign: 'center', padding: '2rem 1rem' }}>
          <p>No insights generated yet.</p>
          <p style={{ fontSize: '0.8rem' }}>Click the button above to analyze the transcript.</p>
        </div>
      )}
      {error && (
        <div className="panel error-banner" style={{ margin: '0 0 1rem 0', borderRadius: '8px', fontSize: '0.85rem' }}>
          <strong>Error:</strong> {error}
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
            {progress && (
              <p style={{ fontSize: '0.8rem' }}>
                Chunk {progress.current} of {progress.total}
              </p>
            )}
          </div>

          {progress && (
            <div style={{ width: '100%', padding: '0 1rem' }}>
              <div style={{ 
                width: '100%', 
                height: '8px', 
                backgroundColor: 'rgba(var(--accent-rgb), 0.1)', 
                borderRadius: '4px',
                overflow: 'hidden'
              }}>
                <div style={{ 
                  width: `${(progress.current / progress.total) * 100}%`, 
                  height: '100%', 
                  backgroundColor: 'var(--accent)',
                  transition: 'width 0.5s ease-out'
                }} />
              </div>
              
              {estimatedSecondsRemaining !== null && (
                <div style={{ 
                  display: 'flex', 
                  alignItems: 'center', 
                  justifyContent: 'center', 
                  gap: '0.4rem', 
                  marginTop: '0.8rem',
                  fontSize: '0.75rem',
                  color: 'var(--accent)'
                }}>
                  <ClockIcon width={14} height={14} />
                  <span>Est. {formatTime(estimatedSecondsRemaining)} remaining</span>
                </div>
              )}
            </div>
          )}

          {!progress && <div className="loading-spinner" style={{ margin: '0 auto' }}></div>}
          
          <div style={{ padding: '0 1rem' }}>
            <p style={{ fontSize: '0.7rem', opacity: 0.8, lineHeight: '1.4' }}>
              Your computer is processing the meeting sequentially to stay responsive. 
              {progress ? ' Almost there!' : ''}
            </p>
          </div>
        </div>
      )}

      {summary && !busy && !progress && (
        <>
          {/* Executive Summary Card */}
          <div className="insight-card">
            <h4>
              <SparklesIcon width={16} height={16} />
              Executive Summary
            </h4>
            <div style={{ fontSize: '0.95rem', lineHeight: '1.5' }}>
              {summary.summary || summary.content}
            </div>
          </div>

          {/* Action Items Card */}
          {(actionItems.length > 0 || !hasStructuredData) && (
            <div className="insight-card">
              <h4>
                <CheckCircleIcon width={16} height={16} />
                Action Items
              </h4>
              {actionItems.length > 0 ? (
                <ul className="action-items-list">
                  {actionItems.map((item, i) => (
                    <li key={i} className="action-item-row">
                      <div className="action-item-check" />
                      <span>{renderItem(item)}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="muted" style={{ fontSize: '0.85rem' }}>No specific actions identified.</div>
              )}
            </div>
          )}

          {/* Key Decisions Card */}
          {(decisions.length > 0 || !hasStructuredData) && (
            <div className="insight-card">
              <h4>
                <ListIcon width={16} height={16} />
                Key Decisions
              </h4>
              {decisions.length > 0 ? (
                <ul className="decisions-list">
                  {decisions.map((item, i) => (
                    <li key={i} className="decision-row">
                      <div className="decision-bullet" />
                      <span>{renderItem(item)}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="muted" style={{ fontSize: '0.85rem' }}>No formal decisions recorded.</div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
