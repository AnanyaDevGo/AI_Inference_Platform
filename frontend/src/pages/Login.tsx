import { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import { useThemeStore } from '../stores/themeStore'
import { apiPost, apiGet } from '../api/client'

interface AuthResponse {
  access_token: string
  user_name: string
  user_email: string
}

declare global {
  interface Window {
    google?: any
  }
}

export default function LoginPage() {
  const { theme, toggleTheme } = useThemeStore()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  
  // Google Auth states
  const [googleClientId, setGoogleClientId] = useState<string | null>(null)
  const [showGooglePrompt, setShowGooglePrompt] = useState(false)
  const [googleEmail, setGoogleEmail] = useState('')
  const [googleError, setGoogleError] = useState('')
  const [googleLoading, setGoogleLoading] = useState(false)

  // Forgot Password states
  const [showForgotPassword, setShowForgotPassword] = useState(false)
  const [forgotEmail, setForgotEmail] = useState('')
  const [forgotOtp, setForgotOtp] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [forgotStep, setForgotStep] = useState<1 | 2>(1)
  const [forgotLoading, setForgotLoading] = useState(false)
  const [forgotError, setForgotError] = useState('')
  const [forgotSuccess, setForgotSuccess] = useState('')
  const [resetToken, setResetToken] = useState<string | null>(null)

  const setAuth = useAuthStore((s) => s.setAuth)
  const navigate = useNavigate()

  // Load Auth Config from Backend
  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const config = await apiGet<{ google_client_id: string | null }>('/auth/config')
        if (config.google_client_id) {
          setGoogleClientId(config.google_client_id)
        }
      } catch (err) {
        console.warn('Failed to fetch auth config', err)
      }
    }
    fetchConfig()
  }, [])

  // Initialize GSI when client ID is available and script is ready
  useEffect(() => {
    if (!googleClientId) return

    const initGoogle = () => {
      if (window.google?.accounts?.id) {
        window.google.accounts.id.initialize({
          client_id: googleClientId,
          callback: handleGoogleCredentialResponse,
        })
        
        const btnContainer = document.getElementById('google-signin-btn')
        if (btnContainer) {
          window.google.accounts.id.renderButton(btnContainer, {
            theme: 'outline',
            size: 'large',
            width: btnContainer.offsetWidth || 320,
            text: 'signin_with',
            shape: 'rectangular',
          })
        }
      }
    }

    const timer = setInterval(() => {
      if (window.google?.accounts?.id) {
        initGoogle()
        clearInterval(timer)
      }
    }, 200)

    return () => clearInterval(timer)
  }, [googleClientId])

  const handleGoogleCredentialResponse = async (response: any) => {
    setGoogleError('')
    setError('')
    setGoogleLoading(true)
    try {
      const data = await apiPost<{ access_token: string; user_name: string; user_email: string; requires_otp: boolean }>('/auth/google', { 
        id_token: response.credential 
      })
      if (data.requires_otp) {
        setError('Account does not exist. Please register first.')
      } else {
        setAuth(data.access_token, data.user_name, data.user_email)
        navigate('/chat')
      }
    } catch (err: any) {
      setError(err.message || 'Google Login failed')
    } finally {
      setGoogleLoading(false)
    }
  }

  const handleForgotPasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setForgotError('')
    if (!forgotEmail) return setForgotError('Email is required')

    setForgotLoading(true)
    try {
      const data = await apiPost<{ success: boolean; message: string; reset_token?: string }>('/auth/forgot-password', { email: forgotEmail })
      if (data.reset_token) {
        setResetToken(data.reset_token)
      } else {
        setResetToken(null)
      }
      setForgotStep(2)
    } catch (err: any) {
      setForgotError(err.message || 'Failed to send reset code')
    } finally {
      setForgotLoading(false)
    }
  }

  const handleResetPasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setForgotError('')

    if (!forgotOtp || forgotOtp.length !== 6) return setForgotError('Please enter the 6-digit code')
    if (!newPassword || newPassword.length < 8) return setForgotError('Password must be at least 8 characters')

    const payload: Record<string, any> = {
      email: forgotEmail,
      new_password: newPassword,
      code: forgotOtp
    }

    if (resetToken) {
      payload.reset_token = resetToken
    }

    setForgotLoading(true)
    try {
      await apiPost('/auth/reset-password', payload)
      setForgotSuccess('Password reset successfully! You can now log in.')
      setEmail(forgotEmail)
      setTimeout(() => {
        setShowForgotPassword(false)
        setForgotStep(1)
        setForgotSuccess('')
        setForgotEmail('')
        setForgotOtp('')
        setNewPassword('')
        setResetToken(null)
      }, 1500)
    } catch (err: any) {
      setForgotError(err.message || 'Password reset failed')
    } finally {
      setForgotLoading(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (!email || !password) return setError('All fields are required')

    setLoading(true)
    try {
      const data = await apiPost<AuthResponse>('/auth/login', { email, password })
      setAuth(data.access_token, data.user_name, data.user_email)
      navigate('/chat')
    } catch (err: any) {
      setError(err.message || 'Invalid email or password')
    } finally {
      setLoading(false)
    }
  }

  const handleGoogleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setGoogleError('')
    if (!googleEmail) return setGoogleError('Google Email is required')

    setGoogleLoading(true)
    try {
      const data = await apiPost<{ access_token: string; user_name: string; user_email: string; requires_otp: boolean }>('/auth/google', { 
        id_token: `google-id-${googleEmail}` 
      })
      if (data.requires_otp) {
        setGoogleError('Account does not exist. Please register first.')
      } else {
        setAuth(data.access_token, data.user_name, data.user_email)
        setShowGooglePrompt(false)
        navigate('/chat')
      }
    } catch (err: any) {
      setGoogleError(err.message || 'Google Login failed')
    } finally {
      setGoogleLoading(false)
    }
  }

  return (
    <div className="auth-wrapper">
      <div 
        style={{
          position: 'absolute',
          top: '20px',
          right: '20px',
          zIndex: 10
        }}
      >
        <button
          onClick={toggleTheme}
          style={{
            background: 'var(--bg-card)',
            border: '1px solid var(--border)',
            color: 'var(--text-primary)',
            fontSize: '18px',
            cursor: 'pointer',
            padding: '10px',
            borderRadius: '50%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            transition: 'all var(--transition)',
            boxShadow: 'var(--shadow-sm)',
            width: '42px',
            height: '42px'
          }}
          onMouseEnter={(e) => { 
            e.currentTarget.style.background = 'var(--bg-input)';
            e.currentTarget.style.borderColor = 'var(--border-hover)';
          }}
          onMouseLeave={(e) => { 
            e.currentTarget.style.background = 'var(--bg-card)';
            e.currentTarget.style.borderColor = 'var(--border)';
          }}
          title={theme === 'dark' ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
        >
          {theme === 'dark' ? '☀️' : '🌙'}
        </button>
      </div>
      <div className="auth-card">
        <h1>Welcome Back</h1>
        <p className="subtitle">Sign in to continue chatting</p>

        {error && <div className="error-msg">{error}</div>}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              name="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              autoComplete="email"
            />
          </div>
          <div className="form-group">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <label htmlFor="password" style={{ margin: 0 }}>Password</label>
              <button 
                type="button" 
                onClick={() => { setForgotError(''); setForgotSuccess(''); setForgotStep(1); setShowForgotPassword(true); }}
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'var(--accent)',
                  cursor: 'pointer',
                  fontSize: '0.85rem',
                  padding: 0,
                  fontWeight: '500'
                }}
              >
                Forgot Password?
              </button>
            </div>
            <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
              <input
                id="password"
                name="password"
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Your password"
                autoComplete="current-password"
                style={{ width: '100%', paddingRight: '40px' }}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                style={{
                  position: 'absolute',
                  right: '10px',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: '1.2rem',
                  color: 'var(--text-muted)'
                }}
                title={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? "👁️‍🗨️" : "👁"}
              </button>
            </div>
          </div>
          <button className="btn" type="submit" disabled={loading}>
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>

        <div className="auth-divider">
          <span>or</span>
        </div>

        {googleClientId ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px' }}>
            <div id="google-signin-btn" style={{ minHeight: '40px', width: '100%', display: 'flex', justifyContent: 'center' }}></div>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Real Federated Google Sign-In Active</span>
          </div>
        ) : (
          <button 
            type="button" 
            className="btn-google"
            onClick={() => { setGoogleError(''); setGoogleEmail(''); setShowGooglePrompt(true); }}
            disabled={loading}
          >
            <svg className="google-icon" viewBox="0 0 24 24" style={{ width: '18px', height: '18px', marginRight: '8px' }}>
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.56-2.77c-.98.66-2.23 1.06-3.72 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"/>
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
            </svg>
            Continue with Google
          </button>
        )}

        <div className="auth-switch">
          Don't have an account? <Link to="/register">Create one</Link>
        </div>
      </div>

      {/* Simulated Google SSO Popup Modal */}
      {showGooglePrompt && (
        <div className="modal-overlay" onClick={() => setShowGooglePrompt(false)}>
          <div 
            className="modal-content auth-card" 
            style={{ maxWidth: '400px', padding: '30px' }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2>Google Sign-In</h2>
            <p className="subtitle">Securely log in with your Google Account</p>
            
            {googleError && <div className="error-msg">{googleError}</div>}
            
            <form onSubmit={handleGoogleLogin}>
              <div className="form-group">
                <label htmlFor="googleEmailInput">Google Email</label>
                <input
                  id="googleEmailInput"
                  name="googleEmail"
                  type="email"
                  value={googleEmail}
                  onChange={(e) => setGoogleEmail(e.target.value)}
                  placeholder="name@gmail.com"
                  autoComplete="email"
                  required
                  autoFocus
                />
              </div>
              <div style={{ display: 'flex', gap: '12px', marginTop: '20px' }}>
                <button type="submit" className="btn" disabled={googleLoading}>
                  {googleLoading ? 'Signing in...' : 'Sign In'}
                </button>
                <button type="button" className="btn btn-secondary" onClick={() => setShowGooglePrompt(false)}>
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Forgot Password Modal */}
      {showForgotPassword && (
        <div className="modal-overlay" onClick={() => setShowForgotPassword(false)}>
          <div 
            className="modal-content auth-card" 
            style={{ maxWidth: '400px', padding: '30px' }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2>Reset Password</h2>
            <p className="subtitle">
              {forgotStep === 1 
                ? 'Enter your email to receive a password reset code' 
                : 'Enter verification code and your new password'}
            </p>
            
            {forgotError && <div className="error-msg">{forgotError}</div>}
            {forgotSuccess && <div style={{ color: 'var(--success)', background: 'rgba(74, 222, 128, 0.08)', padding: '12px', borderRadius: 'var(--radius-sm)', marginBottom: '16px', fontSize: '0.9rem' }}>{forgotSuccess}</div>}
            
            {forgotStep === 1 ? (
              <form onSubmit={handleForgotPasswordSubmit}>
                <div className="form-group">
                  <label htmlFor="forgotEmailInput">Email Address</label>
                  <input
                    id="forgotEmailInput"
                    type="email"
                    value={forgotEmail}
                    onChange={(e) => setForgotEmail(e.target.value)}
                    placeholder="you@example.com"
                    autoComplete="email"
                    required
                    autoFocus
                  />
                </div>
                <div style={{ display: 'flex', gap: '12px', marginTop: '20px' }}>
                  <button type="submit" className="btn" disabled={forgotLoading}>
                    {forgotLoading ? 'Sending...' : 'Send Reset Code'}
                  </button>
                  <button type="button" className="btn btn-secondary" onClick={() => setShowForgotPassword(false)}>
                    Cancel
                  </button>
                </div>
              </form>
            ) : (
              <form onSubmit={handleResetPasswordSubmit}>
                <div className="form-group">
                  <label htmlFor="forgotOtpInput">6-Digit Code</label>
                  <input
                    id="forgotOtpInput"
                    type="text"
                    maxLength={6}
                    value={forgotOtp}
                    onChange={(e) => setForgotOtp(e.target.value.replace(/\D/g, ''))}
                    placeholder="123456"
                    required
                    autoFocus
                  />
                </div>
                <div className="form-group" style={{ marginTop: '16px' }}>
                  <label htmlFor="newPasswordInput">New Password</label>
                  <input
                    id="newPasswordInput"
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="Minimum 8 characters"
                    required
                    autoFocus={!!resetToken}
                  />
                </div>
                <div style={{ display: 'flex', gap: '12px', marginTop: '20px' }}>
                  <button type="submit" className="btn" disabled={forgotLoading}>
                    {forgotLoading ? 'Resetting...' : 'Reset Password'}
                  </button>
                  <button type="button" className="btn btn-secondary" onClick={() => setForgotStep(1)}>
                    Back
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
