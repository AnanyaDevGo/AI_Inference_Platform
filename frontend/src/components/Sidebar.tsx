import { useState } from 'react'
import { useChatStore } from '../stores/chatStore'
import { useAuthStore } from '../stores/authStore'

interface SidebarProps {
  onNewChat: () => void
}

export default function Sidebar({ onNewChat }: SidebarProps) {
  const conversations = useChatStore((s) => s.conversations)
  const activeId = useChatStore((s) => s.activeId)
  const loading = useChatStore((s) => s.loading)
  
  const setActiveId = useChatStore((s) => s.setActiveId)
  const deleteConversation = useChatStore((s) => s.deleteConversation)
  const renameConversation = useChatStore((s) => s.renameConversation)
  const fetchConversation = useChatStore((s) => s.fetchConversation)
  const token = useAuthStore((s) => s.token)

  // Search and Inline Rename State
  const [searchQuery, setSearchQuery] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editTitle, setEditTitle] = useState('')

  const handleSelect = async (id: string) => {
    if (editingId) return // Disable select while editing
    setActiveId(id)
    const conv = conversations.find((c) => c.id === id)
    if (conv && conv.messages.length === 0 && token) {
      await fetchConversation(token, id)
    }
  }

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    if (confirm('Are you sure you want to delete this conversation?') && token) {
      try {
        await deleteConversation(token, id)
      } catch { /* silently fail */ }
    }
  }

  const handleRenameStart = (e: React.MouseEvent, id: string, currentTitle: string) => {
    e.stopPropagation()
    setEditingId(id)
    setEditTitle(currentTitle)
  }

  const handleRenameSave = async (id: string) => {
    const trimmed = editTitle.trim()
    if (trimmed && token) {
      try {
        await renameConversation(token, id, trimmed)
      } catch { /* silently fail */ }
    }
    setEditingId(null)
  }

  const handleRenameKeyDown = (e: React.KeyboardEvent, id: string) => {
    if (e.key === 'Enter') {
      handleRenameSave(id)
    } else if (e.key === 'Escape') {
      setEditingId(null)
    }
  }

  // Filter conversations based on search
  const filteredConversations = conversations.filter((c) =>
    c.title.toLowerCase().includes(searchQuery.toLowerCase())
  )

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <button className="btn-new-chat" onClick={onNewChat}>
          <span className="icon">+</span>
          New Chat
        </button>
      </div>

      {/* Search Bar */}
      <div className="sidebar-search" style={{ padding: '0 16px 12px 16px' }}>
        <input
          type="text"
          placeholder="Search chats..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          style={{
            width: '100%',
            padding: '8px 12px',
            borderRadius: '6px',
            border: '1px solid var(--border)',
            background: 'var(--bg-input)',
            color: 'var(--text-primary)',
            fontSize: '0.85rem',
            outline: 'none',
            transition: 'border-color var(--transition)'
          }}
        />
      </div>

      <nav className="sidebar-nav">
        {loading ? (
          <div className="sidebar-loading" style={{ textAlign: 'center', padding: '20px', color: 'var(--text-muted)' }}>
            Loading chats...
          </div>
        ) : (
          filteredConversations.map((conv) => (
            <button
              key={conv.id}
              className={`sidebar-item ${conv.id === activeId ? 'active' : ''}`}
              onClick={() => handleSelect(conv.id)}
              title={conv.title}
              disabled={editingId === conv.id}
            >
              <span className="sidebar-item-icon">💬</span>
              
              {editingId === conv.id ? (
                <input
                  type="text"
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  onKeyDown={(e) => handleRenameKeyDown(e, conv.id)}
                  onBlur={() => handleRenameSave(conv.id)}
                  autoFocus
                  style={{
                    flex: 1,
                    background: 'transparent',
                    border: 'none',
                    borderBottom: '1px solid var(--accent)',
                    color: 'var(--text-primary)',
                    fontSize: '0.85rem',
                    outline: 'none',
                    padding: '2px 0'
                  }}
                  onClick={(e) => e.stopPropagation()}
                />
              ) : (
                <span className="sidebar-item-title">{conv.title}</span>
              )}

              {editingId !== conv.id && (
                <div className="sidebar-item-actions" style={{ display: 'flex', gap: '4px' }}>
                  <button
                    className="sidebar-item-rename"
                    onClick={(e) => handleRenameStart(e, conv.id, conv.title)}
                    title="Rename"
                    style={{
                      background: 'none',
                      border: 'none',
                      color: 'var(--text-muted)',
                      cursor: 'pointer',
                      fontSize: '0.85rem',
                      padding: '2px'
                    }}
                  >
                    ✏️
                  </button>
                  <button
                    className="sidebar-item-delete"
                    onClick={(e) => handleDelete(e, conv.id)}
                    title="Delete"
                  >
                    ×
                  </button>
                </div>
              )}
            </button>
          ))
        )}

        {!loading && filteredConversations.length === 0 && (
          <div className="sidebar-empty">
            {searchQuery ? 'No matching chats found.' : 'No conversations yet.'}
            <br />
            {!searchQuery && 'Click "New Chat" to start.'}
          </div>
        )}
      </nav>
    </aside>
  )
}
