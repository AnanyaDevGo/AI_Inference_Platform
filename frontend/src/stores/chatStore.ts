import { create } from 'zustand'
import { apiGet, apiPost, apiDelete, apiPatch } from '../api/client'

export interface Message {
  id?: string
  role: 'user' | 'assistant'
  content: string
  position?: number
}

export interface Conversation {
  id: string
  title: string
  model_name?: string | null
  messages: Message[]
  createdAt?: string
  updatedAt?: string
  messageCount?: number
}

interface ChatState {
  conversations: Conversation[]
  activeId: string | null
  loading: boolean
  setActiveId: (id: string | null) => void
  fetchConversations: (token: string) => Promise<void>
  fetchConversation: (token: string, convId: string) => Promise<void>
  createConversation: (token: string, modelName?: string) => Promise<string>
  renameConversation: (token: string, id: string, title: string) => Promise<void>
  deleteConversation: (token: string, id: string) => Promise<void>
  saveMessage: (token: string, convId: string, role: string, content: string) => Promise<string>
  updateMessage: (token: string, convId: string, msgId: string, content: string) => Promise<void>
  updateLocalMessage: (convId: string, content: string) => void
  addLocalMessage: (convId: string, msg: Message) => void
  editLocalUserMessage: (convId: string, msgIndex: number, content: string) => void
  truncateLocalMessages: (convId: string, msgIndex: number) => void
  getActive: () => Conversation | undefined
  clearAll: () => void
}

interface ConvListItem {
  id: string
  title: string
  model_name?: string | null
  created_at: string
  updated_at: string
  message_count: number
}

interface ConvDetail {
  id: string
  title: string
  model_name?: string | null
  messages: { id: string; role: string; content: string; position: number }[]
}

interface MsgResponse {
  id: string
  role: string
  content: string
  position: number
}

export const useChatStore = create<ChatState>((set, get) => ({
  conversations: [],
  activeId: null,
  loading: false,

  setActiveId: (id) => {
    set({ activeId: id })
    if (id) {
      localStorage.setItem('activeChatId', id)
    } else {
      localStorage.removeItem('activeChatId')
    }
  },

  fetchConversations: async (token) => {
    set({ loading: true })
    try {
      const data = await apiGet<ConvListItem[]>('/api/conversations', token)
      set({
        conversations: data.map((c) => ({
          id: c.id,
          title: c.title,
          model_name: c.model_name,
          messages: [],
          createdAt: c.created_at,
          updatedAt: c.updated_at,
          messageCount: c.message_count,
        })),
        loading: false,
      })
    } catch {
      set({ loading: false })
    }
  },

  fetchConversation: async (token, convId) => {
    try {
      const data = await apiGet<ConvDetail>(`/api/conversations/${convId}`, token)
      set((s) => ({
        conversations: s.conversations.map((c) =>
          c.id === convId
            ? {
                ...c,
                title: data.title,
                model_name: data.model_name,
                messages: data.messages.map((m) => ({
                  id: m.id,
                  role: m.role as 'user' | 'assistant',
                  content: m.content,
                  position: m.position,
                })),
              }
            : c
        ),
      }))
    } catch {
      // If unauthorized (403) or missing (404), reset the active chat state
      set({ activeId: null })
      localStorage.removeItem('activeChatId')
    }
  },

  createConversation: async (token, modelName) => {
    const data = await apiPost<ConvDetail>('/api/conversations', { title: 'New Chat', model_name: modelName }, token)
    const conv: Conversation = {
      id: data.id,
      title: data.title,
      model_name: data.model_name,
      messages: [],
    }
    set((s) => ({
      conversations: [conv, ...s.conversations],
      activeId: data.id,
    }))
    localStorage.setItem('activeChatId', data.id)
    return data.id
  },

  renameConversation: async (token, id, title) => {
    await apiPatch(`/api/conversations/${id}`, { title }, token)
    set((s) => ({
      conversations: s.conversations.map((c) =>
        c.id === id ? { ...c, title } : c
      ),
    }))
  },

  deleteConversation: async (token, id) => {
    await apiDelete(`/api/conversations/${id}`, token)
    set((s) => {
      const filtered = s.conversations.filter((c) => c.id !== id)
      const newActive = s.activeId === id ? (filtered[0]?.id ?? null) : s.activeId
      if (newActive) {
        localStorage.setItem('activeChatId', newActive)
      } else {
        localStorage.removeItem('activeChatId')
      }
      return { conversations: filtered, activeId: newActive }
    })
  },

  saveMessage: async (token, convId, role, content) => {
    const data = await apiPost<MsgResponse>(
      `/api/conversations/${convId}/messages`,
      { role, content },
      token
    )
    
    // Sync the message details and the conversation title locally in state
    set((s) => ({
      conversations: s.conversations.map((c) => {
        if (c.id !== convId) return c
        
        let updatedTitle = c.title
        if (role === 'user' && c.messages.filter(m => m.role === 'user').length <= 1) {
          const text = content.trim()
          updatedTitle = text.length > 40 ? text.substring(0, 40) + '…' : text
        }
        
        return {
          ...c,
          title: updatedTitle,
          messages: c.messages.map((m) =>
            m.role === role && !m.id ? { ...m, id: data.id, position: data.position } : m
          ),
        }
      }),
    }))

    return data.id
  },

  updateMessage: async (token, convId, msgId, content) => {
    await apiPatch<MsgResponse>(
      `/api/conversations/${convId}/messages/${msgId}`,
      { role: 'assistant', content },
      token
    )
  },

  addLocalMessage: (convId, msg) => {
    set((s) => ({
      conversations: s.conversations.map((c) => {
        if (c.id !== convId) return c
        return { ...c, messages: [...c.messages, msg] }
      }),
    }))
  },

  updateLocalMessage: (convId, content) => {
    set((s) => ({
      conversations: s.conversations.map((c) => {
        if (c.id !== convId) return c
        const msgs = [...c.messages]
        if (msgs.length > 0 && msgs[msgs.length - 1].role === 'assistant') {
          msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], content }
        }
        return { ...c, messages: msgs }
      }),
    }))
  },

  editLocalUserMessage: (convId, msgIndex, content) => {
    set((s) => ({
      conversations: s.conversations.map((c) => {
        if (c.id !== convId) return c
        const msgs = [...c.messages]
        if (msgs[msgIndex]) {
          msgs[msgIndex] = { ...msgs[msgIndex], content }
        }
        return { ...c, messages: msgs }
      }),
    }))
  },

  truncateLocalMessages: (convId, msgIndex) => {
    set((s) => ({
      conversations: s.conversations.map((c) => {
        if (c.id !== convId) return c
        return { ...c, messages: c.messages.slice(0, msgIndex) }
      }),
    }))
  },

  getActive: () => {
    const { conversations, activeId } = get()
    return conversations.find((c) => c.id === activeId)
  },

  clearAll: () => {
    set({ conversations: [], activeId: null })
  },
}))
