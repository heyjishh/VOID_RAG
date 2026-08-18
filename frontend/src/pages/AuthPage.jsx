import { useState } from 'react'
import { sendOtp, verifyOtp, login, register, reset } from '../lib/session.js'
import LegalFlick from '../components/LegalFlick.jsx'

/* ────────────────────────────────────────────────────────────────────────────
   AUTH DOCKET — brutalist split panel.
   Left: the Constitution desk (interactive volume, turns with a click),
   case-file masthead, stamps.
   Right: the intake form — LOG IN and CREATE ACCOUNT on the same page,
   email-or-mobile access, OTP signup, OTP login, password login,
   forgot → OTP → new password. Dev OTPs surface as stamps.
   ──────────────────────────────────────────────────────────────────────────── */

const FIELD_STYLE = {
  width: '100%',
  padding: '10px 12px',
  fontSize: 13,
  background: 'var(--bg-soft)',
  color: 'var(--text-primary)',
  border: '1px solid var(--border-default)',
  borderRadius: 2,
  outline: 'none',
  fontFamily: 'var(--font-mono)',
  transition: 'border-color var(--dur-fast) var(--ease-out)',
}

const LABEL_STYLE = {
  display: 'block',
  fontSize: 10,
  fontWeight: 700,
  letterSpacing: '0.12em',
  textTransform: 'uppercase',
  color: 'var(--text-secondary)',
  marginBottom: 6,
  fontFamily: 'var(--font-mono)',
}

const stamp = {
  border: '1px dashed var(--border-strong)',
  borderRadius: 2,
  padding: '4px 8px',
  fontSize: 10,
  fontFamily: 'var(--font-mono)',
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  color: 'var(--text-secondary)',
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
  background: 'transparent',
}

function Field({ label, type = 'text', value, onChange, placeholder, autoComplete }) {
  return (
    <label className="block">
      <span style={LABEL_STYLE}>{label}</span>
      <input
        type={type}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete={autoComplete}
        style={FIELD_STYLE}
        onFocus={e => { e.currentTarget.style.borderColor = 'var(--primary)' }}
        onBlur={e => { e.currentTarget.style.borderColor = 'var(--border-default)' }}
      />
    </label>
  )
}

function ErrorStamp({ message }) {
  if (!message) return null
  return (
    <div
      style={{
        border: '1px solid var(--primary)',
        background: 'var(--bg-card)',
        color: 'var(--blood, var(--primary))',
        borderRadius: 2,
        padding: '8px 10px',
        fontSize: 12,
        fontFamily: 'var(--font-mono)',
        textTransform: 'uppercase',
        letterSpacing: '0.04em',
      }}
    >
      ✗ {message}
    </div>
  )
}

function DevOtpStamp({ devOtp }) {
  if (!devOtp) return null
  return (
    <div
      style={{
        marginTop: 10,
        border: '1px dashed var(--gold)',
        borderRadius: 2,
        padding: '8px 10px',
        fontSize: 12,
        fontFamily: 'var(--font-mono)',
        letterSpacing: '0.1em',
        color: 'var(--text-secondary)',
        textTransform: 'uppercase',
      }}
    >
      DEV CODE <span style={{ color: 'var(--gold)', fontWeight: 700 }}>{devOtp}</span>
    </div>
  )
}

function PrimaryButton({ busy, children, ...rest }) {
  return (
    <button
      type="submit"
      disabled={busy}
      {...rest}
      style={{
        width: '100%',
        padding: '11px 14px',
        fontSize: 13,
        fontWeight: 700,
        fontFamily: 'var(--font-mono)',
        letterSpacing: '0.08em',
        textTransform: 'uppercase',
        background: 'var(--primary)',
        color: 'var(--on-primary)',
        border: '1px solid var(--ink)',
        borderRadius: 2,
        boxShadow: '3px 3px 0 var(--ink)',
        cursor: busy ? 'wait' : 'pointer',
        transition: 'transform var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast) var(--ease-out), background var(--dur-fast) var(--ease-out)',
      }}
      onMouseEnter={e => { if (!busy) { e.currentTarget.style.transform = 'translate(1px, 1px)'; e.currentTarget.style.boxShadow = '1px 1px 0 var(--ink)' } }}
      onMouseLeave={e => { e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = '3px 3px 0 var(--ink)' }}
    >
      {busy ? '…' : children}
    </button>
  )
}

function BrandPanel() {
  return (
    <div
      className="hidden lg:flex flex-col relative overflow-hidden flex-1"
      style={{ borderRight: '1px solid var(--border-strong)', background: 'var(--bg-card)' }}
    >
      <div className="flex items-center justify-between px-8 pt-7">
        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 flex items-center justify-center"
            style={{ background: 'var(--primary)', border: '1px solid var(--ink)', borderRadius: 2, boxShadow: '2px 2px 0 var(--ink)' }}
          >
            <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="var(--on-primary)" strokeWidth="2">
              <path d="M12 3v18M5 7l7-4 7 4M5 17l7 4 7-4" strokeLinecap="round" strokeLinejoin="round" />
              <circle cx="12" cy="12" r="2.5" fill="var(--on-primary)" stroke="none" />
            </svg>
          </div>
          <span style={{ fontFamily: 'var(--font-display)', fontSize: 19, fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '0.01em' }}>
            Juris AI
          </span>
        </div>
        <span style={stamp}>FILE NO. AUTH-2026</span>
      </div>

      <div className="relative flex-1 min-h-0 mx-8 mt-6" style={{ border: '1px solid var(--border-default)', background: 'radial-gradient(ellipse 70% 45% at 50% 58%, rgba(193,18,31,0.16), transparent 70%)' }}>
        <LegalFlick variant="full" className="absolute inset-0" />
        <div className="absolute left-3 top-3" style={stamp}>LEGAL RESEARCH SYSTEM</div>
        <div className="absolute right-3 bottom-3" style={stamp}>STATUTE · PRECEDENT · CITATION</div>
      </div>

      <div className="px-8 pb-8 pt-5">
        <p style={{ margin: 0, fontSize: 11, fontFamily: 'var(--font-mono)', letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--gold)' }}>
          Legal research workspace
        </p>
        <h1 style={{ margin: '8px 0 0', fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 27, lineHeight: 1.22, letterSpacing: '-0.015em', color: 'var(--text-primary)' }}>
          The advocate’s terminal for grounded, citable answers.
        </h1>
        <div className="flex items-center gap-3 mt-5">
          <span style={{ width: 7, height: 7, background: 'var(--sage)', display: 'inline-block' }} />
          <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
            OTP + SESSION AUTH · GROUNDEDNESS GATE ACTIVE
          </span>
        </div>
      </div>
    </div>
  )
}

export default function AuthPage({ mode, onAuthed, onSwitchMode }) {
  const [tab, setTab] = useState('email')                 // access channel
  const [intent, setIntent] = useState(mode === 'signup' ? 'signup' : 'login')
  const [step, setStep] = useState('creds')               // creds | otp | newpwd
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [name, setName] = useState('')
  const [org, setOrg] = useState('')
  const [password, setPassword] = useState('')
  const [otp, setOtp] = useState('')
  const [devOtp, setDevOtp] = useState(null)
  const [masked, setMasked] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [resetPending, setResetPending] = useState(false)

  const targetPayload = () => (tab === 'email' ? { via: 'email', email: email.trim() } : { via: 'phone', phone: phone.trim() })

  async function run(fn) {
    setError('')
    setBusy(true)
    try {
      return await fn()
    } catch (err) {
      setError(err.message || 'Request failed.')
      return null
    } finally {
      setBusy(false)
    }
  }

  async function handleSendCode() {
    const target = tab === 'email' ? email.trim() : phone.trim()
    if (!target) { setError('Enter a valid target first.'); return }
    const res = await run(() => sendOtp({ ...targetPayload(), intent, name: intent === 'signup' ? (name || undefined) : undefined }))
    if (!res) return
    setMasked(res.target || target)
    if (res.dev_otp) setDevOtp(res.dev_otp)
    else setDevOtp(null)
    setStep('otp')
  }

  async function handleVerifyOtp() {
    if (otp.trim().length < 4) { setError('Enter the code received.'); return }
    const payload = { ...targetPayload(), otp: otp.trim(), intent }
    if (intent === 'signup') {
      if (!password) { setError('Set a password (min 6 characters).'); return }
      payload.password = password
      if (name) payload.name = name
    }
    const res = await run(() => verifyOtp(payload))
    if (!res) return
    if (res.user) { onAuthed(res.user); return }
    setStep('newpwd')
  }

  async function handlePasswordLogin(e) {
    e.preventDefault()
    if (!email.trim() || !password) { setError('Email and password are required.'); return }
    const res = await run(() => login({ email: email.trim(), password }))
    if (res?.user) onAuthed(res.user)
  }

  async function handleRegisterDirect() {
    if (!password) { setError('Set a password (min 6 characters).'); return }
    const res = await run(() => register({ name: name || 'Researcher', email: tab === 'email' ? email.trim() : undefined, phone: tab === 'phone' ? phone.trim() : undefined, password }))
    if (res?.user) onAuthed(res.user)
  }

  async function handleNewPassword() {
    if (!password || password.length < 6) { setError('Password must be at least 6 characters.'); return }
    if (!otp.trim()) { setError('Enter the code received.'); return }
    const res = await run(() => reset({ ...targetPayload(), otp: otp.trim(), new_password: password }))
    if (res?.user) onAuthed(res.user)
  }

  const atCreds = step === 'creds'
  const atOtp = step === 'otp'
  const atNewPwd = step === 'newpwd'
  const isSignup = intent === 'signup'
  const isReset = intent === 'reset'

  function switchMode(m) {
    setIntent(m === 'signup' ? 'signup' : 'login')
    setStep('creds')
    setOtp('')
    setDevOtp(null)
    setError('')
    onSwitchMode(m)
  }

  return (
    <div className="h-screen flex overflow-hidden" style={{ background: 'var(--bg-main)' }}>
      <BrandPanel />

      <div className="flex-1 flex items-center justify-center p-6 overflow-auto">
        <div className="w-full max-w-[430px] my-auto">
          <LegalFlick variant="compact" className="lg:hidden h-44 mx-auto mb-4" style={{ maxWidth: 320 }} />

          <div style={{ border: '1px solid var(--border-strong)', borderRadius: 3, background: 'var(--bg-card)' }}>
            <div className="flex items-center justify-between px-6 pt-5">
              <span style={stamp}>{isReset ? 'RESET DOCKET' : isSignup ? 'SIGNUP DOCKET' : 'LOGIN DOCKET'}</span>
              <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>ENCRYPTED CHANNEL</span>
            </div>

            <div className="px-6 pt-4">
              {!isReset && (
                <div className="flex" style={{ border: '1px solid var(--border-strong)', borderRadius: 2, overflow: 'hidden', width: 'fit-content' }}>
                  {[
                    { v: 'login', label: 'LOG IN' },
                    { v: 'signup', label: 'CREATE ACCOUNT' },
                  ].map(m => (
                    <button
                      key={m.v}
                      type="button"
                      onClick={() => switchMode(m.v)}
                      style={{
                        padding: '7px 16px',
                        fontSize: 11,
                        fontFamily: 'var(--font-mono)',
                        letterSpacing: '0.08em',
                        textTransform: 'uppercase',
                        background: intent === m.v ? 'var(--primary)' : 'transparent',
                        color: intent === m.v ? 'var(--on-primary)' : 'var(--text-secondary)',
                        border: 'none',
                        cursor: 'pointer',
                        fontWeight: 700,
                      }}
                    >
                      {m.label}
                    </button>
                  ))}
                </div>
              )}

              {!isReset && (
                <div className="flex mt-3" style={{ border: '1px solid var(--border-default)', borderRadius: 2, overflow: 'hidden', width: 'fit-content' }}>
                  {['email', 'phone'].map(v => (
                    <button
                      key={v}
                      type="button"
                      onClick={() => setTab(v)}
                      style={{
                        padding: '6px 14px',
                        fontSize: 11,
                        fontFamily: 'var(--font-mono)',
                        letterSpacing: '0.08em',
                        textTransform: 'uppercase',
                        background: tab === v ? 'var(--primary)' : 'transparent',
                        color: tab === v ? 'var(--on-primary)' : 'var(--text-secondary)',
                        border: 'none',
                        cursor: 'pointer',
                      }}
                    >
                      {v}
                    </button>
                  ))}
                </div>
              )}

              {(atCreds || isReset) && !atNewPwd && (
                <div className="mt-5">
                  {isSignup && (
                    <div className="flex flex-col gap-4">
                      <Field label="Full name" value={name} onChange={setName} placeholder="e.g. Ananya Sharma" autoComplete="name" />
                      <Field label="Firm / organization (optional)" value={org} onChange={setOrg} placeholder="e.g. Sharma & Associates" autoComplete="organization" />
                    </div>
                  )}
                  {tab === 'email' && (
                    <div className={isSignup ? 'mt-4' : ''}>
                      <Field label="Work email" type="email" value={email} onChange={setEmail} placeholder="test@void.legal" autoComplete="email" />
                    </div>
                  )}
                  {tab === 'phone' && (
                    <div className={isSignup ? 'mt-4' : ''}>
                      <Field label="Mobile number" type="tel" value={phone} onChange={setPhone} placeholder="+91 98765 43210" autoComplete="tel" />
                    </div>
                  )}

                  {!isSignup && tab === 'email' && !isReset && (
                    <div className="mt-4">
                      <Field label="Password" type="password" value={password} onChange={setPassword} placeholder="voidtest123" autoComplete="current-password" />
                      <button
                        type="button"
                        onClick={() => { setEmail('test@void.legal'); setPassword('voidtest123') }}
                        style={{ marginTop: 8, padding: 0, background: 'none', border: 'none', fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: '0.08em', color: 'var(--text-muted)', cursor: 'pointer', textDecoration: 'underline', textUnderlineOffset: 3 }}
                      >
                        DEMO · test@void.legal / voidtest123 — tap to fill
                      </button>
                    </div>
                  )}

                  {(isSignup || tab === 'phone' || isReset) && (
                    <div className="mt-5">
                      <PrimaryButton busy={busy} onClick={e => { e.preventDefault(); handleSendCode() }}>
                        {isReset ? 'Send reset code' : 'Send code'}
                      </PrimaryButton>
                    </div>
                  )}

                  {!isSignup && tab === 'email' && !isReset && (
                    <div className="mt-5">
                      <PrimaryButton busy={busy} onClick={handlePasswordLogin}>
                        Sign in
                      </PrimaryButton>
                    </div>
                  )}
                </div>
              )}

              {(atOtp || atNewPwd) && (
                <div className="mt-5">
                  <p style={{ margin: 0, fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                    CODE SENT TO <span style={{ color: 'var(--text-primary)' }}>{masked}</span>
                  </p>
                  <div className="mt-4">
                    <Field label={atNewPwd ? 'New password' : 'One-time password'} type={atNewPwd ? 'password' : 'text'} value={otp} onChange={setOtp} placeholder={atNewPwd ? 'min 6 characters' : '6 digits'} autoComplete={atNewPwd ? 'new-password' : 'one-time-code'} />
                  </div>
                  {atOtp && isSignup && (
                    <div className="mt-4">
                      <Field label="Set a password" type="password" value={password} onChange={setPassword} placeholder="min 6 characters" autoComplete="new-password" />
                    </div>
                  )}
                  <DevOtpStamp devOtp={devOtp} />

                  <div className="mt-5">
                    {atNewPwd ? (
                      <PrimaryButton busy={busy} onClick={e => { e.preventDefault(); handleNewPassword() }}>
                        Set new password
                      </PrimaryButton>
                    ) : (
                      <PrimaryButton busy={busy} onClick={e => { e.preventDefault(); handleVerifyOtp() }}>
                        {isSignup ? 'Verify & create account' : isReset ? 'Verify code' : 'Verify & sign in'}
                      </PrimaryButton>
                    )}
                  </div>

                  <div className="mt-3">
                    <button
                      type="button"
                      onClick={handleSendCode}
                      disabled={busy}
                      style={{ background: 'none', border: 'none', padding: 0, fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)', textDecoration: 'underline', textUnderlineOffset: 3, cursor: 'pointer' }}
                    >
                      RESEND CODE
                    </button>
                  </div>
                </div>
              )}

              <div className="mt-6" style={{ borderTop: '1px dashed var(--border-default)' }}>
                <ErrorStamp message={error} />
              </div>
            </div>

            <div className="px-6 pb-6 pt-2">
              {!isReset && (
                <div className="flex items-center justify-between text-[12px]" style={{ color: 'var(--text-muted)' }}>
                  <button
                    type="button"
                    onClick={() => { setIntent('reset'); setStep('creds'); setError('') }}
                    style={{ background: 'none', border: 'none', padding: 0, fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', cursor: 'pointer' }}
                  >
                    Forgot password?
                  </button>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                    {isSignup ? 'Have a docket?' : 'New to Juris AI?'}{' '}
                    <button
                      type="button"
                      onClick={() => switchMode(isSignup ? 'login' : 'signup')}
                      style={{ background: 'none', border: 'none', padding: 0, fontWeight: 700, color: 'var(--ink)', fontFamily: 'var(--font-mono)', cursor: 'pointer' }}
                    >
                      {isSignup ? 'SIGN IN' : 'STAMP AN ACCOUNT'}
                    </button>
                  </span>
                </div>
              )}
              {isReset && (
                <div className="text-[12px]" style={{ color: 'var(--text-muted)' }}>
                  <button
                    type="button"
                    onClick={() => { setIntent(mode === 'signup' ? 'signup' : 'login'); setStep('creds'); setError('') }}
                    style={{ background: 'none', border: 'none', padding: 0, fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', cursor: 'pointer' }}
                  >
                    ← BACK TO {mode === 'signup' ? 'SIGNUP' : 'LOGIN'}
                  </button>
                </div>
              )}
            </div>
          </div>

          <p className="mt-4 text-center" style={{ marginTop: 14, fontSize: 10, fontFamily: 'var(--font-mono)', letterSpacing: '0.06em', color: 'var(--text-muted)' }}>
            ONE-TIME CODES · SESSION TOKENS · SERVER-SIDE AUTHORITY
          </p>
        </div>
      </div>
    </div>
  )
}