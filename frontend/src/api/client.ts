import { useAuthStore } from '../stores/authStore'

const API_BASE = ''  // Same origin — proxied by Nginx in prod, Vite in dev

interface ApiError {
  success: false
  error: { code: string; message: string; request_id?: string }
}

export async function apiPost<T>(
  path: string,
  body: Record<string, unknown>,
  token?: string | null
): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
    credentials: 'include',
  })

  if (!res.ok) {
    if (res.status === 401) {
      useAuthStore.getState().logout()
      window.location.href = '/login'
    }
    const data = (await res.json()) as ApiError
    throw new Error(data.error?.message || `Request failed (${res.status})`)
  }

  return res.json() as Promise<T>
}

export async function apiGet<T>(
  path: string,
  token?: string | null
): Promise<T> {
  const headers: Record<string, string> = {}
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${API_BASE}${path}`, { 
    headers,
    credentials: 'include',
  })

  if (!res.ok) {
    if (res.status === 401) {
      useAuthStore.getState().logout()
      window.location.href = '/login'
    }
    const data = (await res.json()) as ApiError
    throw new Error(data.error?.message || `Request failed (${res.status})`)
  }

  return res.json() as Promise<T>
}

export async function apiDelete(
  path: string,
  token?: string | null
): Promise<void> {
  const headers: Record<string, string> = {}
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${API_BASE}${path}`, { 
    method: 'DELETE', 
    headers,
    credentials: 'include',
  })

  if (!res.ok && res.status !== 204) {
    if (res.status === 401) {
      useAuthStore.getState().logout()
      window.location.href = '/login'
    }
    const data = (await res.json()) as ApiError
    throw new Error(data.error?.message || `Request failed (${res.status})`)
  }
}

export async function apiPatch<T>(
  path: string,
  body: Record<string, unknown>,
  token?: string | null
): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${API_BASE}${path}`, {
    method: 'PATCH',
    headers,
    body: JSON.stringify(body),
    credentials: 'include',
  })

  if (!res.ok) {
    const data = (await res.json()) as ApiError
    throw new Error(data.error?.message || `Request failed (${res.status})`)
  }

  return res.json() as Promise<T>
}

export async function apiStreamPost(
  path: string,
  body: Record<string, unknown>,
  token: string | null,
  onChunk: (content: string) => void,
  onDone: () => void,
  onError: (msg: string) => void
): Promise<void> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
    credentials: 'include',
  })

  if (!res.ok) {
    const data = await res.json()
    onError(data.error?.message || `Request failed (${res.status})`)
    return
  }

  const reader = res.body?.getReader()
  if (!reader) { onError('No response stream'); return }

  const decoder = new TextDecoder()
  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    const chunk = decoder.decode(value, { stream: true })
    for (const line of chunk.split('\n')) {
      if (!line.startsWith('data: ')) continue
      const data = line.slice(6).trim()
      if (data === '[DONE]') { onDone(); return }

      try {
        const parsed = JSON.parse(data)
        const delta = parsed.choices?.[0]?.delta?.content
        if (delta) onChunk(delta)
      } catch { /* skip malformed */ }
    }
  }
  onDone()
}
