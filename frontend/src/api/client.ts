import axios, { AxiosError } from 'axios'
import type { Meeting, SearchResult, Segment, Summary } from '../types/models'

const API_TOKEN_STORAGE_KEY = 'parrot-script-api-token'

const client = axios.create({
  baseURL: '/api',
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

export function formatApiError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    if (error.response?.status === 401) {
      return 'Unauthorized. Set the API token in the UI.'
    }
    if (error.code === 'ECONNABORTED') {
      return 'Local backend timed out. Check that Parrot Script is still running.'
    }
    if (!error.response && error.code === 'ERR_NETWORK') {
      return 'Cannot reach the local backend at 127.0.0.1:8000.'
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

export const api = {
  async createMeeting(title: string): Promise<Meeting> {
    const cleanTitle = title.trim().slice(0, 200)
    const { data } = await client.post<Meeting>('/meetings/', { title: cleanTitle })
    return data
  },

  async listMeetings(signal?: AbortSignal): Promise<Meeting[]> {
    const { data } = await client.get<Meeting[]>('/meetings/', { signal })
    return data
  },

  async getMeeting(id: string, signal?: AbortSignal): Promise<Meeting> {
    const { data } = await client.get<Meeting>(`/meetings/${id}`, { signal })
    return data
  },

  async startRecording(id: string): Promise<void> {
    await client.post(`/meetings/${id}/start`)
  },

  async stopRecording(id: string): Promise<void> {
    await client.post(`/meetings/${id}/stop`)
  },

  async getTranscript(id: string, signal?: AbortSignal): Promise<Segment[]> {
    const { data } = await client.get<{ items: Segment[] }>(`/meetings/${id}/transcript`, { signal })
    return data.items
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
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', `transcript_${id}.${format}`)
    document.body.appendChild(link)
    link.click()
    link.parentNode?.removeChild(link)
  },

  async downloadSummary(id: string, format: 'json' | 'pdf'): Promise<void> {
    const response = await client.get(`/meetings/${id}/summary/download?format=${format}`, { responseType: 'blob' })
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', `summary_${id}.${format}`)
    document.body.appendChild(link)
    link.click()
    link.parentNode?.removeChild(link)
  },

  async downloadAudio(id: string): Promise<void> {
    const response = await client.get(`/meetings/${id}/audio`, { responseType: 'blob' })
    const url = window.URL.createObjectURL(new Blob([response.data], { type: 'audio/wav' }))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', `audio_${id}.wav`)
    document.body.appendChild(link)
    link.click()
    link.parentNode?.removeChild(link)
    window.URL.revokeObjectURL(url)
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

  getAudioUrl(meetingId: string): string {
    const token = getApiToken()
    const url = `/api/meetings/${meetingId}/audio`
    return token ? `${url}?token=${encodeURIComponent(token)}` : url
  },
}

export type { AxiosError }
