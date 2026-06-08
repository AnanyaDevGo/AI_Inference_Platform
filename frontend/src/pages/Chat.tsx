import { useState, useRef, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import { useChatStore } from '../stores/chatStore'
import { apiGet, apiStreamPost, apiPatch, apiDelete } from '../api/client'
import Sidebar from '../components/Sidebar'
import { useThemeStore } from '../stores/themeStore'

function formatModelDisplayName(modelName: string): string {
  if (!modelName) return 'Assistant'
  const base = modelName.split(':')[0].toLowerCase()
  if (base.includes('gemma2') || base.includes('gemma 2')) return 'Gemma 2'
  if (base.includes('gemma')) return 'Gemma'
  if (base.includes('llama3.2') || base.includes('llama 3.2')) return 'Llama 3.2'
  if (base.includes('llama3') || base.includes('llama 3')) return 'Llama 3'
  if (base.includes('llama')) return 'Llama'
  return base.split(/[-_]/).map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')
}

function parseTextFormatting(text: string) {
  if (!text) return text
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g)
  return parts.map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={index}>{part.slice(2, -2)}</strong>
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return (
        <code 
          key={index} 
          style={{ 
            background: 'var(--bg-input)', 
            padding: '2px 6px', 
            borderRadius: '4px', 
            fontFamily: 'monospace',
            border: '1px solid var(--border)',
            fontSize: '0.9em',
            color: 'var(--accent)'
          }}
        >
          {part.slice(1, -1)}
        </code>
      )
    }
    return part
  })
}

function MessageText({ content }: { content: string }) {
  if (!content) return <span>&nbsp;</span>

  // Split by triple backticks for code blocks
  const parts = content.split('```')

  return (
    <>
      {parts.map((part, index) => {
        if (index % 2 === 0) {
          const lines = part.split('\n')
          return (
            <span key={index}>
              {lines.map((line, lineIdx) => (
                <span key={lineIdx}>
                  {parseTextFormatting(line)}
                  {lineIdx < lines.length - 1 && <br />}
                </span>
              ))}
            </span>
          )
        } else {
          const lines = part.split('\n')
          const firstLine = lines[0].trim()
          const hasLanguage = /^[a-zA-Z0-9_-]+$/.test(firstLine)
          const language = hasLanguage ? firstLine : ''
          const code = hasLanguage ? lines.slice(1).join('\n') : lines.join('\n')

          return (
            <div key={index} className="code-block-container" style={{
              position: 'relative',
              margin: '12px 0',
              background: 'var(--bg-input)',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border)',
              overflow: 'hidden',
              fontFamily: 'monospace'
            }}>
              <div className="code-block-header" style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '6px 12px',
                background: 'var(--bg-secondary)',
                borderBottom: '1px solid var(--border)',
                fontSize: '0.8rem',
                color: 'var(--text-secondary)'
              }}>
                <span style={{ fontWeight: '600' }}>{language.toUpperCase() || 'CODE'}</span>
                <button
                  type="button"
                  onClick={() => navigator.clipboard.writeText(code.trim())}
                  style={{
                    background: 'var(--border)',
                    color: 'var(--text-primary)',
                    border: 'none',
                    padding: '3px 8px',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    fontSize: '0.75rem',
                    transition: 'all 0.2s',
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--border-hover)' }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = 'var(--border)' }}
                >
                  Copy
                </button>
              </div>
              <pre style={{ margin: 0, padding: '12px', overflowX: 'auto', fontSize: '0.9rem', color: 'var(--text-primary)', background: 'var(--bg-input)' }}>
                <code>{code}</code>
              </pre>
            </div>
          )
        }
      })}
    </>
  )
}

export default function ChatPage() {
  const { theme, toggleTheme } = useThemeStore()
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const messagesContainerRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const userIsScrolledUp = useRef(false)

  // Message edit/retry states
  const [editingIndex, setEditingIndex] = useState<number | null>(null)
  const [editContent, setEditContent] = useState('')
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null)

  const token = useAuthStore((s) => s.token)
  const userName = useAuthStore((s) => s.userName)
  const role = useAuthStore((s) => s.role)
  const isAdmin = useAuthStore((s) => s.isAdmin)()
  const logout = useAuthStore((s) => s.logout)
  const navigate = useNavigate()

  const [selectedModel, setSelectedModel] = useState(() => localStorage.getItem('selectedModel') || 'gemma2:2b')
  const [availableModels, setAvailableModels] = useState<string[]>(['gemma2:2b', 'llama3.2'])

  useEffect(() => {
    if (!token) return
    const loadModels = async () => {
      try {
        const data = await apiGet<{ models: string[] }>('/v1/models', token)
        if (data && data.models) {
          const merged = Array.from(new Set(['gemma2:2b', 'llama3.2', ...data.models]))
          setAvailableModels(merged)
        }
      } catch (err) {
        console.warn('Failed to load models list from backend:', err)
      }
    }
    loadModels()
  }, [token])

  const activeId = useChatStore((s) => s.activeId)
  const getActive = useChatStore((s) => s.getActive)
  const createConversation = useChatStore((s) => s.createConversation)
  const addLocalMessage = useChatStore((s) => s.addLocalMessage)
  const updateLocalMessage = useChatStore((s) => s.updateLocalMessage)
  const saveMessage = useChatStore((s) => s.saveMessage)
  const updateMessage = useChatStore((s) => s.updateMessage)
  const fetchConversations = useChatStore((s) => s.fetchConversations)
  const fetchConversation = useChatStore((s) => s.fetchConversation)
  const clearAll = useChatStore((s) => s.clearAll)

  // Load conversations list on mount and restore active chat from localStorage
  useEffect(() => {
    if (token) {
      fetchConversations(token).then(() => {
        const savedId = localStorage.getItem('activeChatId')
        if (savedId) {
          useChatStore.getState().setActiveId(savedId)
          useChatStore.getState().fetchConversation(token, savedId)
        }
      })
    }
  }, [token, fetchConversations])

  // Smart auto-scroll
  const scrollToBottom = useCallback(() => {
    if (!userIsScrolledUp.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: streaming ? 'auto' : 'smooth' })
    }
  }, [streaming])

  const activeConv = getActive()

  useEffect(() => { scrollToBottom() }, [activeConv?.messages, scrollToBottom])

  const handleScroll = () => {
    const el = messagesContainerRef.current
    if (!el) return
    const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    userIsScrolledUp.current = distFromBottom > 100
  }

  useEffect(() => {
    userIsScrolledUp.current = false
    messagesEndRef.current?.scrollIntoView()
  }, [activeId])

  const handleLogout = () => {
    clearAll()
    logout()
    navigate('/login')
  }

  const handleNewChat = async () => {
    if (token) {
      await createConversation(token, selectedModel)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.nativeEvent.isComposing) return
    if ((e.key === 'Enter' || e.keyCode === 13) && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const autoResize = () => {
    const el = textareaRef.current
    if (el) {
      el.style.height = 'auto'
      el.style.height = Math.min(el.scrollHeight, 160) + 'px'
    }
  }

  const runCompletionStream = async (convId: string, assistantMsgId: string) => {
    setStreaming(true)
    userIsScrolledUp.current = false

    const conv = useChatStore.getState().conversations.find((c) => c.id === convId)
    const allMessages = (conv?.messages || [])
      .filter((m) => m.content)
      .map((m) => ({ role: m.role, content: m.content }))

    let accumulated = ''

    try {
      await apiStreamPost(
        '/v1/chat/completions',
        {
          model: selectedModel,
          messages: allMessages,
          stream: true,
          max_tokens: 1024,
          temperature: 0.7,
        },
        token,
        (chunk) => {
          accumulated += chunk
          updateLocalMessage(convId, accumulated)
        },
        async () => {
          if (assistantMsgId && accumulated) {
            try {
              await updateMessage(token!, convId, assistantMsgId, accumulated)
            } catch {}
          }
          setStreaming(false)
        },
        (errMsg) => {
          updateLocalMessage(convId, `Error: ${errMsg}`)
          setStreaming(false)
        }
      )
    } catch {
      updateLocalMessage(convId, 'Error: Could not connect to the inference engine.')
      setStreaming(false)
    }
  }

  const sendMessage = async () => {
    const text = input.trim()
    if (!text || streaming || !token) return

    let convId = activeId
    if (!convId) {
      convId = await createConversation(token, selectedModel)
    }

    setInput('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'

    addLocalMessage(convId, { role: 'user', content: text })
    addLocalMessage(convId, { role: 'assistant', content: '' })

    let userMsgId: string | undefined
    try {
      userMsgId = await saveMessage(token, convId, 'user', text)
    } catch {}

    let assistantMsgId: string | undefined
    try {
      assistantMsgId = await saveMessage(token, convId, 'assistant', '')
    } catch {}

    await runCompletionStream(convId, assistantMsgId || '')
  }

  const handleEditSubmit = async (msgIndex: number, msgId: string) => {
    const trimmed = editContent.trim()
    if (!trimmed || streaming || !token || !activeId) return

    useChatStore.getState().editLocalUserMessage(activeId, msgIndex, trimmed)
    try {
      await apiPatch(`/api/conversations/${activeId}/messages/${msgId}`, {
        role: 'user',
        content: trimmed
      }, token)
    } catch {}

    const conv = useChatStore.getState().conversations.find((c) => c.id === activeId)
    if (!conv) return

    const nextMsg = conv.messages[msgIndex + 1]
    if (nextMsg && nextMsg.id) {
      try {
        await apiDelete(`/api/conversations/${activeId}/messages/${nextMsg.id}`, token)
      } catch {}
    }

    useChatStore.getState().truncateLocalMessages(activeId, msgIndex + 1)

    addLocalMessage(activeId, { role: 'assistant', content: '' })
    let newAssistantMsgId = ''
    try {
      newAssistantMsgId = await saveMessage(token, activeId, 'assistant', '')
    } catch {}

    setEditingIndex(null)
    await runCompletionStream(activeId, newAssistantMsgId)
  }

  const handleRetry = async (msgIndex: number, msgId: string) => {
    if (streaming || !token || !activeId) return

    try {
      await apiDelete(`/api/conversations/${activeId}/messages/${msgId}`, token)
    } catch {}

    useChatStore.getState().truncateLocalMessages(activeId, msgIndex)

    addLocalMessage(activeId, { role: 'assistant', content: '' })
    let newAssistantMsgId = ''
    try {
      newAssistantMsgId = await saveMessage(token, activeId, 'assistant', '')
    } catch {}

    await runCompletionStream(activeId, newAssistantMsgId)
  }

  const initials = (userName || 'U').charAt(0).toUpperCase()
  const messages = activeConv?.messages || []

  return (
    <div className="chat-layout">
      <div className={`sidebar-wrapper ${sidebarOpen ? 'open' : 'closed'}`}>
        <Sidebar onNewChat={handleNewChat} />
      </div>

      <div className="chat-app">
        <header className="chat-header">
          <div className="header-left">
            <button
              className="btn-toggle-sidebar"
              onClick={() => setSidebarOpen(!sidebarOpen)}
              title={sidebarOpen ? 'Close sidebar' : 'Open sidebar'}
            >
              {sidebarOpen ? '◁' : '▷'}
            </button>
            <div className="logo">
              <div className="logo-icon">⚡</div>
              <span className="logo-text">InferVoyage</span>
            </div>
            <select
              value={selectedModel}
              onChange={(e) => {
                const val = e.target.value
                setSelectedModel(val)
                localStorage.setItem('selectedModel', val)
              }}
              style={{
                marginLeft: '16px',
                background: 'var(--bg-input)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border)',
                borderRadius: '6px',
                padding: '4px 8px',
                fontSize: '0.85rem',
                fontWeight: '600',
                cursor: 'pointer',
                outline: 'none',
                transition: 'border-color var(--transition)',
              }}
              className="model-select"
            >
              {availableModels.map((m) => (
                <option key={m} value={m} style={{ background: 'var(--bg-secondary)', color: 'var(--text-primary)' }}>
                  {m}
                </option>
              ))}
            </select>
          </div>
          <div className="header-right">
            <button
              onClick={toggleTheme}
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--text-primary)',
                fontSize: '18px',
                cursor: 'pointer',
                padding: '8px',
                borderRadius: '50%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                transition: 'background var(--transition)',
                marginRight: '12px'
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--border)' }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'none' }}
              title={theme === 'dark' ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
            >
              {theme === 'dark' ? '☀️' : '🌙'}
            </button>
            <div className="user-info">
              <div className="user-avatar">{initials}</div>
              <span className="user-name">{userName}</span>
              {role && <span className="role-badge">{role.replace('_', ' ')}</span>}
            </div>
            {isAdmin && (
              <button className="btn-admin" onClick={() => navigate('/admin')} title="Admin Panel">
                ⚙ Admin
              </button>
            )}
            <button className="btn-logout" onClick={handleLogout}>
              Sign Out
            </button>
          </div>
        </header>

        <div
          className="chat-messages"
          ref={messagesContainerRef}
          onScroll={handleScroll}
        >
          {messages.length === 0 && (
            <div className="welcome-msg">
              <div className="welcome-icon">✦</div>
              <h2>What can I help you with?</h2>
              <p>Start a conversation with {formatModelDisplayName(selectedModel)} — ask questions, brainstorm ideas, or get help with code.</p>
              <div className="welcome-suggestions">
                {[
                  'Explain quantum computing simply',
                  'Write a Python function to sort a list',
                  'What is the theory of relativity?',
                ].map((s) => (
                  <button
                    key={s}
                    className="suggestion-chip"
                    onClick={() => { setInput(s); textareaRef.current?.focus() }}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={msg.id || i} className={`message ${msg.role}`}>
              <div className="message-avatar">
                {msg.role === 'user' ? initials : '✦'}
              </div>
              <div className="message-content">
                <div className="message-role" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span>{msg.role === 'user' ? 'You' : formatModelDisplayName(selectedModel)}</span>
                  {!streaming && msg.role === 'user' && editingIndex !== i && (
                    <button
                      type="button"
                      onClick={() => { setEditingIndex(i); setEditContent(msg.content); }}
                      style={{
                        background: 'none',
                        border: 'none',
                        color: 'var(--text-muted)',
                        cursor: 'pointer',
                        fontSize: '0.75rem',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '4px',
                        padding: '2px 6px',
                        borderRadius: '4px',
                        transition: 'color var(--transition)'
                      }}
                      className="btn-edit-message"
                      title="Edit Message"
                    >
                      ✏️ Edit
                    </button>
                  )}
                  {!streaming && msg.role === 'assistant' && (
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button
                        type="button"
                        onClick={() => {
                          navigator.clipboard.writeText(msg.content)
                          setCopiedIndex(i)
                          setTimeout(() => setCopiedIndex(null), 2000)
                        }}
                        style={{
                          background: 'none',
                          border: 'none',
                          color: 'var(--text-muted)',
                          cursor: 'pointer',
                          fontSize: '0.75rem',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '4px',
                          padding: '2px 6px',
                          borderRadius: '4px',
                          transition: 'color var(--transition)'
                        }}
                        className="btn-copy-message"
                        title="Copy response"
                      >
                        {copiedIndex === i ? '✅ Copied' : '📋 Copy'}
                      </button>
                      {msg.id && (
                        <button
                          type="button"
                          onClick={() => handleRetry(i, msg.id || '')}
                          style={{
                            background: 'none',
                            border: 'none',
                            color: 'var(--text-muted)',
                            cursor: 'pointer',
                            fontSize: '0.75rem',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '4px',
                            padding: '2px 6px',
                            borderRadius: '4px',
                            transition: 'color var(--transition)'
                          }}
                          className="btn-retry-message"
                          title="Retry response"
                        >
                          ↻ Retry
                        </button>
                      )}
                    </div>
                  )}
                </div>
                
                {editingIndex === i ? (
                  <div style={{ marginTop: '8px' }}>
                    <textarea
                      value={editContent}
                      onChange={(e) => setEditContent(e.target.value)}
                      style={{
                        width: '100%',
                        background: 'var(--bg-input)',
                        border: '1px solid var(--border)',
                        color: 'var(--text-primary)',
                        padding: '10px',
                        borderRadius: 'var(--radius-sm)',
                        fontSize: '14px',
                        fontFamily: 'inherit',
                        outline: 'none',
                        resize: 'vertical',
                        minHeight: '60px'
                      }}
                      autoFocus
                    />
                    <div style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
                      <button
                        onClick={() => handleEditSubmit(i, msg.id || '')}
                        disabled={streaming}
                        style={{
                          background: 'var(--accent)',
                          color: 'white',
                          border: 'none',
                          padding: '6px 12px',
                          borderRadius: '6px',
                          cursor: 'pointer',
                          fontSize: '0.8rem',
                          fontWeight: '600'
                        }}
                      >
                        Save & Submit
                      </button>
                      <button
                        onClick={() => setEditingIndex(null)}
                        style={{
                          background: 'transparent',
                          color: 'var(--text-secondary)',
                          border: '1px solid var(--border)',
                          padding: '6px 12px',
                          borderRadius: '6px',
                          cursor: 'pointer',
                          fontSize: '0.8rem'
                        }}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <div
                    className={`message-text ${
                      msg.role === 'assistant' && streaming && i === messages.length - 1
                        ? 'streaming-cursor'
                        : ''
                    }`}
                  >
                    {msg.role === 'assistant' && msg.content === '' && streaming && i === messages.length - 1 ? (
                      <div className="typing-indicator" style={{ display: 'flex', gap: '6px', alignItems: 'center', height: '20px', padding: '8px 0' }}>
                        <span style={{ width: '8px', height: '8px', background: 'var(--accent)', borderRadius: '50%', display: 'inline-block', animation: 'typing-pulse 1.4s infinite ease-in-out both' }}></span>
                        <span style={{ width: '8px', height: '8px', background: 'var(--accent)', borderRadius: '50%', display: 'inline-block', animation: 'typing-pulse 1.4s infinite ease-in-out both 0.2s' }}></span>
                        <span style={{ width: '8px', height: '8px', background: 'var(--accent)', borderRadius: '50%', display: 'inline-block', animation: 'typing-pulse 1.4s infinite ease-in-out both 0.4s' }}></span>
                      </div>
                    ) : (
                      <MessageText content={msg.content} />
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}

          <div ref={messagesEndRef} />
        </div>

        <div className="chat-input-area">
          <div className="input-wrapper">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => { setInput(e.target.value); autoResize() }}
              onKeyDown={handleKeyDown}
              placeholder="Type your message..."
              rows={1}
              disabled={streaming}
            />
            <button
              className="btn-send"
              onClick={sendMessage}
              disabled={streaming || !input.trim()}
              title="Send"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            </button>
          </div>
          <div className="input-hint">Enter to send · Shift+Enter for new line · Model: {selectedModel}</div>
        </div>
      </div>
    </div>
  )
}
