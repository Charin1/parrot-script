import { useEffect, useMemo, useState } from 'react'
import { getApiToken, getBackendOrigin } from '../api/client'
import type { MeetingStatus, Segment } from '../types/models'

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
  if (prev.some((segment) => segmentKey(segment) === key)) {
    return prev
  }

  const next = [...prev, incoming]

  // Sort by start_time so parallel-processed chunks always appear in chronological order
  next.sort((a, b) => a.start_time - b.start_time)

  if (next.length <= MAX_SEGMENTS) {
    return next
  }
  return next.slice(next.length - MAX_SEGMENTS)
}

export function useWebSocket(meetingId: string | null, apiToken: string) {
  const [segments, setSegments] = useState<Segment[]>([])
  const [status, setStatus] = useState<MeetingStatus | undefined>(undefined)
  const [connectionState, setConnectionState] = useState<StreamConnectionState>('idle')

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
      setConnectionState('idle')
      return
    }

    // Reset state when switching to a new meeting URL
    setSegments([])
    setStatus(undefined)

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
          } else if (msg.type === 'status' && msg.data) {
            setStatus(msg.data as MeetingStatus)
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

  return { segments, status, setSegments, connectionState }
}
