import { create } from 'zustand'

interface AuthState {
  token: string | null
  userName: string | null
  userEmail: string | null
  orgId: string | null
  role: string | null
  setAuth: (token: string, name: string, email: string) => void
  logout: () => void
  isAuthenticated: () => boolean
  isAdmin: () => boolean
}

function decodeJwt(token: string): Record<string, string> {
  try {
    const payload = token.split('.')[1]
    return JSON.parse(atob(payload))
  } catch {
    return {}
  }
}

const savedToken = localStorage.getItem('token')
const savedName = localStorage.getItem('userName')
const savedEmail = localStorage.getItem('userEmail')

let initialOrgId: string | null = null
let initialRole: string | null = null

if (savedToken) {
  const decoded = decodeJwt(savedToken)
  initialOrgId = decoded.org_id || null
  initialRole = decoded.role || null
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: savedToken || null,
  userName: savedName || null,
  userEmail: savedEmail || null,
  orgId: initialOrgId,
  role: initialRole,
  
  setAuth: (token, name, email) => {
    const decoded = decodeJwt(token)
    localStorage.setItem('token', token)
    localStorage.setItem('userName', name)
    localStorage.setItem('userEmail', email)
    set({
      token,
      userName: name,
      userEmail: email,
      orgId: decoded.org_id || null,
      role: decoded.role || null,
    })
  },
  
  logout: () => {
    localStorage.removeItem('token')
    localStorage.removeItem('userName')
    localStorage.removeItem('userEmail')
    localStorage.removeItem('activeChatId')
    set({ token: null, userName: null, userEmail: null, orgId: null, role: null })
  },
  
  isAuthenticated: () => get().token !== null,
  
  isAdmin: () => {
    const role = get().role
    return role === 'platform_admin' || role === 'org_admin'
  },
}))
