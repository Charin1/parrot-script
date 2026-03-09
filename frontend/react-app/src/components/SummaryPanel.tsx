import { useState, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import type { Summary } from '../types/models'
import { SparklesIcon, DownloadIcon } from './icons'
import { api } from '../api/client'

interface Props {
  summary: Summary | null
  onGenerate: (promptTemplate?: string) => Promise<void>
  busy?: boolean
  disabled?: boolean
}

const DEFAULT_PROMPT = ""

export function SummaryPanel({ summary, onGenerate, busy = false, disabled = false }: Props) {
  const [promptTemplate, setPromptTemplate] = useState(() => {
    return localStorage.getItem('parrot_custom_prompt') || DEFAULT_PROMPT
  })
  const [isPromptOpen, setIsPromptOpen] = useState(false)

  useEffect(() => {
    localStorage.setItem('parrot_custom_prompt', promptTemplate)
  }, [promptTemplate])

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
            onClick={() => void onGenerate(promptTemplate.trim() ? promptTemplate : undefined)}
            disabled={busy || disabled}
          >
            <SparklesIcon className="btn-icon" width={14} height={14} />
            <span>{busy ? 'Generating...' : 'Generate'}</span>
          </button>
        </div>
      </div>

      <div style={{ marginBottom: '1rem' }}>
        <details
          open={isPromptOpen}
          onToggle={(e) => setIsPromptOpen((e.target as HTMLDetailsElement).open)}
          style={{
            padding: '0.5rem',
            background: 'var(--bg-secondary)',
            borderRadius: 'var(--radius)',
            border: '1px solid var(--border)'
          }}
        >
          <summary style={{ cursor: 'pointer', fontWeight: 500, fontSize: '0.9rem' }}>
            Custom Summary Rules (Optional)
          </summary>
          <div style={{ marginTop: '0.5rem' }}>
            <textarea
              value={promptTemplate}
              onChange={(e) => setPromptTemplate(e.target.value)}
              placeholder="e.g. Write the summary entirely in French, specifically focusing on metrics..."
              style={{
                width: '100%',
                minHeight: '80px',
                padding: '0.5rem',
                borderRadius: 'var(--radius)',
                border: '1px solid var(--border)',
                background: 'var(--bg-primary)',
                color: 'var(--text-primary)',
                fontFamily: 'inherit',
                resize: 'vertical'
              }}
            />
            <p className="muted" style={{ fontSize: '0.8rem', marginTop: '0.25rem' }}>
              Overrides the default instructions. Use {'{transcript}'} or {'{summaries}'} to specify where the text goes, otherwise it will be appended automatically.
            </p>
          </div>
        </details>
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
