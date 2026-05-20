import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import { useThemeStore } from '../stores/themeStore'
import { apiGet, apiPost, apiPatch, apiDelete } from '../api/client'

interface Org { id: string; name: string; slug: string; rate_limit_rpm: number; rate_limit_burst: number; is_active: boolean }
interface UserItem { id: string; org_id: string; name: string; email: string; role: string; is_active: boolean }
interface ApiKeyItem { id: string; org_id: string; name: string; key_prefix: string; is_active: boolean; created_at: string; plaintext_key?: string }
interface UsageSummary { total_requests: number; prompt_tokens: number; completion_tokens: number; total_tokens: number; }

const ROLE_NAMES: Record<string, string> = {
  platform_admin: 'Super Admin',
  org_admin: 'Org Admin',
  operator: 'Team Lead',
  viewer: 'User'
}

type Tab = 'orgs' | 'users' | 'keys' | 'usage'

export default function AdminPage() {
  const { theme, toggleTheme } = useThemeStore()
  const role = useAuthStore(s => s.role)
  const isPlatformAdmin = role === 'platform_admin'
  const [tab, setTab] = useState<Tab>(isPlatformAdmin ? 'orgs' : 'users')
  const token = useAuthStore(s => s.token)
  const userName = useAuthStore(s => s.userName)
  const logout = useAuthStore(s => s.logout)
  const navigate = useNavigate()

  const initials = (userName || 'A').charAt(0).toUpperCase()

  return (
    <div className="admin-layout">
      <header className="admin-header">
        <div className="header-left">
          <button className="btn-back" onClick={() => navigate('/chat')} title="Back to Chat">â† Chat</button>
          <div className="logo">
            <div className="logo-icon">âš™</div>
            <span className="logo-text">Admin Panel</span>
          </div>
          <span className="role-badge">{ROLE_NAMES[role || 'viewer']}</span>
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
            {theme === 'dark' ? 'â˜€ï¸' : 'ðŸŒ™'}
          </button>
          <div className="user-info">
            <div className="user-avatar">{initials}</div>
            <span className="user-name">{userName}</span>
          </div>
          <button className="btn-logout" onClick={() => { logout(); navigate('/login') }}>Sign Out</button>
        </div>
      </header>

      <div className="admin-tabs">
        {isPlatformAdmin && (
          <button className={`admin-tab ${tab === 'orgs' ? 'active' : ''}`} onClick={() => setTab('orgs')}>
            Organizations
          </button>
        )}
        <button className={`admin-tab ${tab === 'users' ? 'active' : ''}`} onClick={() => setTab('users')}>
          Users
        </button>
        <button className={`admin-tab ${tab === 'keys' ? 'active' : ''}`} onClick={() => setTab('keys')}>
          API Keys
        </button>
        <button className={`admin-tab ${tab === 'usage' ? 'active' : ''}`} onClick={() => setTab('usage')}>
          Usage
        </button>
      </div>

      <div className="admin-content">
        {tab === 'orgs' && isPlatformAdmin && <OrgsTab token={token} />}
        {tab === 'users' && <UsersTab token={token} isPlatformAdmin={isPlatformAdmin} />}
        {tab === 'keys' && <KeysTab token={token} />}
        {tab === 'usage' && <UsageTab token={token} />}
      </div>
    </div>
  )
}

// â”€â”€ Orgs Tab â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function OrgsTab({ token }: { token: string | null }) {
  const [orgs, setOrgs] = useState<Org[]>([])
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ name: '', slug: '', rate_limit_rpm: 60, rate_limit_burst: 10 })
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    if (!token) return
    try {
      const data = await apiGet<Org[]>('/admin/orgs', token)
      setOrgs(data)
    } catch { /* */ }
  }, [token])

  useEffect(() => { load() }, [load])

  const create = async () => {
    setError('')
    try {
      await apiPost('/admin/orgs', form as unknown as Record<string, unknown>, token)
      setShowCreate(false)
      setForm({ name: '', slug: '', rate_limit_rpm: 60, rate_limit_burst: 10 })
      load()
    } catch (e: any) { setError(e.message) }
  }

  const updateOrg = async (id: string, data: Partial<Org>) => {
    try {
      await apiPatch(`/admin/orgs/${id}`, data as Record<string, unknown>, token)
      load()
    } catch { /* */ }
  }

  const deleteOrg = async (id: string) => {
    if (!window.confirm("Are you sure you want to delete this organization? This is irreversible.")) return
    setError('')
    try {
      await apiDelete(`/admin/orgs/${id}`, token)
      load()
    } catch (e: any) {
      setError(e.message || 'Failed to delete organization')
    }
  }

  return (
    <div className="admin-section">
      <div className="section-header">
        <h2>Organizations</h2>
        <button className="btn-primary-sm" onClick={() => setShowCreate(!showCreate)}>
          {showCreate ? 'Cancel' : '+ New Org'}
        </button>
      </div>

      {error && <div className="error-msg" style={{ marginBottom: '16px' }}>{error}</div>}

      {showCreate && (
        <div className="create-form">
          {error && <div className="error-msg">{error}</div>}
          <div className="form-row">
            <input placeholder="Org Name" value={form.name} onChange={e => setForm({...form, name: e.target.value})} />
            <input placeholder="slug" value={form.slug} onChange={e => setForm({...form, slug: e.target.value})} />
          </div>
          <div className="form-row">
            <input type="number" placeholder="RPM" value={form.rate_limit_rpm} onChange={e => setForm({...form, rate_limit_rpm: +e.target.value})} />
            <input type="number" placeholder="Burst" value={form.rate_limit_burst} onChange={e => setForm({...form, rate_limit_burst: +e.target.value})} />
            <button className="btn-primary-sm" onClick={create}>Create</button>
          </div>
        </div>
      )}

      <table className="admin-table">
        <thead>
          <tr><th>Name</th><th>Slug</th><th>RPM</th><th>Burst</th><th>Active</th><th>Actions</th></tr>
        </thead>
        <tbody>
          {orgs.map(o => (
            <tr key={o.id}>
              <td>{o.name}</td>
              <td><code>{o.slug}</code></td>
              <td>{o.rate_limit_rpm}</td>
              <td>{o.rate_limit_burst}</td>
              <td><span className={`status-dot ${o.is_active ? 'active' : 'inactive'}`} /></td>
              <td>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button className="btn-sm" onClick={() => updateOrg(o.id, { is_active: !o.is_active })}>
                    {o.is_active ? 'Disable' : 'Enable'}
                  </button>
                  <button className="btn-sm btn-danger" onClick={() => deleteOrg(o.id)}>
                    Delete
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// â”€â”€ Users Tab â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function UsersTab({ token, isPlatformAdmin }: { token: string | null; isPlatformAdmin: boolean }) {
  const [users, setUsers] = useState<UserItem[]>([])
  const [orgs, setOrgs] = useState<Org[]>([])
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ name: '', email: '', password: '', role: 'viewer', org_id: '' })
  const [error, setError] = useState('')
  const orgId = useAuthStore(s => s.orgId)

  const load = useCallback(async () => {
    if (!token) return
    try {
      const data = await apiGet<UserItem[]>('/admin/users', token)
      setUsers(data)
    } catch { /* */ }
  }, [token])

  const loadOrgs = useCallback(async () => {
    if (!token || !isPlatformAdmin) return
    try {
      const data = await apiGet<Org[]>('/admin/orgs', token)
      setOrgs(data)
      if (data.length > 0) {
        setForm(f => ({ ...f, org_id: data[0].id }))
      }
    } catch { /* */ }
  }, [token, isPlatformAdmin])

  useEffect(() => { load() }, [load])
  useEffect(() => { loadOrgs() }, [loadOrgs])

  const createUser = async () => {
    setError('')
    try {
      const body = { 
        ...form, 
        org_id: isPlatformAdmin ? (form.org_id || orgs[0]?.id || '') : orgId 
      }
      await apiPost('/admin/users', body, token)
      setShowCreate(false)
      setForm({ name: '', email: '', password: '', role: 'viewer', org_id: orgs[0]?.id || '' })
      load()
    } catch (e: any) { setError(e.message) }
  }

  const updateRole = async (userId: string, role: string) => {
    try {
      await apiPatch(`/admin/users/${userId}`, { role } as Record<string, unknown>, token)
      load()
    } catch { /* */ }
  }

  const toggleActive = async (userId: string, isActive: boolean) => {
    try {
      await apiPatch(`/admin/users/${userId}`, { is_active: !isActive } as Record<string, unknown>, token)
      load()
    } catch { /* */ }
  }

  const deleteUser = async (userId: string) => {
    if (!window.confirm("Are you sure you want to delete this user? This is irreversible.")) return
    setError('')
    try {
      await apiDelete(`/admin/users/${userId}`, token)
      load()
    } catch (e: any) {
      setError(e.message || 'Failed to delete user')
    }
  }

  return (
    <div className="admin-section">
      <div className="section-header">
        <h2>Users</h2>
        <button className="btn-primary-sm" onClick={() => setShowCreate(!showCreate)}>
          {showCreate ? 'Cancel' : '+ Invite User'}
        </button>
      </div>

      {error && <div className="error-msg" style={{ marginBottom: '16px' }}>{error}</div>}

      {showCreate && (
        <div className="create-form">
          {error && <div className="error-msg">{error}</div>}
          <div className="form-row">
            <input placeholder="Name" value={form.name} onChange={e => setForm({...form, name: e.target.value})} />
            <input placeholder="Email" type="email" value={form.email} onChange={e => setForm({...form, email: e.target.value})} />
            <input placeholder="Password" type="password" value={form.password} onChange={e => setForm({...form, password: e.target.value})} />
          </div>
          <div className="form-row">
            <select value={form.role} onChange={e => setForm({...form, role: e.target.value})} className="role-select">
              <option value="viewer">User</option>
              <option value="operator">Team Lead</option>
              <option value="org_admin">Org Admin</option>
            </select>
            {isPlatformAdmin && orgs.length > 0 && (
               <select value={form.org_id} onChange={e => setForm({...form, org_id: e.target.value})} className="role-select">
                 {orgs.map(o => (
                   <option key={o.id} value={o.id}>{o.name}</option>
                 ))}
               </select>
            )}
            <button className="btn-primary-sm" onClick={createUser} disabled={!form.name || !form.email || !form.password}>Create</button>
          </div>
        </div>
      )}
      <table className="admin-table">
        <thead>
          <tr><th>Name</th><th>Email</th><th>Role</th><th>Active</th><th>Actions</th></tr>
        </thead>
        <tbody>
          {users.map(u => (
            <tr key={u.id}>
              <td>{u.name}</td>
              <td>{u.email}</td>
              <td>
                <select
                  value={u.role}
                  onChange={e => updateRole(u.id, e.target.value)}
                  className="role-select"
                >
                  {isPlatformAdmin && <option value="platform_admin">Super Admin</option>}
                  <option value="org_admin">Org Admin</option>
                  <option value="operator">Team Lead</option>
                  <option value="viewer">User</option>
                </select>
              </td>
              <td><span className={`status-dot ${u.is_active ? 'active' : 'inactive'}`} /></td>
              <td>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button className="btn-sm" onClick={() => toggleActive(u.id, u.is_active)}>
                    {u.is_active ? 'Deactivate' : 'Activate'}
                  </button>
                  <button className="btn-sm btn-danger" onClick={() => deleteUser(u.id)}>
                    Delete
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// â”€â”€ API Keys Tab â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function KeysTab({ token }: { token: string | null }) {
  const [keys, setKeys] = useState<ApiKeyItem[]>([])
  const [newKeyName, setNewKeyName] = useState('')
  const [createdKey, setCreatedKey] = useState<string | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    if (!token) return
    try {
      const data = await apiGet<ApiKeyItem[]>('/admin/api-keys', token)
      setKeys(data)
    } catch { /* */ }
  }, [token])

  useEffect(() => { load() }, [load])

  const create = async () => {
    setError('')
    setCreatedKey(null)
    try {
      const data = await apiPost<ApiKeyItem>('/admin/api-keys', { name: newKeyName }, token)
      setCreatedKey(data.plaintext_key || null)
      setNewKeyName('')
      load()
    } catch (e: any) { setError(e.message) }
  }

  const revoke = async (id: string) => {
    if (!window.confirm("Revoke this key?")) return
    try {
      await apiDelete(`/admin/api-keys/${id}`, token)
      load()
    } catch { /* */ }
  }

  const rotate = async (id: string) => {
    if (!window.confirm("Rotate this key? The old key will immediately stop working.")) return
    setCreatedKey(null)
    setError('')
    try {
      const data = await apiPost<ApiKeyItem>(`/admin/api-keys/${id}/rotate`, {}, token)
      setCreatedKey(data.plaintext_key || null)
      load()
    } catch (e: any) { setError(e.message) }
  }

  return (
    <div className="admin-section">
      <div className="section-header">
        <h2>API Keys</h2>
      </div>

      <div className="create-form">
        {error && <div className="error-msg">{error}</div>}
        <div className="form-row">
          <input placeholder="Key name (e.g. Production)" value={newKeyName} onChange={e => setNewKeyName(e.target.value)} />
          <button className="btn-primary-sm" onClick={create} disabled={!newKeyName.trim()}>Create Key</button>
        </div>
      </div>

      {createdKey && (
        <div className="key-created-banner">
          <strong>âš  Save this key â€” it won't be shown again!</strong>
          <code className="key-display">{createdKey}</code>
          <button className="btn-sm" onClick={() => { navigator.clipboard.writeText(createdKey); }}>Copy</button>
        </div>
      )}

      <table className="admin-table">
        <thead>
          <tr><th>Name</th><th>Prefix</th><th>Active</th><th>Created</th><th>Actions</th></tr>
        </thead>
        <tbody>
          {keys.map(k => (
            <tr key={k.id}>
              <td>{k.name}</td>
              <td><code>{k.key_prefix}...</code></td>
              <td><span className={`status-dot ${k.is_active ? 'active' : 'inactive'}`} /></td>
              <td>{new Date(k.created_at).toLocaleDateString()}</td>
              <td>
                {k.is_active && (
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button className="btn-sm" onClick={() => rotate(k.id)}>Rotate</button>
                    <button className="btn-sm btn-danger" onClick={() => revoke(k.id)}>Revoke</button>
                  </div>
                )}
              </td>
            </tr>
          ))}
          {keys.length === 0 && (
            <tr><td colSpan={5} className="empty-row">No API keys yet</td></tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

// â”€â”€ Usage Tab â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

interface DailyUsageItem {
  date: string
  requests: number
  tokens: number
}

function UsageTab({ token }: { token: string | null }) {
  const [summary, setSummary] = useState<UsageSummary | null>(null)
  const [daily, setDaily] = useState<DailyUsageItem[]>([])
  const [chartMetric, setChartMetric] = useState<'requests' | 'tokens'>('requests')
  const [hoveredPoint, setHoveredPoint] = useState<any | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!token) return
    setLoading(true)
    setError(null)
    try {
      const [sumData, dailyData] = await Promise.all([
        apiGet<UsageSummary>('/admin/usage/summary', token),
        apiGet<DailyUsageItem[]>('/admin/usage/daily', token),
      ])
      setSummary(sumData)
      setDaily(dailyData)
    } catch (err: any) {
      setError(err?.message || 'Failed to load usage data')
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => { load() }, [load])

  if (loading) return (
    <div className="admin-section" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '300px', gap: '12px', color: 'var(--text-muted)' }}>
      <span style={{ fontSize: '1.5rem', animation: 'spin 1s linear infinite' }}>âŸ³</span>
      Loading usage dataâ€¦
    </div>
  )

  if (error) return (
    <div className="admin-section" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '300px', gap: '16px' }}>
      <div style={{ color: 'var(--error)', fontSize: '2rem' }}>âš ï¸</div>
      <div style={{ color: 'var(--error)', fontWeight: '600' }}>Failed to load usage data</div>
      <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>{error}</div>
      <button className="btn-primary-sm" onClick={load}>Retry</button>
    </div>
  )

  // SVG Chart Dimensions
  const width = 600
  const height = 240
  const padding = 40

  // Calculate points
  const maxVal = Math.max(...daily.map(d => d[chartMetric]), 10)
  
  const points = daily.map((d, index) => {
    const x = padding + (index / (daily.length - 1 || 1)) * (width - padding * 2)
    const y = height - padding - (d[chartMetric] / maxVal) * (height - padding * 2)
    return { x, y, ...d }
  })

  const pathD = points.length > 0 
    ? `M ${points[0].x} ${points[0].y} ` + points.slice(1).map(p => `L ${p.x} ${p.y}`).join(' ')
    : ''

  const areaD = points.length > 0
    ? `${pathD} L ${points[points.length - 1].x} ${height - padding} L ${points[0].x} ${height - padding} Z`
    : ''

  return (
    <div className="admin-section" style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div className="section-header">
        <h2>Usage Summary</h2>
        <button className="btn-primary-sm" onClick={load} title="Refresh data" style={{ minWidth: '90px' }}>â†» Refresh</button>
      </div>

      <div className="usage-stats-grid">
        <div className="stat-card">
          <div className="stat-label">Total Requests</div>
          <div className="stat-value">{summary!.total_requests.toLocaleString()}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Total Tokens</div>
          <div className="stat-value">{summary!.total_tokens.toLocaleString()}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Prompt Tokens</div>
          <div className="stat-value">{summary!.prompt_tokens.toLocaleString()}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Completion Tokens</div>
          <div className="stat-value">{summary!.completion_tokens.toLocaleString()}</div>
        </div>
      </div>

      {/* SVG Chart Container */}
      <div className="stat-card" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '1.1rem', color: 'var(--text-primary)' }}>Usage History</h3>
            <p style={{ margin: '4px 0 0 0', fontSize: '0.8rem', color: 'var(--text-muted)' }}>Daily breakdown for the last 15 days</p>
          </div>
          <div className="btn-group" style={{ display: 'flex', background: 'var(--bg-input)', padding: '4px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
            <button
              onClick={() => setChartMetric('requests')}
              style={{
                background: chartMetric === 'requests' ? 'var(--accent)' : 'none',
                color: chartMetric === 'requests' ? '#ffffff' : 'var(--text-primary)',
                border: 'none',
                padding: '6px 12px',
                borderRadius: '4px',
                fontSize: '0.8rem',
                fontWeight: '500',
                cursor: 'pointer',
                transition: 'all var(--transition)'
              }}
            >
              Requests
            </button>
            <button
              onClick={() => setChartMetric('tokens')}
              style={{
                background: chartMetric === 'tokens' ? 'var(--accent)' : 'none',
                color: chartMetric === 'tokens' ? '#ffffff' : 'var(--text-primary)',
                border: 'none',
                padding: '6px 12px',
                borderRadius: '4px',
                fontSize: '0.8rem',
                fontWeight: '500',
                cursor: 'pointer',
                transition: 'all var(--transition)'
              }}
            >
              Tokens
            </button>
          </div>
        </div>

        <div style={{ position: 'relative', width: '100%' }}>
          {daily.every(d => d[chartMetric] === 0) ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '200px', gap: '10px', color: 'var(--text-muted)' }}>
              <div style={{ fontSize: '2.5rem' }}>ðŸ“Š</div>
              <div style={{ fontWeight: '600', fontSize: '0.95rem', color: 'var(--text-secondary)' }}>No usage data yet</div>
              <div style={{ fontSize: '0.8rem' }}>Send some chat messages to see data appear here</div>
            </div>
          ) : (
            <>
              <svg viewBox={`0 0 ${width} ${height}`} style={{ width: '100%', height: 'auto', display: 'block', overflow: 'visible' }}>
                {[0, 0.25, 0.5, 0.75, 1].map((ratio, index) => {
                  const y = padding + ratio * (height - padding * 2)
                  const val = Math.round(maxVal - ratio * maxVal)
                  return (
                    <g key={index}>
                      <line x1={padding} y1={y} x2={width - padding} y2={y} stroke="var(--border)" strokeWidth="1" strokeDasharray="4 4" />
                      <text x={padding - 10} y={y + 4} fill="var(--text-muted)" fontSize="10" textAnchor="end">{val.toLocaleString()}</text>
                    </g>
                  )
                })}
                {areaD && <path d={areaD} fill="url(#chartGradient)" opacity="0.15" />}
                {pathD && <path d={pathD} fill="none" stroke="var(--accent)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />}
                <defs>
                  <linearGradient id="chartGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--accent)" />
                    <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
                  </linearGradient>
                </defs>
                {points.map((p, index) => (
                  <circle
                    key={index}
                    cx={p.x}
                    cy={p.y}
                    r={hoveredPoint?.date === p.date ? 6 : 4}
                    fill={hoveredPoint?.date === p.date ? 'var(--accent)' : 'var(--bg-card)'}
                    stroke="var(--accent)"
                    strokeWidth="2"
                    style={{ cursor: 'pointer', transition: 'all 0.1s' }}
                    onMouseEnter={() => setHoveredPoint(p)}
                    onMouseLeave={() => setHoveredPoint(null)}
                  />
                ))}
                {points.length > 0 && (
                  <>
                    <text x={points[0].x} y={height - padding + 18} fill="var(--text-muted)" fontSize="10" textAnchor="middle">
                      {new Date(points[0].date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                    </text>
                    <text x={points[Math.floor(points.length / 2)].x} y={height - padding + 18} fill="var(--text-muted)" fontSize="10" textAnchor="middle">
                      {new Date(points[Math.floor(points.length / 2)].date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                    </text>
                    <text x={points[points.length - 1].x} y={height - padding + 18} fill="var(--text-muted)" fontSize="10" textAnchor="middle">
                      {new Date(points[points.length - 1].date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                    </text>
                  </>
                )}
              </svg>
              {hoveredPoint && (
                <div style={{
                  position: 'absolute',
                  left: `${(hoveredPoint.x / width) * 100}%`,
                  top: `${(hoveredPoint.y / height) * 100 - 15}%`,
                  transform: 'translate(-50%, -100%)',
                  background: 'var(--bg-secondary)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '8px 12px',
                  boxShadow: 'var(--shadow-md)',
                  fontSize: '0.8rem',
                  color: 'var(--text-primary)',
                  pointerEvents: 'none',
                  zIndex: 10,
                  whiteSpace: 'nowrap',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '2px'
                }}>
                  <span style={{ fontWeight: '600' }}>
                    {new Date(hoveredPoint.date).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}
                  </span>
                  <span style={{ color: 'var(--accent)', fontWeight: '700' }}>
                    {hoveredPoint[chartMetric].toLocaleString()} {chartMetric}
                  </span>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

