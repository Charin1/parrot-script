import type { Meeting } from '../types/models'
import { SearchIcon } from './icons'

interface Props {
  meetings: Meeting[]
  onOpenMeeting: (meetingId: string) => void
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString()
}

function formatDuration(seconds: number | null): string {
  if (!seconds || seconds <= 0) {
    return 'N/A'
  }
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}m ${secs}s`
}

export function PastMeetingsDashboard({ meetings, onOpenMeeting }: Props) {
  const pastMeetings = meetings.filter((meeting) => meeting.status === 'completed' || meeting.status === 'failed')

  const completedCount = pastMeetings.filter((meeting) => meeting.status === 'completed').length
  const failedCount = pastMeetings.filter((meeting) => meeting.status === 'failed').length

  const avgDuration =
    pastMeetings.length === 0
      ? 0
      : Math.round(
          pastMeetings.reduce((sum, meeting) => sum + (meeting.duration_s ?? 0), 0) / pastMeetings.length,
        )

  return (
    <section className="panel dashboard-panel">
      <div className="panel-header">
        <h3>Past Meetings Dashboard</h3>
      </div>

      <div className="dashboard-stats">
        <article className="dashboard-stat-card">
          <span>Total Past</span>
          <strong>{pastMeetings.length}</strong>
        </article>
        <article className="dashboard-stat-card">
          <span>Completed</span>
          <strong>{completedCount}</strong>
        </article>
        <article className="dashboard-stat-card">
          <span>Failed</span>
          <strong>{failedCount}</strong>
        </article>
        <article className="dashboard-stat-card">
          <span>Avg Duration</span>
          <strong>{formatDuration(avgDuration)}</strong>
        </article>
      </div>

      <div className="dashboard-list">
        {pastMeetings.length === 0 ? (
          <p className="muted">No past meetings yet.</p>
        ) : (
          pastMeetings.map((meeting) => (
            <article key={meeting.id} className="dashboard-meeting-row">
              <div>
                <h4>{meeting.title}</h4>
                <p className="muted">{formatDate(meeting.created_at)}</p>
              </div>
              <div className="dashboard-meta">
                <span className={`badge ${meeting.status === 'failed' ? 'badge-failed' : 'badge-idle'}`}>
                  {meeting.status}
                </span>
                <span className="muted">{formatDuration(meeting.duration_s)}</span>
                <button type="button" className="secondary" onClick={() => onOpenMeeting(meeting.id)}>
                  <SearchIcon className="btn-icon" width={14} height={14} />
                  <span>Open</span>
                </button>
              </div>
            </article>
          ))
        )}
      </div>
    </section>
  )
}
