import { useEffect, useRef, useState } from 'react'
import type { Meeting } from '../types/models'
import { SearchIcon, TrashIcon } from './icons'

type StatusFilter = 'all' | 'completed' | 'failed'

interface DashboardFilters {
  q: string
  status: StatusFilter
  from_date: string
  to_date: string
}

interface Props {
  meetings: Meeting[]
  onOpenMeeting: (meetingId: string) => void
  onDeleteMeeting: (meetingId: string) => void
  onFiltersChange?: (filters: {
    q?: string
    status?: string
    from_date?: string
    to_date?: string
  }) => void
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatDuration(seconds: number | null): string {
  if (!seconds || seconds <= 0) return 'N/A'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}m ${secs}s`
}

export function PastMeetingsDashboard({ meetings, onOpenMeeting, onDeleteMeeting, onFiltersChange }: Props) {
  const pastMeetings = meetings.filter((m) => m.status === 'completed' || m.status === 'failed')
  const completedCount = pastMeetings.filter((m) => m.status === 'completed').length
  const failedCount = pastMeetings.filter((m) => m.status === 'failed').length
  const avgDuration =
    pastMeetings.length === 0
      ? 0
      : Math.round(pastMeetings.reduce((sum, m) => sum + (m.duration_s ?? 0), 0) / pastMeetings.length)

  const [filters, setFilters] = useState<DashboardFilters>({ q: '', status: 'all', from_date: '', to_date: '' })
  const [debouncedQ, setDebouncedQ] = useState('')
  const isMounted = useRef(false)

  useEffect(() => {
    const id = setTimeout(() => setDebouncedQ(filters.q), 300)
    return () => clearTimeout(id)
  }, [filters.q])

  useEffect(() => {
    if (!isMounted.current) {
      isMounted.current = true
      return
    }
    if (!onFiltersChange) return
    const payload: { q?: string; status?: string; from_date?: string; to_date?: string } = {}
    if (debouncedQ) payload.q = debouncedQ
    if (filters.status !== 'all') payload.status = filters.status
    if (filters.from_date) payload.from_date = new Date(filters.from_date).toISOString()
    if (filters.to_date) {
      const d = new Date(filters.to_date)
      d.setHours(23, 59, 59, 999)
      payload.to_date = d.toISOString()
    }
    onFiltersChange(payload)
  }, [debouncedQ, filters.status, filters.from_date, filters.to_date, onFiltersChange])

  const setFilter = <K extends keyof DashboardFilters>(key: K, value: DashboardFilters[K]) =>
    setFilters((prev) => ({ ...prev, [key]: value }))

  const clearFilters = () => setFilters({ q: '', status: 'all', from_date: '', to_date: '' })
  const hasActiveFilters = filters.q || filters.status !== 'all' || filters.from_date || filters.to_date

  const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
    { value: 'all', label: 'All' },
    { value: 'completed', label: 'Completed' },
    { value: 'failed', label: 'Failed' },
  ]

  return (
    <section className="panel dashboard-panel">
      <div className="panel-header">
        <h3>Past Meetings</h3>
        <div className="dashboard-summary-chips">
          <span className="dsummary-chip dsummary-chip--total">
            <strong>{pastMeetings.length}</strong> total
          </span>
          <span className="dsummary-chip dsummary-chip--ok">
            <strong>{completedCount}</strong> done
          </span>
          {failedCount > 0 && (
            <span className="dsummary-chip dsummary-chip--fail">
              <strong>{failedCount}</strong> failed
            </span>
          )}
          <span className="dsummary-chip dsummary-chip--dur">
            ⌀ {formatDuration(avgDuration)}
          </span>
        </div>
      </div>

      {/* ── Toolbar ── */}
      <div className="dtoolbar">
        {/* Search */}
        <div className="dtoolbar-search">
          <SearchIcon className="dtoolbar-search-icon" width={13} height={13} />
          <input
            id="dashboard-search"
            type="search"
            className="dtoolbar-search-input"
            placeholder="Search by title…"
            value={filters.q}
            onChange={(e) => setFilter('q', e.target.value)}
          />
        </div>

        {/* Status pill-tabs */}
        <div className="dtoolbar-status-tabs" role="group" aria-label="Filter by status">
          {STATUS_OPTIONS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              className={`dtab ${filters.status === value ? 'dtab--active' : ''}`}
              onClick={() => setFilter('status', value)}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Date range */}
        <div className="dtoolbar-dates">
          <input
            id="dashboard-filter-from"
            type="date"
            className="dtoolbar-date"
            title="From"
            value={filters.from_date}
            onChange={(e) => setFilter('from_date', e.target.value)}
          />
          <span className="dtoolbar-date-sep">–</span>
          <input
            id="dashboard-filter-to"
            type="date"
            className="dtoolbar-date"
            title="To"
            value={filters.to_date}
            onChange={(e) => setFilter('to_date', e.target.value)}
          />
        </div>

        {hasActiveFilters && (
          <button type="button" className="secondary dtoolbar-clear" onClick={clearFilters} title="Clear all filters">
            ✕ Clear
          </button>
        )}
      </div>

      {/* ── Meeting List ── */}
      <div className="dashboard-list">
        {pastMeetings.length === 0 ? (
          <div className="dashboard-empty">
            <span className="dashboard-empty-icon">🔍</span>
            <p>{hasActiveFilters ? 'No meetings match your filters.' : 'No past meetings yet.'}</p>
          </div>
        ) : (
          pastMeetings.map((meeting) => (
            <article key={meeting.id} className="dashboard-meeting-row">
              <div className="dmr-left">
                <h4>{meeting.title}</h4>
                <p className="muted dmr-meta">{formatDate(meeting.created_at)} · {formatDuration(meeting.duration_s)}</p>
              </div>
              <div className="dashboard-meta">
                <span className={`badge ${meeting.status === 'failed' ? 'badge-failed' : 'badge-idle'}`}>
                  {meeting.status}
                </span>
                <button type="button" className="secondary dmr-btn" onClick={() => onOpenMeeting(meeting.id)}>
                  <SearchIcon className="btn-icon" width={13} height={13} />
                  <span>Transcript</span>
                </button>
                <button
                  type="button"
                  className="secondary btn-danger dmr-btn dmr-btn--danger"
                  onClick={(e) => { e.stopPropagation(); onDeleteMeeting(meeting.id) }}
                  title="Delete Meeting"
                >
                  <TrashIcon className="btn-icon" width={13} height={13} />
                </button>
              </div>
            </article>
          ))
        )}
      </div>
    </section>
  )
}
