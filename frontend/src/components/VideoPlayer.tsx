import { useEffect, useRef, useState } from 'react'
import type { PlaybackSyncSource } from '../types/models'

interface VideoPlayerProps {
  src: string
  meetingTitle?: string
  onDownload?: () => void
  onTimeUpdate?: (time: number) => void
  onPlayStateChange?: (isPlaying: boolean) => void
  syncTime?: number
  syncPlaying?: boolean
  syncSource?: PlaybackSyncSource
}

export function VideoPlayer({
  src,
  meetingTitle,
  onDownload,
  onTimeUpdate,
  onPlayStateChange,
  syncTime,
  syncPlaying,
  syncSource = 'system',
}: VideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const suppressEventsUntilRef = useRef(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [duration, setDuration] = useState(0)
  const [currentTime, setCurrentTime] = useState(0)
  const [isMuted, setIsMuted] = useState(false)
  const [volume, setVolume] = useState(1)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [loading, setLoading] = useState(true)
  const containerRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    setIsPlaying(false)
    setCurrentTime(0)
    setDuration(0)
    setLoading(true)
  }, [src])

  const nowMs = () => (typeof performance !== 'undefined' ? performance.now() : Date.now())
  const suppressEventsFor = (ms: number) => {
    suppressEventsUntilRef.current = nowMs() + ms
  }
  const eventsSuppressed = () => nowMs() < suppressEventsUntilRef.current
  const shouldPublishPlayback = syncSource !== 'audio'

  useEffect(() => {
    const video = videoRef.current
    if (!video) return

    const onLoaded = () => { setDuration(video.duration); setLoading(false) }
    const onTimeUpdateEvent = () => {
      setCurrentTime(video.currentTime)
      if (!eventsSuppressed() && shouldPublishPlayback && onTimeUpdate) {
        onTimeUpdate(video.currentTime)
      }
    }
    const onPlay = () => {
      setIsPlaying(true)
      if (!eventsSuppressed() && shouldPublishPlayback && onPlayStateChange) {
        onPlayStateChange(true)
      }
    }
    const onPause = () => {
      setIsPlaying(false)
      if (!eventsSuppressed() && shouldPublishPlayback && onPlayStateChange) {
        onPlayStateChange(false)
      }
    }
    const onEnded = () => {
      setIsPlaying(false)
      if (!eventsSuppressed() && shouldPublishPlayback && onPlayStateChange) {
        onPlayStateChange(false)
      }
    }
    const onError = () => setLoading(false)

    if (video.readyState > 0) onLoaded()

    video.addEventListener('loadeddata', onLoaded)
    video.addEventListener('timeupdate', onTimeUpdateEvent)
    video.addEventListener('play', onPlay)
    video.addEventListener('pause', onPause)
    video.addEventListener('ended', onEnded)
    video.addEventListener('error', onError)

    return () => {
      video.removeEventListener('loadeddata', onLoaded)
      video.removeEventListener('timeupdate', onTimeUpdateEvent)
      video.removeEventListener('play', onPlay)
      video.removeEventListener('pause', onPause)
      video.removeEventListener('ended', onEnded)
      video.removeEventListener('error', onError)
    }
  }, [onPlayStateChange, onTimeUpdate, shouldPublishPlayback, src])

  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    if (syncSource === 'video') return
    if (syncTime === undefined || !Number.isFinite(syncTime) || syncTime < 0) return
    if (Math.abs(video.currentTime - syncTime) < 0.2) return

    suppressEventsFor(350)
    video.currentTime = syncTime
    setCurrentTime(syncTime)
  }, [syncSource, syncTime, src])

  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    if (syncSource === 'video' || syncPlaying === undefined) return

    if (syncPlaying) {
      if (!video.paused) return
      suppressEventsFor(500)
      video.play().catch(() => {})
      return
    }

    if (video.paused) return
    suppressEventsFor(350)
    video.pause()
  }, [syncPlaying, syncSource, src])

  useEffect(() => {
    const onFsChange = () => setIsFullscreen(!!document.fullscreenElement)
    document.addEventListener('fullscreenchange', onFsChange)
    return () => document.removeEventListener('fullscreenchange', onFsChange)
  }, [])

  const togglePlayPause = () => {
    if (!videoRef.current) return
    if (isPlaying) {
      videoRef.current.pause()
      if (onPlayStateChange) onPlayStateChange(false)
      if (onTimeUpdate) onTimeUpdate(videoRef.current.currentTime)
    } else {
      videoRef.current.play()
        .then(() => {
          if (onPlayStateChange) onPlayStateChange(true)
          if (onTimeUpdate) onTimeUpdate(videoRef.current?.currentTime ?? 0)
        })
        .catch(() => {})
    }
  }

  const toggleMute = () => {
    if (!videoRef.current) return
    const next = !isMuted
    videoRef.current.muted = next
    setIsMuted(next)
  }

  const handleVolumeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = parseFloat(e.target.value)
    if (!videoRef.current) return
    videoRef.current.volume = v
    videoRef.current.muted = v === 0
    setVolume(v)
    setIsMuted(v === 0)
  }

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const t = parseFloat(e.target.value)
    if (videoRef.current) {
      videoRef.current.currentTime = t
      setCurrentTime(t)
      if (onTimeUpdate) onTimeUpdate(t)
    }
  }

  const toggleFullscreen = () => {
    if (!containerRef.current) return
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen().catch(() => {})
    } else {
      document.exitFullscreen().catch(() => {})
    }
  }

  const formatTime = (t: number) => {
    if (isNaN(t) || !isFinite(t)) return '0:00'
    const m = Math.floor(t / 60)
    const s = Math.floor(t % 60)
    return `${m}:${s.toString().padStart(2, '0')}`
  }

  const effectiveDuration = duration && isFinite(duration) ? duration : 0
  const progress = effectiveDuration > 0 ? (currentTime / effectiveDuration) * 100 : 0

  if (!src) return null

  return (
    <div className="video-player-wrapper">
      <div className="video-player-header">
        <span className="video-player-label">🎬 Screen Recording</span>
        {meetingTitle ? <span className="muted">{meetingTitle}</span> : null}
        {onDownload ? (
          <button type="button" className="secondary video-download-btn" onClick={onDownload} title="Download MP4">
            ↓ Download MP4
          </button>
        ) : null}
      </div>

      <div ref={containerRef} className="video-player-container">
        <video
          ref={videoRef}
          src={src}
          preload="metadata"
          muted={isMuted}
          className="video-element"
          onClick={togglePlayPause}
        />

        {loading ? (
          <div className="video-loading-overlay">Loading…</div>
        ) : null}

        <div className="video-controls-bar">
          {/* Play / Pause */}
          <button
            type="button"
            className="play-btn"
            onClick={togglePlayPause}
            title={isPlaying ? 'Pause' : 'Play'}
          >
            {isPlaying ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="4" width="4" height="16" /><rect x="14" y="4" width="4" height="16" />
              </svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <polygon points="5,3 19,12 5,21" />
              </svg>
            )}
          </button>

          {/* Time */}
          <span className="time-display">{formatTime(currentTime)} / {formatTime(effectiveDuration)}</span>

          {/* Seek */}
          <input
            type="range"
            className="progress-slider"
            min={0}
            max={effectiveDuration || 100}
            step={0.1}
            value={currentTime}
            onChange={handleSeek}
            style={{ '--progress': `${progress}%` } as React.CSSProperties}
          />

          {/* Mute + Volume */}
          <button type="button" className="mute-btn" onClick={toggleMute} title={isMuted ? 'Unmute' : 'Mute'}>
            {isMuted || volume === 0 ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <path d="M16.5 12A4.5 4.5 0 0 0 14 7.97v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z"/>
              </svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3A4.5 4.5 0 0 0 14 7.97v8.05c1.48-.73 2.5-2.25 2.5-4.02z"/>
              </svg>
            )}
          </button>
          <input
            type="range"
            className="volume-slider"
            min={0}
            max={1}
            step={0.02}
            value={isMuted ? 0 : volume}
            onChange={handleVolumeChange}
            style={{ '--vol': `${(isMuted ? 0 : volume) * 100}%` } as React.CSSProperties}
          />

          {/* Fullscreen */}
          <button type="button" className="mute-btn" onClick={toggleFullscreen} title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}>
            {isFullscreen ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <path d="M5 16h3v3h2v-5H5v2zm3-8H5v2h5V5H8v3zm6 11h2v-3h3v-2h-5v5zm2-11V5h-2v5h5V8h-3z"/>
              </svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <path d="M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z"/>
              </svg>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
