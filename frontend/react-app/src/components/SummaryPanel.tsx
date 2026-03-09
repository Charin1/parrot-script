import ReactMarkdown from 'react-markdown'
import type { Summary } from '../types/models'
import { SparklesIcon, DownloadIcon } from './icons'
import { api } from '../api/client'

interface Props {
  summary: Summary | null
  onGenerate: () => Promise<void>
  busy?: boolean
  disabled?: boolean
}

export function SummaryPanel({ summary, onGenerate, busy = false, disabled = false }: Props) {
  return (
    <div className="panel">
      <div className="panel-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3>Meeting Summary</h3>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          {summary && (
            <>
              <button
                type="button"
                className="secondary"
                onClick={() => void api.downloadSummary(summary.meeting_id, 'json')}
                title="Download JSON"
              >
                <DownloadIcon className="btn-icon" width={14} height={14} />
                <span>JSON</span>
              </button>
              <button
                type="button"
                className="secondary"
                onClick={() => void api.downloadSummary(summary.meeting_id, 'pdf')}
                title="Download PDF"
              >
                <DownloadIcon className="btn-icon" width={14} height={14} />
                <span>PDF</span>
              </button>
            </>
          )}
          <button
            type="button"
            className="secondary"
            onClick={() => void onGenerate()}
            disabled={busy || disabled}
          >
            <SparklesIcon className="btn-icon" width={14} height={14} />
            <span>{busy ? 'Generating...' : 'Generate'}</span>
          </button>
        </div>
      </div>

      {summary ? (
        <div className="markdown-body">
          <ReactMarkdown
            components={{
              a: ({ ...props }) => (
                <a {...props} target="_blank" rel="noreferrer noopener" />
              ),
            }}
          >
            {summary.content}
          </ReactMarkdown>
        </div>
      ) : (
        <p className="muted">No summary generated yet.</p>
      )}
    </div>
  )
}
