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

export const useAuthStore = create<AuthState>((set, get) => ({
  token: null,
  userName: null,
  userEmail: null,
  orgId: null,
  role: null,
  setAuth: (token, name, email) => {
    const decoded = decodeJwt(token)
    set({
      token,
      userName: name,
      userEmail: email,
      orgId: decoded.org_id || null,
      role: decoded.role || null,
    })
  },
  logout: () => set({ token: null, userName: null, userEmail: null, orgId: null, role: null }),
  isAuthenticated: () => get().token !== null,
  isAdmin: () => {
    const role = get().role;
    return role === 'platform_admin' || role === 'org_admin' || role === 'operator'
  },
}))
