import { useState, useRef, useEffect } from 'react'
import { api, formatApiError } from '../api/client'
import { SparklesIcon, SendIcon, UserIcon } from './icons'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: number
  sources?: any[]
}

interface LiveParrotAgentProps {
  meetingId: string
  disabled?: boolean
}

export function LiveParrotAgent({ meetingId, disabled }: LiveParrotAgentProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, loading, status])

  const handleSend = async () => {
    const text = input.trim()
    if (!text || loading || disabled) return

    const userMessage: Message = {
      id: Math.random().toString(36).substr(2, 9),
      role: 'user',
      content: text,
      timestamp: Date.now()
    }

    setMessages(prev => [...prev, userMessage])
    setInput('')
    setLoading(true)
    setStatus('Analyzing query...')

    try {
      const history = messages.map(m => ({ role: m.role, content: m.content }))
      const result = await api.agentChat(meetingId, text, history)
      
      const assistantMessage: Message = {
        id: Math.random().toString(36).substr(2, 9),
        role: 'assistant',
        content: result.response,
        timestamp: Date.now(),
        sources: result.sources,
        // Custom field for displaying the intent/search type
        intent: result.source_type
      } as any
      setMessages(prev => [...prev, assistantMessage])
    } catch (err) {
      const errorMessage: Message = {
        id: Math.random().toString(36).substr(2, 9),
        role: 'assistant',
        content: `Expert Note: The agent encountered a connection or processing error. ${formatApiError(err)}`,
        timestamp: Date.now()
      }
      setMessages(prev => [...prev, errorMessage])
    } finally {
      setLoading(false)
      setStatus('')
    }
  }

  return (
    <div className="agent-chat-container">
      <div className="agent-messages" ref={scrollRef}>
        {messages.length === 0 && (
          <div className="agent-empty-state">
            <SparklesIcon width={32} height={32} style={{ opacity: 0.5, marginBottom: '0.5rem' }} />
            <p>Ask me anything about this meeting.</p>
            <p className="muted" style={{ fontSize: '0.8rem' }}>"What were the next steps?" or "Who mentioned the budget?"</p>
          </div>
        )}
        {messages.map(m => (
          <div key={m.id} className={`agent-message-row ${m.role}`}>
            <div className="agent-message-avatar">
              {m.role === 'user' ? <UserIcon width={16} height={16} /> : <SparklesIcon width={16} height={16} />}
            </div>
            <div className="agent-message-bubble">
              <div className="agent-message-content">{m.content}</div>
              {(m.sources || (m as any).intent) && (
                <div className="agent-message-sources">
                   <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                    <span className="muted" style={{ fontSize: '0.65rem', textTransform: 'uppercase', letterSpacing: '0.02em' }}>
                      {(m as any).intent ? `Search Mode: ${(m as any).intent}` : 'Sources'}
                    </span>
                  </div>
                  {m.sources && m.sources.length > 0 && (
                    <div className="sources-list">
                      {m.sources.slice(0, 3).map((s, i) => (
                        <div key={i} className="agent-source-chip" title={s.text}>
                          {s.text.length > 40 ? s.text.substring(0, 40) + '...' : s.text}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div className="agent-message-row assistant">
            <div className="agent-message-avatar">
              <SparklesIcon width={16} height={16} className="loading-pulse" />
            </div>
            <div className="agent-message-bubble loading">
              <div className="status-indicator">{status}</div>
              <div className="loading-dots">
                <span>.</span><span>.</span><span>.</span>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="agent-input-row">
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSend()}
          placeholder={disabled ? "Chat disabled" : "Type a message..."}
          disabled={loading || disabled}
        />
        <button onClick={handleSend} disabled={loading || disabled || !input.trim()}>
          <SendIcon width={18} height={18} />
        </button>
      </div>
    </div>
  )
}
