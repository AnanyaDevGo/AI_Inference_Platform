import { useAuthStore } from '../stores/authStore'

const API_BASE = ''  // Same origin — proxied by Nginx in prod, Vite in dev

interface ApiError {
  success: false
  error: { code: string; message: string; request_id?: string }
}

/**
 * Perform a fetch request and intercept network/CORS connectivity issues with detailed diagnostics.
 */
async function performFetch(url: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init)
  } catch (err: any) {
    console.error('API connectivity failure:', err)
    let message = 'Network connection failed'
    if (err && err.message) {
      if (err.message.includes('Failed to fetch') || err.name === 'TypeError') {
        message = 'Connection to the backend API failed. This could be due to a CORS origin rejection, an untrusted self-signed SSL/TLS certificate, or the backend service being offline. Please check browser console logs or visit https://localhost/health/diagnostics.'
      } else {
        message = `API connection error: ${err.message}`
      }
    }
    throw new Error(message)
  }
}

/**
 * Handle API responses, parsing JSON error envelopes or falling back to raw text for gateway failures.
 */
async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    if (res.status === 401) {
      useAuthStore.getState().logout()
      window.location.href = '/login'
    }

    let errorMessage = `Request failed (status ${res.status})`
    try {
      const data = (await res.json()) as ApiError
      errorMessage = data.error?.message || errorMessage
    } catch {
      try {
        const text = await res.text()
        errorMessage = `Server Error (${res.status}): ${text.substring(0, 150)}`
      } catch {
        errorMessage = `Server responded with status ${res.status} (no details)`
      }
    }
    throw new Error(errorMessage)
  }

  if (res.status === 204) {
    return {} as T
  }

  return res.json() as Promise<T>
}

export async function apiPost<T>(
  path: string,
  body: Record<string, unknown>,
  token?: string | null
): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await performFetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
    credentials: 'include',
  })

  return handleResponse<T>(res)
}

export async function apiGet<T>(
  path: string,
  token?: string | null
): Promise<T> {
  const headers: Record<string, string> = {}
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await performFetch(`${API_BASE}${path}`, { 
    headers,
    credentials: 'include',
  })

  return handleResponse<T>(res)
}

export async function apiDelete(
  path: string,
  token?: string | null
): Promise<void> {
  const headers: Record<string, string> = {}
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await performFetch(`${API_BASE}${path}`, { 
    method: 'DELETE', 
    headers,
    credentials: 'include',
  })

  await handleResponse<void>(res)
}

export async function apiPatch<T>(
  path: string,
  body: Record<string, unknown>,
  token?: string | null
): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await performFetch(`${API_BASE}${path}`, {
    method: 'PATCH',
    headers,
    body: JSON.stringify(body),
    credentials: 'include',
  })

  return handleResponse<T>(res)
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

  let res: Response
  try {
    res = await performFetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      credentials: 'include',
    })
  } catch (err: any) {
    onError(err.message || 'Streaming connection failed')
    return
  }

  if (!res.ok) {
    let errorMessage = `Streaming failed (${res.status})`
    try {
      const data = await res.json()
      errorMessage = data.error?.message || errorMessage
    } catch {
      try {
        const text = await res.text()
        errorMessage = `Server Error (${res.status}): ${text.substring(0, 150)}`
      } catch {}
    }
    onError(errorMessage)
    return
  }

  const reader = res.body?.getReader()
  if (!reader) { onError('No response stream'); return }

  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      if (buffer.trim()) {
        const line = buffer.trim()
        if (line.startsWith('data: ')) {
          const data = line.slice(6).trim()
          if (data === '[DONE]') { onDone(); return }
          try {
            const parsed = JSON.parse(data)
            const delta = parsed.choices?.[0]?.delta?.content
            if (delta) onChunk(delta)
          } catch {}
        }
      }
      break
    }

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed) continue
      if (!trimmed.startsWith('data: ')) continue
      const data = trimmed.slice(6).trim()
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
