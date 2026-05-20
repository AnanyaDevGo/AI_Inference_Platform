import { useChatStore } from '../stores/chatStore'
import { useAuthStore } from '../stores/authStore'

interface SidebarProps {
  onNewChat: () => void
}

export default function Sidebar({ onNewChat }: SidebarProps) {
  const conversations = useChatStore((s) => s.conversations)
  const activeId = useChatStore((s) => s.activeId)
  const setActiveId = useChatStore((s) => s.setActiveId)
  const deleteConversation = useChatStore((s) => s.deleteConversation)
  const fetchConversation = useChatStore((s) => s.fetchConversation)
  const token = useAuthStore((s) => s.token)

  const handleSelect = async (id: string) => {
    setActiveId(id)
    // Fetch messages if not loaded yet
    const conv = conversations.find((c) => c.id === id)
    if (conv && conv.messages.length === 0 && (conv.messageCount ?? 0) > 0 && token) {
      await fetchConversation(token, id)
    }
  }

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    if (token) {
      try {
        await deleteConversation(token, id)
      } catch { /* silently fail */ }
    }
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <button className="btn-new-chat" onClick={onNewChat}>
          <span className="icon">+</span>
          New Chat
        </button>
      </div>

      <nav className="sidebar-nav">
        {conversations.map((conv) => (
          <button
            key={conv.id}
            className={`sidebar-item ${conv.id === activeId ? 'active' : ''}`}
            onClick={() => handleSelect(conv.id)}
            title={conv.title}
          >
            <span className="sidebar-item-icon">💬</span>
            <span className="sidebar-item-title">{conv.title}</span>
            <button
              className="sidebar-item-delete"
              onClick={(e) => handleDelete(e, conv.id)}
              title="Delete"
            >
              ×
            </button>
          </button>
        ))}

        {conversations.length === 0 && (
          <div className="sidebar-empty">
            No conversations yet.<br />Click "New Chat" to start.
          </div>
        )}
      </nav>
    </aside>
  )
}
