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

export default function RegisterPage() {
  const { theme, toggleTheme } = useThemeStore()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [orgName, setOrgName] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)

  // Google Register + OTP states
  const [googleClientId, setGoogleClientId] = useState<string | null>(null)
  const [showGooglePrompt, setShowGooglePrompt] = useState(false)
  const [googleName, setGoogleName] = useState('')
  const [googleEmail, setGoogleEmail] = useState('')
  const [googleOrgName, setGoogleOrgName] = useState('')
  const [googleError, setGoogleError] = useState('')
  const [googleLoading, setGoogleLoading] = useState(false)
  const [otpSent, setOtpSent] = useState(false)
  const [otpCode, setOtpCode] = useState('')
  const [verificationToken, setVerificationToken] = useState<string | null>(null)
  const [countdown, setCountdown] = useState(300)
  const [resendCooldown, setResendCooldown] = useState(0)
  const [resendAttempts, setResendAttempts] = useState(0)

  useEffect(() => {
    let timer: any = null
    if (otpSent && countdown > 0) {
      timer = setInterval(() => {
        setCountdown((c) => c - 1)
      }, 1000)
    }
    return () => clearInterval(timer)
  }, [otpSent, countdown])

  useEffect(() => {
    let timer: any = null
    if (resendCooldown > 0) {
      timer = setInterval(() => {
        setResendCooldown((c) => c - 1)
      }, 1000)
    }
    return () => clearInterval(timer)
  }, [resendCooldown])

  // Password Setup States for OAuth users
  const [showPasswordSetup, setShowPasswordSetup] = useState(false)
  const [setupPasswordVal, setSetupPasswordVal] = useState('')
  const [tempAccessToken, setTempAccessToken] = useState<string | null>(null)

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
            text: 'signup_with',
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
      const body: Record<string, unknown> = {
        id_token: response.credential
      }
      if (orgName.trim()) {
        body.org_name = orgName.trim()
      }
      const data = await apiPost<{ access_token: string; user_name: string; user_email: string; requires_otp: boolean; verification_token?: string }>('/auth/google', body)
      if (data.requires_otp) {
        setGoogleEmail(data.user_email)
        setVerificationToken(data.verification_token || null)
        setOtpSent(true)
        setCountdown(300)
        setResendCooldown(60)
        setResendAttempts(0)
        setShowGooglePrompt(true)
      } else {
        setAuth(data.access_token, data.user_name, data.user_email)
        navigate('/chat')
      }
    } catch (err: any) {
      setError(err.message || 'Google registration failed')
    } finally {
      setGoogleLoading(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (!name || !email || !password) return setError('All fields are required')
    if (password.length < 8) return setError('Password must be at least 8 characters')

    setLoading(true)
    try {
      const body: Record<string, unknown> = { name, email, password }
      if (orgName.trim()) {
        body.org_name = orgName.trim()
      }
      const data = await apiPost<{ access_token: string; user_name: string; user_email: string; requires_otp: boolean; verification_token?: string }>('/auth/register', body)
      if (data.requires_otp) {
        setVerificationToken(data.verification_token || null)
        setOtpSent(true)
        setCountdown(300)
        setResendCooldown(60)
        setResendAttempts(0)
      } else {
        setAuth(data.access_token, data.user_name, data.user_email)
        navigate('/chat')
      }
    } catch (err: any) {
      setError(err.message || 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  const handleLocalOtpVerify = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (countdown <= 0) return setError('The verification code has expired. Please request a new code.')
    if (!otpCode || otpCode.length !== 6) return setError('Please enter a 6-digit code')

    setLoading(true)
    try {
      const payload: Record<string, any> = { email, code: otpCode }
      if (verificationToken) {
        payload.verification_token = verificationToken
      }
      const data = await apiPost<AuthResponse>('/auth/verify-email-otp', payload)
      setAuth(data.access_token, data.user_name, data.user_email)
      navigate('/chat')
    } catch (err: any) {
      setError(err.message || 'Invalid or expired verification code')
    } finally {
      setLoading(false)
    }
  }

  const handleLocalResendOtp = async () => {
    if (resendCooldown > 0) return
    if (resendAttempts >= 3) {
      setError("Maximum resend attempts exceeded. Please try again later.")
      return
    }
    setError('')
    try {
      await apiPost('/auth/send-verification-otp', { email })
      setResendCooldown(60)
      setResendAttempts(a => a + 1)
      setCountdown(300)
      alert('Verification code resent successfully!')
    } catch (err: any) {
      setError(err.message || 'Resend failed')
    }
  }

  const handleGoogleRegisterSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setGoogleError('')
    if (!googleName || !googleEmail) return setGoogleError('Name and Email are required')

    setGoogleLoading(true)
    try {
      const body: Record<string, unknown> = {
        id_token: `google-id-${googleEmail}`
      }
      if (googleOrgName.trim()) {
        body.org_name = googleOrgName.trim()
      }
      const data = await apiPost<{ access_token: string; user_name: string; user_email: string; requires_otp: boolean; verification_token?: string }>('/auth/google', body)
      if (data.requires_otp) {
        setVerificationToken(data.verification_token || null)
        setOtpSent(true)
        setCountdown(300)
        setResendCooldown(60)
        setResendAttempts(0)
      } else {
        setAuth(data.access_token, data.user_name, data.user_email)
        setShowGooglePrompt(false)
        navigate('/chat')
      }
    } catch (err: any) {
      setGoogleError(err.message || 'Google registration failed to start')
    } finally {
      setGoogleLoading(false)
    }
  }

  const handleGoogleOtpVerify = async (e: React.FormEvent) => {
    e.preventDefault()
    setGoogleError('')

    if (countdown <= 0) {
      setGoogleError("The verification code has expired. Please request a new code.")
      return
    }

    if (!otpCode || otpCode.length !== 6) return setGoogleError('Please enter a 6-digit code')
    const payload: Record<string, any> = { email: googleEmail, code: otpCode }
    if (verificationToken) {
      payload.verification_token = verificationToken
    }

    setGoogleLoading(true)
    try {
      const data = await apiPost<AuthResponse>('/auth/verify-email-otp', payload)
      setTempAccessToken(data.access_token)
      setAuth(data.access_token, data.user_name, data.user_email)
      setVerificationToken(null)
      setShowPasswordSetup(true)
    } catch (err: any) {
      setGoogleError(err.message || 'Invalid or expired verification code')
    } finally {
      setGoogleLoading(false)
    }
  }

  const handleSetupPasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setGoogleError('')
    if (setupPasswordVal.length < 8) {
      return setGoogleError('Password must be at least 8 characters')
    }

    setGoogleLoading(true)
    try {
      await apiPost('/auth/setup-password', { password: setupPasswordVal }, tempAccessToken)
      setShowPasswordSetup(false)
      setShowGooglePrompt(false)
      navigate('/chat')
    } catch (err: any) {
      setGoogleError(err.message || 'Failed to setup password. Please try again.')
    } finally {
      setGoogleLoading(false)
    }
  }

  const handleSkipPasswordSetup = () => {
    setShowPasswordSetup(false)
    setShowGooglePrompt(false)
    navigate('/chat')
  }

  const handleResendOtp = async () => {
    if (resendCooldown > 0) return
    if (resendAttempts >= 3) {
      setGoogleError("Maximum resend attempts exceeded. Please try again later.")
      return
    }
    setGoogleError('')
    try {
      await apiPost('/auth/send-verification-otp', { email: googleEmail })
      setResendCooldown(60)
      setResendAttempts(a => a + 1)
      setCountdown(300)
      alert('Verification code resent successfully!')
    } catch (err: any) {
      setGoogleError(err.message || 'Resend failed')
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
        <h1>{otpSent ? 'Verify Email' : 'Create Account'}</h1>
        <p className="subtitle">
          {otpSent ? `We've sent a 6-digit OTP verification code to ${email}` : 'Get started with InferVoyage'}
        </p>

        {error && <div className="error-msg">{error}</div>}

        {otpSent ? (
          <form onSubmit={handleLocalOtpVerify}>
            <div className="form-group">
              <label htmlFor="localOtpInput">6-Digit Verification Code</label>
              <input
                id="localOtpInput"
                name="otpCode"
                type="text"
                maxLength={6}
                value={otpCode}
                onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, ''))}
                placeholder="123456"
                style={{
                  textAlign: 'center',
                  fontSize: '2rem',
                  letterSpacing: '8px',
                  padding: '10px'
                }}
                required
                autoFocus
              />
            </div>
            <div style={{ display: 'flex', gap: '12px', marginTop: '20px' }}>
              <button type="submit" className="btn" disabled={loading}>
                {loading ? 'Verifying...' : 'Verify & Sign In'}
              </button>
              <button type="button" className="btn btn-secondary" onClick={handleLocalResendOtp}>
                Resend Code
              </button>
              <button type="button" className="btn btn-secondary" onClick={() => setOtpSent(false)}>
                Back
              </button>
            </div>
          </form>
        ) : (
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label htmlFor="name">Full Name</label>
              <input
                id="name"
                name="name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="John Doe"
                autoComplete="name"
              />
            </div>
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
              <label htmlFor="orgName">Organization</label>
              <input
                id="orgName"
                name="orgName"
                type="text"
                value={orgName}
                onChange={(e) => setOrgName(e.target.value)}
                placeholder="Your company or team name (optional)"
                autoComplete="organization"
              />
              <span className="form-hint">Leave blank to join the Default organization</span>
            </div>
            <div className="form-group">
              <label htmlFor="password">Password</label>
              <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                <input
                  id="password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Min. 8 characters"
                  autoComplete="new-password"
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
              {loading ? 'Creating...' : 'Create Account'}
            </button>
          </form>
        )}

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
            onClick={() => {
              setGoogleError('');
              setGoogleName('');
              setGoogleEmail('');
              setGoogleOrgName('');
              setOtpSent(false);
              setOtpCode('');
              setShowGooglePrompt(true);
            }}
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
          Already have an account? <Link to="/login">Sign in</Link>
        </div>
      </div>

      {/* Simulated Google Register & OTP Modal overlay */}
      {showGooglePrompt && (
        <div className="modal-overlay" onClick={() => setShowGooglePrompt(false)}>
          <div 
            className="modal-content auth-card" 
            style={{ maxWidth: '400px', padding: '30px' }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2>Google Registration</h2>
            
            {googleError && <div className="error-msg">{googleError}</div>}
            
            {showPasswordSetup ? (
              <form onSubmit={handleSetupPasswordSubmit}>
                <p className="subtitle">
                  Create a password to sign in using email + password in the future. You can also do this later or skip it now.
                </p>
                <div className="form-group">
                  <label htmlFor="setupPasswordInput">Password (Optional)</label>
                  <input
                    id="setupPasswordInput"
                    name="setupPassword"
                    type="password"
                    value={setupPasswordVal}
                    onChange={(e) => setSetupPasswordVal(e.target.value)}
                    placeholder="Min. 8 characters"
                    minLength={8}
                    required
                    autoFocus
                  />
                </div>
                <div style={{ display: 'flex', gap: '12px', marginTop: '20px' }}>
                  <button type="submit" className="btn" disabled={googleLoading}>
                    {googleLoading ? 'Saving...' : 'Set Password'}
                  </button>
                  <button type="button" className="btn btn-secondary" onClick={handleSkipPasswordSetup}>
                    Skip
                  </button>
                </div>
              </form>
            ) : !otpSent ? (
              <form onSubmit={handleGoogleRegisterSubmit}>
                <p className="subtitle">Set up your workspace under Google Federated Sign-On</p>
                <div className="form-group">
                  <label htmlFor="googleNameInput">Full Name</label>
                  <input
                    id="googleNameInput"
                    name="googleName"
                    type="text"
                    value={googleName}
                    onChange={(e) => setGoogleName(e.target.value)}
                    placeholder="John Doe"
                    autoComplete="name"
                    required
                    autoFocus
                  />
                </div>
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
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="googleOrgInput">Organization (optional)</label>
                  <input
                    id="googleOrgInput"
                    name="googleOrgName"
                    type="text"
                    value={googleOrgName}
                    onChange={(e) => setGoogleOrgName(e.target.value)}
                    placeholder="Company/Team Name"
                    autoComplete="organization"
                  />
                  <span className="form-hint">Leave blank to join the Default organization</span>
                </div>
                <div style={{ display: 'flex', gap: '12px', marginTop: '20px' }}>
                  <button type="submit" className="btn" disabled={googleLoading}>
                    {googleLoading ? 'Sending...' : 'Send Verification OTP'}
                  </button>
                  <button type="button" className="btn btn-secondary" onClick={() => setShowGooglePrompt(false)}>
                    Cancel
                  </button>
                </div>
              </form>
             ) : (
              <form onSubmit={handleGoogleOtpVerify}>
                <p className="subtitle">
                  We've sent a 6-digit OTP verification code to <strong>{googleEmail}</strong>. Please enter it below.
                </p>
                <div className="form-group">
                  <label htmlFor="googleOtpInput">6-Digit Verification Code</label>
                  <input
                    id="googleOtpInput"
                    name="otpCode"
                    type="text"
                    maxLength={6}
                    value={otpCode}
                    onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, ''))}
                    placeholder="123456"
                    style={{
                      textAlign: 'center',
                      fontSize: '2rem',
                      letterSpacing: '8px',
                      padding: '10px'
                    }}
                    required
                    autoFocus
                  />
                </div>
                
                <div style={{ textAlign: 'center', margin: '15px 0', fontSize: '0.9rem', color: 'var(--text-muted)' }}>
                  {countdown > 0 ? (
                    <span>Code expires in <strong style={{ color: 'var(--accent)' }}>{Math.floor(countdown / 60)}:{(countdown % 60).toString().padStart(2, '0')}</strong></span>
                  ) : (
                    <span style={{ color: 'var(--danger)', fontWeight: 'bold' }}>The verification code has expired. Please request a new code.</span>
                  )}
                </div>

                <div style={{ display: 'flex', gap: '12px', marginTop: '20px' }}>
                  <button type="submit" className="btn" disabled={googleLoading || countdown <= 0}>
                    {googleLoading ? 'Verifying...' : 'Verify & Register'}
                  </button>
                  <button 
                    type="button" 
                    className="btn btn-secondary" 
                    onClick={handleResendOtp}
                    disabled={resendCooldown > 0 || resendAttempts >= 3 || googleLoading}
                    style={{ minWidth: '110px' }}
                  >
                    {resendCooldown > 0 
                      ? `Resend (${resendCooldown}s)` 
                      : resendAttempts >= 3 
                        ? 'Resend Locked' 
                        : 'Resend Code'}
                  </button>
                  <button type="button" className="btn btn-secondary" onClick={() => setOtpSent(false)}>
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
