export type MeetingLifecycleStatus = 'active' | 'recording' | 'completed' | 'failed'
export type CaptureMode = 'private' | 'assistant'
export type SourcePlatform = 'local' | 'google_meet' | 'zoom' | 'teams' | 'other'
export type AssistantJoinStatus = 'not_requested' | 'pending' | 'joined' | 'unsupported' | 'failed'
export type ConsentStatus = 'not_needed' | 'required' | 'pending' | 'granted' | 'denied' | 'unknown'
export type RecordingType = 'audio' | 'video_audio'
export type VideoResolution = '1280x720' | '854x480' | '1920x1080' | '2560x1440'
export type PlaybackSyncSource = 'system' | 'transcript' | 'audio' | 'video'

export interface Meeting {
  id: string
  title: string
  created_at: string
  ended_at: string | null
  duration_s: number | null
  status: MeetingLifecycleStatus
  metadata: string | null
  capture_mode: CaptureMode
  ghost_mode: boolean
  source_platform: SourcePlatform | null
  meeting_url: string | null
  assistant_join_status: AssistantJoinStatus
  assistant_visible_name: string | null
  consent_status: ConsentStatus
  provider_session_id: string | null
  provider_metadata: string | null
  recording_type: RecordingType
  video_resolution: string | null
  has_video: boolean
}

export interface StartRecordingOptions {
  capture_mode?: CaptureMode
  ghost_mode?: boolean
  meeting_url?: string | null
  source_platform?: SourcePlatform | null
  assistant_visible_name?: string | null
  recording_type?: RecordingType
  video_resolution?: VideoResolution | null
}

export interface StartRecordingResult {
  status: string
  meeting_id: string
  message: string | null
}

export interface Segment {
  id?: string
  segment_id?: string
  meeting_id: string
  speaker: string
  display_name?: string
  text: string
  start_time: number
  end_time: number
  confidence: number
  is_bookmarked?: boolean
}

export interface Summary {
  id: string
  meeting_id: string
  content: string
  created_at: string
  model_used: string | null
}

export interface MeetingStatus {
  meeting_id: string
  recording: boolean
  speakers_detected: number
  duration_s: number
}

export interface SearchResult {
  meeting_id: string
  text: string
  score: number
}
