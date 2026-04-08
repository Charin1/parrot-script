import { useEffect, useMemo, useRef, useState } from 'react'
import type { PlaybackSyncSource, Segment } from '../types/models'
import { api } from '../api/client'
import { EditIcon, DownloadIcon, BookmarkIcon, SyncIcon } from './icons'
import { AudioPlayer } from './AudioPlayer'

interface Props {
  segments: Segment[]
  meetingId: string | null
  playbackTime: number
  playbackPlaying: boolean
  playbackSource: PlaybackSyncSource
  onPlaybackTimeChange: (time: number, source: PlaybackSyncSource) => void
  onPlaybackPlayStateChange: (isPlaying: boolean, source: PlaybackSyncSource) => void
}

function colorForSpeaker(speaker: string): string {
  const palette = ['#0b7285', '#c92a2a', '#2f9e44', '#5f3dc4', '#e67700', '#087f5b']
  const value = Array.from(speaker).reduce((sum, ch) => sum + ch.charCodeAt(0), 0)
  return palette[value % palette.length]
}

function latestStartedSegmentIndex(segments: Array<{ start_time: number }>, currentTime: number): number {
  if (currentTime <= 0) {
    return -1
  }

  for (let index = segments.length - 1; index >= 0; index -= 1) {
    if (currentTime >= segments[index].start_time) {
      return index
    }
  }

  return -1
}

export function LiveTranscript({
  segments,
  meetingId,
  playbackTime,
  playbackPlaying,
  playbackSource,
  onPlaybackTimeChange,
  onPlaybackPlayStateChange,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [editingSegmentKey, setEditingSegmentKey] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')
  const [editingTextKey, setEditingTextKey] = useState<string | null>(null)
  const [editTextValue, setEditTextValue] = useState('')
  const [optimisticNames, setOptimisticNames] = useState<Record<string, string>>({})
  const [optimisticBookmarks, setOptimisticBookmarks] = useState<Record<string, boolean>>({})
  const [optimisticTexts, setOptimisticTexts] = useState<Record<string, string>>({})
  const [autoScroll, setAutoScroll] = useState(true)

  const audioSrc = useMemo(
    () => meetingId ? api.getAudioUrl(meetingId) : '',
    [meetingId]
  )

  useEffect(() => {
    if (!containerRef.current) return
    if (autoScroll && meetingId) {
      if (playbackTime === 0) {
        containerRef.current.scrollTop = containerRef.current.scrollHeight
      }
    }
  }, [segments, autoScroll, meetingId, playbackTime])

  useEffect(() => {
    setOptimisticNames({})
    setOptimisticBookmarks({})
    setOptimisticTexts({})
    setEditingSegmentKey(null)
    setEditingTextKey(null)
    setAutoScroll(true)
  }, [meetingId])

  useEffect(() => {
    if (!segments || segments.length === 0) return

    let changedNames = false
    const newNames = { ...optimisticNames }
    let changedTexts = false
    const newTexts = { ...optimisticTexts }
    let changedBookmarks = false
    const newBookmarks = { ...optimisticBookmarks }

    for (const seg of segments) {
      if (seg.speaker && newNames[seg.speaker] === seg.display_name) {
        delete newNames[seg.speaker]
        changedNames = true
      }
      const segId = seg.id ?? seg.segment_id ?? ''
      if (segId) {
        if (newTexts[segId] === seg.text) {
          delete newTexts[segId]
          changedTexts = true
        }
        if (newBookmarks[segId] === seg.is_bookmarked) {
          delete newBookmarks[segId]
          changedBookmarks = true
        }
      }
    }

    if (changedNames) setOptimisticNames(newNames)
    if (changedTexts) setOptimisticTexts(newTexts)
    if (changedBookmarks) setOptimisticBookmarks(newBookmarks)
  }, [segments])

  const grouped = useMemo(() => {
    return segments.map((segment) => ({
      ...segment,
      key: segment.id ?? segment.segment_id ?? `${segment.start_time}-${segment.text}`,
      displaySpeaker: optimisticNames[segment.speaker] || segment.display_name || segment.speaker,
      displayText: optimisticTexts[segment.id ?? segment.segment_id ?? ''] || segment.text,
      isBookmarked: optimisticBookmarks[segment.id ?? segment.segment_id ?? ''] ?? segment.is_bookmarked ?? false
    }))
  }, [segments, optimisticNames, optimisticBookmarks, optimisticTexts])

  const scrollKeyForPlaybackTime = (playbackTime: number): string | null => {
    if (playbackTime <= 0) {
      return null
    }

    const segmentIndex = latestStartedSegmentIndex(grouped, playbackTime)
    if (segmentIndex >= 0) {
      return grouped[segmentIndex].key
    }

    return grouped[0]?.key ?? null
  }

  const scrollToSegment = (segmentKey: string | null, behavior: ScrollBehavior = 'smooth'): boolean => {
    const container = containerRef.current
    if (!container || !segmentKey) {
      return false
    }

    const element = document.getElementById(`segment-${segmentKey}`)
    if (!element) {
      return false
    }

    const containerRect = container.getBoundingClientRect()
    const elementRect = element.getBoundingClientRect()
    const nextTop =
      container.scrollTop +
      (elementRect.top - containerRect.top) -
      (container.clientHeight / 2) +
      (elementRect.height / 2)

    container.scrollTo({
      top: Math.max(0, nextTop),
      behavior,
    })
    return true
  }

  const scrollToPlaybackPosition = (playbackTime: number, behavior: ScrollBehavior = 'smooth'): boolean => {
    return scrollToSegment(scrollKeyForPlaybackTime(playbackTime), behavior)
  }

  const startEditing = (segmentKey: string, currentDisplay: string) => {
    setEditingSegmentKey(segmentKey)
    setEditValue(currentDisplay)
  }

  const OFFLINE_QUEUE_KEY = `parrot-offline-queue-${meetingId ?? 'none'}`

  const enqueueOffline = (mutation: object) => {
    try {
      const raw = localStorage.getItem(OFFLINE_QUEUE_KEY)
      const queue: object[] = raw ? JSON.parse(raw) : []
      queue.push(mutation)
      localStorage.setItem(OFFLINE_QUEUE_KEY, JSON.stringify(queue))
    } catch {
      // localStorage may be full or unavailable; silent no-op
    }
  }

  const flushOfflineQueue = async (mid: string) => {
    try {
      const raw = localStorage.getItem(OFFLINE_QUEUE_KEY)
      if (!raw) return
      const queue: Array<{ type: string; payload: Record<string, string> }> = JSON.parse(raw)
      localStorage.removeItem(OFFLINE_QUEUE_KEY)
      for (const item of queue) {
        if (item.type === 'speaker' && item.payload.label && item.payload.name) {
          await api.updateSpeakerName(mid, item.payload.label, item.payload.name)
        } else if (item.type === 'text' && item.payload.segmentId && item.payload.text) {
          await api.updateSegmentText(mid, item.payload.segmentId, item.payload.text)
        }
      }
    } catch {
      // If flush fails network is still down; queue will persist in localStorage for next reconnect
    }
  }

  // Flush any pending offline queue when the browser comes back online
  useEffect(() => {
    if (!meetingId) return
    const handleOnline = () => { void flushOfflineQueue(meetingId) }
    window.addEventListener('online', handleOnline)
    // Also try flushing immediately on mount in case we recovered mid-session
    if (navigator.onLine) { void flushOfflineQueue(meetingId) }
    return () => window.removeEventListener('online', handleOnline)
  }, [meetingId])

  const saveSpeakerName = async (meetingId: string, originalLabel: string) => {
    const newName = editValue.trim()
    setEditingSegmentKey(null)

    if (!newName || newName === (optimisticNames[originalLabel] || originalLabel)) return

    // Immediately update UI
    setOptimisticNames(prev => ({ ...prev, [originalLabel]: newName }))

    if (!navigator.onLine) {
      enqueueOffline({ type: 'speaker', payload: { label: originalLabel, name: newName } })
      return
    }

    try {
      await api.updateSpeakerName(meetingId, originalLabel, newName)
    } catch (err) {
      // On failure, persist to queue for retry rather than silently dropping
      enqueueOffline({ type: 'speaker', payload: { label: originalLabel, name: newName } })
      console.error('Failed to rename speaker, queued for retry:', err)
    }
  }

  const startEditingText = (segmentKey: string, currentText: string) => {
    setEditingTextKey(segmentKey)
    setEditTextValue(currentText)
  }

  const saveSegmentText = async (meetingId: string, segmentKey: string) => {
    const newText = editTextValue.trim()
    setEditingTextKey(null)

    if (!segmentKey || !newText) return

    setOptimisticTexts(prev => ({ ...prev, [segmentKey]: newText }))

    if (!navigator.onLine) {
      enqueueOffline({ type: 'text', payload: { segmentId: segmentKey, text: newText } })
      return
    }

    try {
      await api.updateSegmentText(meetingId, segmentKey, newText)
    } catch (err) {
      enqueueOffline({ type: 'text', payload: { segmentId: segmentKey, text: newText } })
      console.error('Failed to update text, queued for retry:', err)
    }
  }

  const seekPlayback = (time: number) => {
    onPlaybackTimeChange(time, 'transcript')
    onPlaybackPlayStateChange(true, 'transcript')
    setAutoScroll(true)
  }

  useEffect(() => {
    if (!containerRef.current) return
    if (!autoScroll) {
      return
    }

    if (playbackTime > 0) {
      scrollToPlaybackPosition(playbackTime)
      return
    }

    containerRef.current.scrollTo({ top: containerRef.current.scrollHeight, behavior: 'smooth' })
  }, [autoScroll, grouped, playbackTime, segments.length])

  const handleUserScroll = () => {
    if (autoScroll) setAutoScroll(false)
  }

  return (
    <div className="panel">
      <div className="panel-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <h3 style={{ margin: 0, minWidth: '150px' }}>Live Transcript</h3>

        {meetingId && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.8rem', flexWrap: 'wrap', flex: 1, justifyContent: 'flex-end' }}>
            {/* Custom Audio Player */}
            <AudioPlayer
              src={audioSrc}
              onTimeUpdate={(time) => onPlaybackTimeChange(time, 'audio')}
              onPlayStateChange={(isPlaying) => onPlaybackPlayStateChange(isPlaying, 'audio')}
              maxDuration={segments.length > 0 ? segments[segments.length - 1].end_time : 0}
              syncTime={playbackTime}
              syncPlaying={playbackPlaying}
              syncSource={playbackSource}
            />

            {/* Download Buttons */}
            {segments.length > 0 && (
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => void api.downloadAudio(meetingId)}
                  title="Download Audio"
                >
                  <DownloadIcon className="btn-icon" width={14} height={14} />
                  <span>WAV</span>
                </button>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => void api.downloadTranscript(meetingId, 'json')}
                  title="Download JSON"
                >
                  <DownloadIcon className="btn-icon" width={14} height={14} />
                  <span>JSON</span>
                </button>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => void api.downloadTranscript(meetingId, 'pdf')}
                  title="Download PDF"
                >
                  <DownloadIcon className="btn-icon" width={14} height={14} />
                  <span>PDF</span>
                </button>
              </div>
            )}
          </div>
        )}
      </div>
      <div
        ref={containerRef}
        className="transcript-scroll"
        onWheel={handleUserScroll}
        onTouchMove={handleUserScroll}
        style={{ position: 'relative' }}
      >
        {!autoScroll && segments.length > 0 && meetingId && (
          <div style={{ position: 'sticky', top: '10px', display: 'flex', justifyContent: 'center', zIndex: 100, pointerEvents: 'none' }}>
            <button
              className="sync-btn"
              style={{ pointerEvents: 'auto' }}
              onClick={() => {
                setAutoScroll(true)
                if (playbackTime > 0) {
                  scrollToPlaybackPosition(playbackTime)
                } else if (containerRef.current) {
                  containerRef.current.scrollTo({ top: containerRef.current.scrollHeight, behavior: 'smooth' })
                }
              }}
            >
              <SyncIcon width={14} height={14} /> Resume Sync
            </button>
          </div>
        )}

        {grouped.length === 0 ? <p className="muted">No transcript yet.</p> : null}
        {grouped.map((segment) => (
          <article key={segment.key} id={`segment-${segment.key}`} className="transcript-segment">
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
            {editingTextKey === segment.key ? (
              <textarea
                autoFocus
                className="segment-edit-input"
                value={editTextValue}
                onChange={e => setEditTextValue(e.target.value)}
                onBlur={() => saveSegmentText(segment.meeting_id, segment.key!)}
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    saveSegmentText(segment.meeting_id, segment.key!);
                  }
                  if (e.key === 'Escape') setEditingTextKey(null);
                }}
                style={{ width: '100%', minHeight: '60px', padding: '8px', marginTop: '4px', borderRadius: '4px', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-secondary)', color: 'var(--text-primary)', resize: 'vertical' }}
              />
            ) : (
              <p
                onDoubleClick={() => {
                  if (segment.key) startEditingText(segment.key, segment.displayText);
                }}
                onClick={() => seekPlayback(segment.start_time)}
                className="segment-text"
                style={{
                  cursor: 'pointer',
                  padding: '4px',
                  borderRadius: '4px',
                  backgroundColor: playbackTime >= segment.start_time && playbackTime <= segment.end_time ? 'var(--bg-active, rgba(238, 191, 165, 0.2))' : 'transparent',
                  transition: 'background-color 0.2s',
                  position: 'relative'
                }}
                title="Click to play from here. Double click to edit."
              >
                {segment.displayText}
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    if (segment.key) startEditingText(segment.key, segment.displayText);
                  }}
                  className="edit-text-btn"
                  title="Edit text"
                  style={{
                    position: 'absolute',
                    right: 0,
                    top: 0,
                    opacity: 0,
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    color: 'var(--text-muted)'
                  }}
                >
                  <EditIcon width={14} height={14} />
                </button>
              </p>
            )}
          </article>
        ))}
      </div>
    </div>
  )
}
