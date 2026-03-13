import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react'
import { PlayIcon, PauseIcon, VolumeUpIcon, VolumeMuteIcon } from './icons'

interface AudioPlayerProps {
    src: string
    onTimeUpdate?: (time: number) => void
    maxDuration?: number
}

export const AudioPlayer = forwardRef<HTMLAudioElement, AudioPlayerProps>(({ src, onTimeUpdate, maxDuration }, forwardedRef) => {
    const audioRef = useRef<HTMLAudioElement | null>(null)
    useImperativeHandle(forwardedRef, () => audioRef.current!)

    const [isPlaying, setIsPlaying] = useState(false)
    const [duration, setDuration] = useState(0)
    const [currentTime, setCurrentTime] = useState(0)
    const [isMuted, setIsMuted] = useState(false)
    const [volume, setVolume] = useState(1)
    const [loading, setLoading] = useState(true)

    // Reset state whenever the source changes
    useEffect(() => {
        setIsPlaying(false)
        setCurrentTime(0)
        setDuration(0)
        setLoading(true)
    }, [src])

    useEffect(() => {
        const audio = audioRef.current
        if (!audio) return

        const setAudioData = () => {
            setDuration(audio.duration)
            setCurrentTime(audio.currentTime)
            setLoading(false)
        }

        const setAudioTime = () => {
            setCurrentTime(audio.currentTime)
            if (onTimeUpdate) onTimeUpdate(audio.currentTime)
        }

        const onPlay = () => {
            setIsPlaying(true)
            if (onTimeUpdate) onTimeUpdate(audio.currentTime)
        }
        const onPause = () => setIsPlaying(false)
        const onEnded = () => setIsPlaying(false)
        const onError = () => setLoading(false) // Hide or handle error state

        if (audio.readyState > 0) {
            setAudioData()
        }

        audio.addEventListener('loadeddata', setAudioData)
        audio.addEventListener('timeupdate', setAudioTime)
        audio.addEventListener('play', onPlay)
        audio.addEventListener('pause', onPause)
        audio.addEventListener('ended', onEnded)
        audio.addEventListener('error', onError)

        return () => {
            audio.removeEventListener('loadeddata', setAudioData)
            audio.removeEventListener('timeupdate', setAudioTime)
            audio.removeEventListener('play', onPlay)
            audio.removeEventListener('pause', onPause)
            audio.removeEventListener('ended', onEnded)
            audio.removeEventListener('error', onError)
        }
    }, [onTimeUpdate, src])

    const togglePlayPause = () => {
        if (!audioRef.current) return
        if (isPlaying) {
            audioRef.current.pause()
        } else {
            audioRef.current.play().catch(() => { })
        }
    }

    const toggleMute = () => {
        if (!audioRef.current) return
        const newMuted = !isMuted
        audioRef.current.muted = newMuted
        setIsMuted(newMuted)
    }

    const handleVolumeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const v = parseFloat(e.target.value)
        if (!audioRef.current) return
        audioRef.current.volume = v
        audioRef.current.muted = v === 0
        setVolume(v)
        setIsMuted(v === 0)
    }

    const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
        const time = parseFloat(e.target.value)
        if (audioRef.current) {
            audioRef.current.currentTime = time
            setCurrentTime(time)
            if (onTimeUpdate) onTimeUpdate(time)
        }
    }

    const formatTime = (time: number) => {
        if (isNaN(time) || !isFinite(time)) return '0:00'
        const minutes = Math.floor(time / 60)
        const seconds = Math.floor(time % 60)
        return `${minutes}:${seconds.toString().padStart(2, '0')}`
    }

    const effectiveDuration = maxDuration && (!duration || !isFinite(duration) || duration < maxDuration) ? maxDuration : duration || 0

    if (!src) return null

    return (
        <div className="custom-audio-player">
            <audio ref={audioRef} src={src} preload="metadata" />

            <button
                type="button"
                className="play-btn"
                onClick={togglePlayPause}
                title={isPlaying ? "Pause" : "Play"}
            >
                {isPlaying ? <PauseIcon width={16} height={16} /> : <PlayIcon width={16} height={16} style={{ marginLeft: '2px' }} />}
            </button>

            <span className="time-display">
                {formatTime(currentTime)} / {formatTime(effectiveDuration)}
            </span>

            <input
                type="range"
                className="progress-slider"
                min={0}
                max={effectiveDuration || 100}
                step={0.1}
                value={currentTime}
                onChange={handleSeek}
                style={{ '--progress': `${(currentTime / (effectiveDuration || 1)) * 100}%` } as React.CSSProperties}
            />

            <div className="volume-control">
                <button type="button" className="mute-btn" onClick={toggleMute} title={isMuted ? 'Unmute' : 'Mute'}>
                    {isMuted || volume === 0 ? <VolumeMuteIcon width={16} height={16} /> : <VolumeUpIcon width={16} height={16} />}
                </button>
                <input
                    type="range"
                    className="volume-slider"
                    min={0}
                    max={1}
                    step={0.02}
                    value={isMuted ? 0 : volume}
                    onChange={handleVolumeChange}
                    title={`Volume: ${Math.round((isMuted ? 0 : volume) * 100)}%`}
                    style={{ '--vol': `${(isMuted ? 0 : volume) * 100}%` } as React.CSSProperties}
                />
            </div>
        </div>
    )
}
)

AudioPlayer.displayName = 'AudioPlayer'
