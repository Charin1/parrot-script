import { formatApiError } from '../api/client'
import { useEffect, useRef, useState } from 'react'
import type { SearchResult } from '../types/models'
import { SearchIcon } from './icons'

interface Props {
  disabled?: boolean
  onSearch: (query: string, signal?: AbortSignal) => Promise<SearchResult[]>
  onSelectMeeting: (meetingId: string) => void
}

export function SearchBar({ disabled = false, onSearch, onSelectMeeting }: Props) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const controllerRef = useRef<AbortController | null>(null)

  useEffect(() => {
    return () => {
      controllerRef.current?.abort()
    }
  }, [])

  useEffect(() => {
    if (!disabled) {
      return
    }

    controllerRef.current?.abort()
    setLoading(false)
    setResults([])
    setError(null)
  }, [disabled])

  const submit = async () => {
    if (disabled) {
      setError('Load the local API token before searching.')
      return
    }

    const value = query.trim()
    if (!value) {
      setResults([])
      setError(null)
      return
    }

    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller

    setLoading(true)
    setError(null)
    try {
      const found = await onSearch(value, controller.signal)
      setResults(found)
    } catch (error) {
      if (!controller.signal.aborted) {
        setError(formatApiError(error))
      }
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false)
      }
    }
  }

  return (
    <div className="panel">
      <h3>Semantic Search</h3>
      <div className="search-row">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search across meeting transcripts"
          disabled={disabled}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              void submit()
            }
          }}
        />
        <button
          type="button"
          className="secondary"
          onClick={() => void submit()}
          disabled={loading || disabled}
        >
          <SearchIcon className="btn-icon" width={14} height={14} />
          <span>{loading ? 'Searching...' : 'Search'}</span>
        </button>
      </div>

      {error ? <p className="error-text">{error}</p> : null}

      <div className="search-results">
        {results.map((result, index) => (
          <button
            key={`${result.meeting_id}-${index}`}
            type="button"
            className="search-item"
            onClick={() => onSelectMeeting(result.meeting_id)}
          >
            <strong>Meeting {result.meeting_id.slice(0, 8)}</strong>
            <p>{result.text}</p>
            <span>Score: {result.score.toFixed(3)}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
