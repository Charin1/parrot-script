import axios, { AxiosError } from 'axios'
import type {
  Meeting,
  NativeParticipant,
  NativeSpeakingEvent,
  RecordingType,
  SearchResult,
  Segment,
  StartRecordingOptions,
  StartRecordingResult,
  Summary,
} from '../types/models'

const API_TOKEN_STORAGE_KEY = 'parrot-script-api-token'
const DEFAULT_BACKEND_PORT = '8000'
const DEFAULT_BACKEND_PROTOCOL = 'http:'
const TRANSCRIPT_PAGE_SIZE = 500

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '')
}

export function getBackendOrigin(): string {
  const configured = import.meta.env.VITE_BACKEND_ORIGIN?.trim()
  if (configured) {
    return trimTrailingSlash(configured)
  }

  const defaultOrigin = `${DEFAULT_BACKEND_PROTOCOL}//127.0.0.1:${DEFAULT_BACKEND_PORT}`
  if (typeof window === 'undefined') {
    return defaultOrigin
  }

  const { protocol, hostname, port, origin } = window.location
  const isHttp = protocol === 'http:' || protocol === 'https:'
  const isLoopback = hostname === '127.0.0.1' || hostname === 'localhost'
  if (!isHttp) {
    return defaultOrigin
  }
  if (isLoopback && port === DEFAULT_BACKEND_PORT) {
    return trimTrailingSlash(origin)
  }
  if (isLoopback) {
    return `${protocol}//${hostname}:${DEFAULT_BACKEND_PORT}`
  }
  return defaultOrigin
}

export function buildBackendUrl(path: string): string {
  return new URL(path, `${getBackendOrigin()}/`).toString()
}

const client = axios.create({
  baseURL: buildBackendUrl('/api'),
  timeout: 30000,
  headers: {
    'X-Requested-With': 'ParrotScriptClient',
  },
})

export function getApiToken(): string {
  return window.localStorage.getItem(API_TOKEN_STORAGE_KEY)?.trim() ?? ''
}

export function setApiToken(token: string): void {
  const cleanToken = token.trim()
  if (!cleanToken) {
    window.localStorage.removeItem(API_TOKEN_STORAGE_KEY)
    return
  }
  window.localStorage.setItem(API_TOKEN_STORAGE_KEY, cleanToken)
}

export function clearApiToken(): void {
  window.localStorage.removeItem(API_TOKEN_STORAGE_KEY)
}

client.interceptors.request.use((config) => {
  const token = getApiToken()
  if (token) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Custom Axios Exponential Backoff Retry Interceptor
client.interceptors.response.use(undefined, async (error: AxiosError) => {
  const config = error.config as any
  if (!config || !config.url) {
    return Promise.reject(error)
  }

  // Initialize retry state
  config._retryCount = config._retryCount ?? 0
  
  // Only retry idempotent methods
  const method = config.method?.toUpperCase()
  const isIdempotent = ['GET', 'PATCH', 'PUT'].includes(method || '')
  
  // Retry on network errors or 5xx server errors
  const isNetworkError = error.code === 'ECONNABORTED' || error.code === 'ERR_NETWORK' || error.message === 'Network Error'
  const isServerError = error.response && error.response.status >= 500
  
  if (!isIdempotent || (!isNetworkError && !isServerError) || config._retryCount >= 3) {
    return Promise.reject(error)
  }

  config._retryCount += 1
  
  // Exponential backoff with jitter: 1s, 2s, 4s
  const backoffDelay = 1000 * (2 ** (config._retryCount - 1)) + Math.random() * 500
  await new Promise(resolve => setTimeout(resolve, backoffDelay))
  
  return client(config)
})

export function formatApiError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    if (error.response?.status === 401) {
      return 'Unauthorized. Set the API token in the UI.'
    }
    if (error.code === 'ECONNABORTED') {
      return 'Local backend timed out. Check that Parrot Script is still running.'
    }
    if (!error.response && error.code === 'ERR_NETWORK') {
      return `Cannot reach the local backend at ${getBackendOrigin()}.`
    }
    const detail = (error.response?.data as { detail?: string } | undefined)?.detail
    if (typeof detail === 'string' && detail.trim()) {
      return detail
    }
    if (error.message) {
      return error.message
    }
  }
  return 'Unexpected request error'
}

function downloadBlob(data: BlobPart, filename: string, mimeType?: string): void {
  const blob = mimeType ? new Blob([data], { type: mimeType }) : new Blob([data])
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.setAttribute('download', filename)
  document.body.appendChild(link)
  link.click()
  link.parentNode?.removeChild(link)
  window.URL.revokeObjectURL(url)
}

export const api = {
  async createMeeting(title: string): Promise<Meeting> {
    const cleanTitle = title.trim().slice(0, 200)
    const { data } = await client.post<Meeting>('/meetings/', { title: cleanTitle })
    return data
  },

  async listMeetings(signal?: AbortSignal, filters?: {
    q?: string
    status?: string
    from_date?: string
    to_date?: string
  }): Promise<Meeting[]> {
    const params: Record<string, string> = {}
    if (filters?.q) params.q = filters.q
    if (filters?.status) params.status = filters.status
    if (filters?.from_date) params.from_date = filters.from_date
    if (filters?.to_date) params.to_date = filters.to_date
    const { data } = await client.get<Meeting[]>('/meetings/', { signal, params })
    return data
  },

  async getMeeting(id: string, signal?: AbortSignal): Promise<Meeting> {
    const { data } = await client.get<Meeting>(`/meetings/${id}`, { signal })
    return data
  },

  async startRecording(id: string, options?: StartRecordingOptions): Promise<StartRecordingResult> {
    const body: Record<string, unknown> = {}
    if (options?.capture_mode) body.capture_mode = options.capture_mode
    if (typeof options?.ghost_mode === 'boolean') body.ghost_mode = options.ghost_mode
    if (options?.meeting_url !== undefined) {
      body.meeting_url = options.meeting_url?.trim() || null
    }
    if (options?.source_platform) body.source_platform = options.source_platform
    if (options?.assistant_visible_name !== undefined) {
      body.assistant_visible_name = options.assistant_visible_name?.trim() || null
    }
    if (options?.recording_type) body.recording_type = options.recording_type
    if (options?.video_resolution !== undefined) body.video_resolution = options.video_resolution
    const { data } = await client.post<StartRecordingResult>(`/meetings/${id}/start`, body)
    return data
  },

  async stopRecording(id: string): Promise<void> {
    await client.post(`/meetings/${id}/stop`)
  },

  async getTranscript(id: string, signal?: AbortSignal): Promise<Segment[]> {
    let page = 1
    let total = 0
    const items: Segment[] = []

    do {
      const { data } = await client.get<{ items: Segment[]; total: number }>(`/meetings/${id}/transcript`, {
        signal,
        params: {
          page,
          limit: TRANSCRIPT_PAGE_SIZE,
        },
      })
      items.push(...data.items)
      total = data.total
      page += 1
    } while (items.length < total)

    return items
  },

  async getSummary(id: string, signal?: AbortSignal): Promise<Summary> {
    const { data } = await client.get<Summary>(`/meetings/${id}/summary`, { signal })
    return data
  },

  async generateSummary(id: string, promptTemplate?: string): Promise<Summary> {
    const { data } = await client.post<Summary>(`/meetings/${id}/summarize`, {
      prompt_template: promptTemplate
    })
    return data
  },

  async search(query: string, limit = 10, signal?: AbortSignal): Promise<SearchResult[]> {
    const cleanQuery = query.trim().slice(0, 500)
    const { data } = await client.post<SearchResult[]>(
      '/search',
      { query: cleanQuery, limit },
      { signal },
    )
    return data
  },

  async updateSpeakerName(meetingId: string, speakerLabel: string, name: string): Promise<void> {
    const cleanName = name.trim().slice(0, 100)
    await client.patch(`/meetings/${meetingId}/speakers/${encodeURIComponent(speakerLabel)}`, { name: cleanName })
  },

  async downloadTranscript(id: string, format: 'json' | 'pdf'): Promise<void> {
    const response = await client.get(`/meetings/${id}/transcript/download?format=${format}`, { responseType: 'blob' })
    downloadBlob(response.data, `transcript_${id}.${format}`)
  },

  async downloadSummary(id: string, format: 'json' | 'pdf'): Promise<void> {
    const response = await client.get(`/meetings/${id}/summary/download?format=${format}`, { responseType: 'blob' })
    downloadBlob(response.data, `summary_${id}.${format}`)
  },

  async downloadAudio(id: string): Promise<void> {
    const response = await client.get(`/meetings/${id}/audio`, { responseType: 'blob' })
    downloadBlob(response.data, `audio_${id}.wav`, 'audio/wav')
  },

  async toggleBookmark(meetingId: string, segmentId: string, isBookmarked: boolean): Promise<{ id: string, is_bookmarked: boolean }> {
    const { data } = await client.patch<{ id: string, is_bookmarked: boolean }>(`/meetings/${meetingId}/segments/${segmentId}/bookmark`, {
      is_bookmarked: isBookmarked
    })
    return data
  },

  async updateSegmentText(meetingId: string, segmentId: string, text: string): Promise<{ id: string, text: string }> {
    const { data } = await client.patch<{ id: string, text: string }>(`/meetings/${meetingId}/segments/${segmentId}/text`, {
      text
    })
    return data
  },

  async deleteMeeting(id: string): Promise<void> {
    await client.delete(`/meetings/${id}`)
  },

  async listNativeParticipants(meetingId: string): Promise<NativeParticipant[]> {
    const { data } = await client.get<{ items: NativeParticipant[] }>(`/meetings/${meetingId}/native/participants`)
    return data.items
  },

  async syncNativeParticipants(meetingId: string, participants: NativeParticipant[]): Promise<{ participants_synced: number }> {
    const { data } = await client.put<{ participants_synced: number }>(`/meetings/${meetingId}/native/participants`, {
      participants,
    })
    return data
  },

  async syncNativeSpeakingEvents(
    meetingId: string,
    events: NativeSpeakingEvent[],
    source = 'native_provider_event'
  ): Promise<{ events_received: number; events_inserted: number; events_dropped: number }> {
    const { data } = await client.put<{ events_received: number; events_inserted: number; events_dropped: number }>(
      `/meetings/${meetingId}/native/speaking-events`,
      { events, source },
    )
    return data
  },

  async recomputeNativeAttribution(
    meetingId: string,
  ): Promise<{ segments_total: number; segments_mapped: number; segments_unmapped: number }> {
    const { data } = await client.post<{ segments_total: number; segments_mapped: number; segments_unmapped: number }>(
      `/meetings/${meetingId}/native/attribution/recompute`
    )
    return data
  },

  getAudioUrl(meetingId: string): string {
    const token = getApiToken()
    const cacheBust = Date.now()
    const url = new URL(`/api/meetings/${meetingId}/audio`, `${getBackendOrigin()}/`)
    if (token) {
      url.searchParams.set('token', token)
    }
    url.searchParams.set('_t', String(cacheBust))
    return url.toString()
  },

  getVideoUrl(meetingId: string): string {
    const token = getApiToken()
    const cacheBust = Date.now()
    const url = new URL(`/api/meetings/${meetingId}/video`, `${getBackendOrigin()}/`)
    if (token) {
      url.searchParams.set('token', token)
    }
    url.searchParams.set('_t', String(cacheBust))
    return url.toString()
  },

  async downloadVideo(id: string): Promise<void> {
    const response = await client.get(`/meetings/${id}/video`, { responseType: 'blob' })
    downloadBlob(response.data, `video_${id}.mp4`, 'video/mp4')
  },
}

export type { AxiosError }
