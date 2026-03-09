import { useEffect, useMemo, useRef, useState } from 'react'
import type { Segment } from '../types/models'
import { api } from '../api/client'
import { EditIcon, DownloadIcon, BookmarkIcon } from './icons'

interface Props {
  segments: Segment[]
}

function colorForSpeaker(speaker: string): string {
  const palette = ['#0b7285', '#c92a2a', '#2f9e44', '#5f3dc4', '#e67700', '#087f5b']
  const value = Array.from(speaker).reduce((sum, ch) => sum + ch.charCodeAt(0), 0)
  return palette[value % palette.length]
}

export function LiveTranscript({ segments }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [editingSegmentKey, setEditingSegmentKey] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')
  const [optimisticNames, setOptimisticNames] = useState<Record<string, string>>({})
  const [optimisticBookmarks, setOptimisticBookmarks] = useState<Record<string, boolean>>({})

  useEffect(() => {
    if (!containerRef.current) return
    containerRef.current.scrollTop = containerRef.current.scrollHeight
  }, [segments])

  const currentMeetingId = segments.length > 0 ? segments[0].meeting_id : null;

  useEffect(() => {
    setOptimisticNames({});
    setOptimisticBookmarks({});
    setEditingSegmentKey(null);
  }, [currentMeetingId]);

  const grouped = useMemo(() => {
    return segments.map((segment) => ({
      ...segment,
      key: segment.id ?? segment.segment_id ?? `${segment.start_time}-${segment.text}`,
      displaySpeaker: optimisticNames[segment.speaker] || segment.display_name || segment.speaker,
      isBookmarked: optimisticBookmarks[segment.id ?? segment.segment_id ?? ''] ?? segment.is_bookmarked ?? false
    }))
  }, [segments, optimisticNames, optimisticBookmarks])

  const startEditing = (segmentKey: string, currentDisplay: string) => {
    setEditingSegmentKey(segmentKey)
    setEditValue(currentDisplay)
  }

  const saveSpeakerName = async (meetingId: string, originalLabel: string) => {
    const newName = editValue.trim()
    setEditingSegmentKey(null)

    if (!newName || newName === (optimisticNames[originalLabel] || originalLabel)) return

    // Immediately update UI
    setOptimisticNames(prev => ({ ...prev, [originalLabel]: newName }))

    try {
      await api.updateSpeakerName(meetingId, originalLabel, newName)
    } catch (err) {
      console.error('Failed to rename speaker:', err)
    }
  }

  return (
    <div className="panel">
      <div className="panel-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3>Live Transcript</h3>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          {segments.length > 0 && currentMeetingId && (
            <>
              <button
                type="button"
                className="secondary"
                onClick={() => void api.downloadTranscript(currentMeetingId, 'json')}
                title="Download JSON"
              >
                <DownloadIcon className="btn-icon" width={14} height={14} />
                <span>JSON</span>
              </button>
              <button
                type="button"
                className="secondary"
                onClick={() => void api.downloadTranscript(currentMeetingId, 'pdf')}
                title="Download PDF"
              >
                <DownloadIcon className="btn-icon" width={14} height={14} />
                <span>PDF</span>
              </button>
            </>
          )}
        </div>
      </div>
      <div ref={containerRef} className="transcript-scroll">
        {grouped.length === 0 ? <p className="muted">No transcript yet.</p> : null}
        {grouped.map((segment) => (
          <article key={segment.key} className="transcript-segment">
            <header>
              {editingSegmentKey === segment.key ? (
                <input
                  type="text"
                  autoFocus
                  className="speaker-edit-input"
                  value={editValue}
                  onChange={e => setEditValue(e.target.value)}
                  onBlur={() => saveSpeakerName(segment.meeting_id, segment.speaker)}
                  onKeyDown={e => {
                    if (e.key === 'Enter') saveSpeakerName(segment.meeting_id, segment.speaker)
                    if (e.key === 'Escape') setEditingSegmentKey(null)
                  }}
                  style={{ backgroundColor: colorForSpeaker(segment.speaker), color: '#fff', border: 'none', borderRadius: '12px', padding: '2px 8px', fontSize: '0.8rem', outline: 'none' }}
                />
              ) : (
                <button
                  type="button"
                  className="speaker-pill cursor-pointer flex-center gap-1"
                  style={{ backgroundColor: colorForSpeaker(segment.speaker), cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '4px', border: 'none', color: '#fff', position: 'relative', zIndex: 10 }}
                  onClick={(e) => {
                    e.preventDefault();
                    startEditing(segment.key, segment.displaySpeaker);
                  }}
                  title="Click to rename speaker"
                >
                  {segment.displaySpeaker}
                  <EditIcon width={12} height={12} style={{ opacity: 0.7, pointerEvents: 'none' }} />
                </button>
              )}
              <span className="time-pill">
                {segment.start_time.toFixed(1)}s - {segment.end_time.toFixed(1)}s
              </span>
              <button
                type="button"
                className="bookmark-btn"
                onClick={async () => {
                  if (!segment.key) return
                  const desiredState = !segment.isBookmarked
                  setOptimisticBookmarks(prev => ({ ...prev, [segment.key]: desiredState }))
                  try {
                    await api.toggleBookmark(segment.meeting_id, segment.key, desiredState)
                  } catch (err) {
                    console.error('Failed to toggle bookmark', err)
                    // Revert on failure
                    setOptimisticBookmarks(prev => ({ ...prev, [segment.key]: !desiredState }))
                  }
                }}
                title={segment.isBookmarked ? "Remove Bookmark" : "Bookmark this segment"}
                style={{
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  padding: '2px',
                  color: segment.isBookmarked ? '#eebfa5' : 'var(--text-muted)'
                }}
              >
                <BookmarkIcon width={16} height={16} filled={segment.isBookmarked} />
              </button>
            </header>
            <p>{segment.text}</p>
          </article>
        ))}
      </div>
    </div>
  )
}
