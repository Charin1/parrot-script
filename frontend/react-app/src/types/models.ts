export type MeetingLifecycleStatus = 'active' | 'recording' | 'completed' | 'failed'

export interface Meeting {
  id: string
  title: string
  created_at: string
  ended_at: string | null
  duration_s: number | null
  status: MeetingLifecycleStatus
  metadata: string | null
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
