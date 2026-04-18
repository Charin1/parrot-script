import { useCallback, useEffect, useState } from 'react'
import { api, formatApiError } from '../api/client'
import type { Meeting, StartRecordingOptions, Summary } from '../types/models'
import type { Segment } from '../types/models'

export function useMeetings(
  authReady: boolean,
  setAppError: (err: string | null) => void,
  setAppNotice: (notice: string | null) => void,
  setBusy: (busy: boolean) => void,
  setSegments: (segments: Segment[]) => void,
  setSummaryProcessing: (processing: boolean) => void
) {
  const [meetings, setMeetings] = useState<Meeting[]>([])
  const [selectedMeetingId, setSelectedMeetingId] = useState<string | null>(null)
  const [summary, setSummary] = useState<Summary | null>(null)

  const clearMeetingsState = useCallback(() => {
    setMeetings([])
    setSelectedMeetingId(null)
    setSummary(null)
    setSummaryProcessing(false)
    setSegments([])
  }, [setSegments, setSummaryProcessing])

  const refreshMeetings = useCallback(async (signal?: AbortSignal, filters?: {
    q?: string
    status?: string
    from_date?: string
    to_date?: string
  }) => {
    const list = await api.listMeetings(signal, filters)
    setMeetings(list)
    setSelectedMeetingId((current) => {
      if (current && list.some((meeting) => meeting.id === current)) {
        return current
      }
      return list.length > 0 ? list[0].id : null
    })
  }, [])

  const runBusy = async (action: () => Promise<void>) => {
    setBusy(true)
    setAppError(null)
    setAppNotice(null)
    try {
      await action()
    } catch (error) {
      console.error('Action failed:', error)
      setAppError(formatApiError(error))
    } finally {
      setBusy(false)
    }
  }

  const createMeeting = async (title: string) => {
    await runBusy(async () => {
      const created = await api.createMeeting(title)
      await refreshMeetings()
      setSelectedMeetingId(created.id)
      setSummary(null)
      setSegments([])
    })
  }

  const startMeeting = async (options: StartRecordingOptions) => {
    if (!selectedMeetingId) return
    await runBusy(async () => {
      const result = await api.startRecording(selectedMeetingId, options)
      await refreshMeetings()
      if (result.message) {
        setAppNotice(result.message)
      }
    })
  }

  const stopMeeting = async () => {
    if (!selectedMeetingId) return
    await runBusy(async () => {
      await api.stopRecording(selectedMeetingId)
      await refreshMeetings()
    })
  }

  const generateSummary = async (promptTemplate?: string) => {
    if (!selectedMeetingId) return
    setSummaryProcessing(true)
    setAppError(null)
    setAppNotice(null)
    setSummary(null)
    try {
      const data = await api.generateSummary(selectedMeetingId, promptTemplate)
      if ((data as any).status === 'processing') {
        return
      }
      setSummary(data)
      setSummaryProcessing(false)
    } catch (error) {
      console.error('Action failed:', error)
      setAppError(formatApiError(error))
      setSummaryProcessing(false)
    }
  }

  const deleteMeeting = async (id: string, meetingTitle: string) => {
    if (!window.confirm(`Are you sure you want to permanently delete "${meetingTitle}"? This will remove all transcripts and the audio recording.`)) {
      return
    }

    await runBusy(async () => {
      await api.deleteMeeting(id)
      if (selectedMeetingId === id) {
        setSelectedMeetingId(null)
        setSummary(null)
        setSegments([])
      }
      await refreshMeetings()
    })
  }

  return {
    meetings,
    setMeetings,
    selectedMeetingId,
    setSelectedMeetingId,
    summary,
    setSummary,
    clearMeetingsState,
    refreshMeetings,
    createMeeting,
    startMeeting,
    stopMeeting,
    generateSummary,
    deleteMeeting,
  }
}
