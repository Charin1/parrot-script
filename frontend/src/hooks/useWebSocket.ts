import { useEffect, useMemo, useRef } from 'react'
import { getApiToken, getBackendOrigin } from '../api/client'
import type { MeetingStatus, Segment, Summary, SummaryProgress, TranscriptProgress } from '../types/models'

const MAX_SEGMENTS = 2000
const UNAUTHORIZED_CLOSE_CODE = 4401

export type StreamConnectionState =
  | 'idle'
  | 'connecting'
  | 'connected'
  | 'reconnecting'
  | 'unauthorized'
  | 'disconnected'

function segmentKey(segment: Segment): string {
  return segment.id ?? segment.segment_id ?? `${segment.start_time}:${segment.end_time}:${segment.text}`
}

function appendSegment(prev: Segment[], incoming: Segment): Segment[] {
  const key = segmentKey(incoming)
  const existingIndex = prev.findIndex((segment) => segmentKey(segment) === key)
  
  if (existingIndex >= 0) {
    // Update existing segment (required for dynamic speaker attribution mapping)
    const next = [...prev]
    next[existingIndex] = incoming
    return next
  }

  const next = [...prev, incoming]

  // Sort by start_time so parallel-processed chunks always appear in chronological order
  next.sort((a, b) => a.start_time - b.start_time)

  if (next.length <= MAX_SEGMENTS) {
    return next
  }
  return next.slice(next.length - MAX_SEGMENTS)
}

export function useWebSocket(
  meetingId: string | null, 
  apiToken: string,
  setSegments: (val: Segment[] | ((prev: Segment[]) => Segment[])) => void,
  setStatus: (val: MeetingStatus | undefined) => void,
  setSummaryProgress: (val: SummaryProgress | null) => void,
  setTranscriptProgress: (val: TranscriptProgress | null) => void,
  setConnectionState: (val: StreamConnectionState) => void,
  onSummaryCompleted?: (summary: Summary) => void,
  onSummaryFailed?: (payload: { meeting_id?: string; error?: string }) => void
) {
  const onSummaryCompletedRef = useRef<typeof onSummaryCompleted>(undefined)
  const onSummaryFailedRef = useRef<typeof onSummaryFailed>(undefined)
  const transcriptMessageCountRef = useRef(0)

  useEffect(() => {
    onSummaryCompletedRef.current = onSummaryCompleted
  }, [onSummaryCompleted])

  useEffect(() => {
    onSummaryFailedRef.current = onSummaryFailed
  }, [onSummaryFailed])

  const wsUrl = useMemo(() => {
    if (!meetingId) {
      return null
    }

    const backendOrigin = new URL(getBackendOrigin())
    const protocol = backendOrigin.protocol === 'https:' ? 'wss:' : 'ws:'
    const token = apiToken.trim() || getApiToken()
    const socketUrl = new URL(`/ws/meetings/${meetingId}`, `${protocol}//${backendOrigin.host}`)
    if (token) {
      socketUrl.searchParams.set('token', token)
    }
    return socketUrl.toString()
  }, [meetingId, apiToken])

  useEffect(() => {
    if (!wsUrl) {
      setSegments([])
      setStatus(undefined)
      setSummaryProgress(null)
      setTranscriptProgress(null)
      setConnectionState('idle')
      transcriptMessageCountRef.current = 0
      return
    }

    // Reset state when switching to a new meeting URL
    setSegments([])
    setStatus(undefined)
    setSummaryProgress(null)
    setTranscriptProgress(null)
    transcriptMessageCountRef.current = 0

    let cancelled = false
    let activeSocket: WebSocket | null = null
    let reconnectTimer: number | null = null
    let retryAttempt = 0

    const clearReconnectTimer = () => {
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer)
        reconnectTimer = null
      }
    }

    const scheduleReconnect = (delay: number) => {
      clearReconnectTimer()
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null
        connect()
      }, delay)
    }

    const connect = () => {
      if (cancelled) {
        return
      }

      if (activeSocket && activeSocket.readyState < WebSocket.CLOSING) {
        return
      }

      setConnectionState(retryAttempt === 0 ? 'connecting' : 'reconnecting')

      const currentSocket = new WebSocket(wsUrl)
      activeSocket = currentSocket
      let heartbeatTimer: number | null = null

      const clearHeartbeat = () => {
        if (heartbeatTimer !== null) {
          window.clearInterval(heartbeatTimer)
          heartbeatTimer = null
        }
      }

      currentSocket.onopen = () => {
        if (cancelled || activeSocket !== currentSocket) {
          return
        }

        retryAttempt = 0
        setConnectionState('connected')
        heartbeatTimer = window.setInterval(() => {
          if (currentSocket.readyState === WebSocket.OPEN) {
            currentSocket.send('ping')
          }
        }, 15000)
      }

      currentSocket.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data) as { type?: string; data?: unknown }
          if (msg.type === 'transcript' && msg.data) {
            setSegments((prev) => appendSegment(prev, msg.data as Segment))
            transcriptMessageCountRef.current += 1
            const n = transcriptMessageCountRef.current
            if (n === 1 || n % 50 === 0) {
              const seg = msg.data as any
              const start = typeof seg?.start_time === 'number' ? seg.start_time.toFixed(1) : '?'
              const end = typeof seg?.end_time === 'number' ? seg.end_time.toFixed(1) : '?'
              console.info(`[ws] transcript meeting=${meetingId ?? ''} segments=${n} t=${start}-${end}`)
            }
          } else if (msg.type === 'status' && msg.data) {
            const status = msg.data as MeetingStatus
            setStatus(status)
            if (!status.recording) {
              setTranscriptProgress(null)
            }
          } else if (msg.type === 'summary_progress' && msg.data) {
            const progress = msg.data as SummaryProgress
            setSummaryProgress(progress)
            console.info(`[ws] summary_progress meeting=${progress.meeting_id} ${progress.current}/${progress.total}`)
          } else if (msg.type === 'transcript_progress' && msg.data) {
            const progress = msg.data as TranscriptProgress
            setTranscriptProgress(progress)
            if (progress.current === 1 || progress.current % 20 === 0 || progress.current === progress.total) {
              console.info(`[ws] transcript_progress meeting=${progress.meeting_id} ${progress.current}/${progress.total}`)
            }
          } else if (msg.type === 'summary_completed' && msg.data) {
            setSummaryProgress(null)
            if (onSummaryCompletedRef.current) {
              const completed = msg.data as any
              const meeting = typeof completed?.meeting_id === 'string' ? completed.meeting_id : meetingId ?? ''
              console.info(`[ws] summary_completed meeting=${meeting}`)
              onSummaryCompletedRef.current(msg.data as Summary)
            }
          } else if (msg.type === 'summary_failed') {
            setSummaryProgress(null)
            if (onSummaryFailedRef.current) {
              const payload = (msg.data ?? {}) as any
              const meeting = typeof payload?.meeting_id === 'string' ? payload.meeting_id : meetingId ?? ''
              const err = typeof payload?.error === 'string' ? payload.error : ''
              console.warn(`[ws] summary_failed meeting=${meeting}`, err)
              onSummaryFailedRef.current((msg.data ?? {}) as { meeting_id?: string; error?: string })
            }
          }
        } catch {
          // Drop malformed messages.
        }
      }

      currentSocket.onclose = (event) => {
        clearHeartbeat()

        if (cancelled || activeSocket !== currentSocket) {
          return
        }

        activeSocket = null
        if (event.code === UNAUTHORIZED_CLOSE_CODE || event.code === 1008) {
          setConnectionState('unauthorized')
          return
        }

        retryAttempt += 1
        setConnectionState('reconnecting')
        
        // Exponential backoff with Full Jitter, capping at 60s
        const maxDelay = 60000
        const baseDelay = 1000
        const temp = Math.min(maxDelay, baseDelay * (2 ** Math.min(retryAttempt - 1, 10)))
        const jitteredDelay = Math.floor(Math.random() * temp)
        
        scheduleReconnect(jitteredDelay)
      }

      currentSocket.onerror = () => {
        if (activeSocket === currentSocket && currentSocket.readyState < WebSocket.CLOSING) {
          currentSocket.close()
        }
      }
    }

    const reconnectSoon = () => {
      if (cancelled) {
        return
      }
      if (activeSocket && activeSocket.readyState < WebSocket.CLOSING) {
        return
      }
      retryAttempt = 0
      scheduleReconnect(150)
    }

    const onBrowserOnline = () => reconnectSoon()
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        reconnectSoon()
      }
    }

    window.addEventListener('online', onBrowserOnline)
    document.addEventListener('visibilitychange', onVisibilityChange)
    connect()

    return () => {
      cancelled = true
      clearReconnectTimer()
      window.removeEventListener('online', onBrowserOnline)
      document.removeEventListener('visibilitychange', onVisibilityChange)
      if (activeSocket && activeSocket.readyState < WebSocket.CLOSING) {
        activeSocket.close()
      }
      activeSocket = null
      setConnectionState('disconnected')
    }
  }, [wsUrl])
}
