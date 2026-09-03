import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { setUser } from '../lib/api'

const ROLES = [
  { value: 'cso', label: 'Chief Sustainability Officer', landing: '/' },
  { value: 'esg_manager', label: 'ESG Manager', landing: '/analytics/quality' },
  { value: 'carbon_accountant', label: 'Carbon Accountant', landing: '/accounting/scope/scope_1' },
  { value: 'procurement', label: 'Supply Chain / Procurement', landing: '/suppliers' },
  { value: 'product_rnd', label: 'Product / R&D', landing: '/lca/products' },
  { value: 'finance', label: 'Finance', landing: '/finance' },
  { value: 'compliance_officer', label: 'Compliance', landing: '/compliance' },
  { value: 'auditor', label: 'Auditor / Verifier', landing: '/compliance' },
]

const DEMO_EMAILS: Record<string, string> = {
  cso: 'ana.k@meridian.example', esg_manager: 'marcus.r@meridian.example',
  carbon_accountant: 'priya.s@meridian.example', procurement: 'carlos.m@meridian.example',
  product_rnd: 'yuki.t@meridian.example', finance: 'iris.d@meridian.example',
  compliance_officer: 'rafael.g@meridian.example', auditor: 'audit@northstar-assurance.example',
}

function AuthFrame({ children, title, subtitle }: any) {
  return <main className="auth-page">
    <section className="auth-aside">
      <div className="auth-mark">N</div>
      <p className="auth-kicker">NEXGILE · DECARBX</p>
      <h1>Decisions with a measurable climate signal.</h1>
      <p>Audit-grade carbon intelligence for operations, products, suppliers, finance, and disclosure teams.</p>
      <div className="auth-stats"><span><b>184,260</b> tCO2e monitored</span><span><b>82.4</b> confidence score</span></div>
    </section>
    <section className="auth-panel">
      <div className="auth-card">
        <p className="auth-kicker">ENVIRONMENTAL INTELLIGENCE PLATFORM</p>
        <h2>{title}</h2>
        <p className="auth-subtitle">{subtitle}</p>
        {children}
      </div>
    </section>
  </main>
}

export function Login() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('ana.k@meridian.example')
  const [message, setMessage] = useState('')
  function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!email.trim()) return setMessage('Enter your work email.')
    const knownEmail = Object.values(DEMO_EMAILS).includes(email.trim())
      ? email.trim() : DEMO_EMAILS.cso
    setUser(knownEmail)
    localStorage.setItem('decarbx.authenticated', 'true')
    navigate('/')
  }
  return <AuthFrame title="Welcome back" subtitle="Sign in to continue to your climate workspace.">
    <form className="auth-form" onSubmit={submit}>
      <label className="field">Work email<input type="email" autoComplete="email" value={email}
        onChange={(e) => setEmail(e.target.value)} required /></label>
      <label className="field">Password<input type="password" autoComplete="current-password" placeholder="Enter your password" required /></label>
      <div className="auth-row"><label className="check"><input type="checkbox" /> Remember this device</label><button type="button" className="text-button">Forgot password?</button></div>
      {message && <p className="auth-error">{message}</p>}
      <button className="btn primary auth-submit" type="submit">Sign in</button>
    </form>
    <p className="auth-switch">New to Nexgile? <Link to="/signup">Create an account</Link></p>
  </AuthFrame>
}

export function Signup() {
  const navigate = useNavigate()
  const [form, setForm] = useState({ name: '', email: '', role: 'cso', password: '' })
  const [message, setMessage] = useState('')
  const update = (key: string, value: string) => setForm((current) => ({ ...current, [key]: value }))
  function submit(e: React.FormEvent) {
    e.preventDefault()
    if (form.password.length < 8) return setMessage('Use at least 8 characters for your password.')
    const role = ROLES.find((item) => item.value === form.role) || ROLES[0]
    setUser(DEMO_EMAILS[role.value] || DEMO_EMAILS.cso)
    localStorage.setItem('decarbx.authenticated', 'true')
    localStorage.setItem('decarbx.role', role.value)
    navigate(role.landing)
  }
  return <AuthFrame title="Create your workspace" subtitle="Set up a role-aware climate intelligence workspace in minutes.">
    <form className="auth-form" onSubmit={submit}>
      <label className="field">Full name<input value={form.name} onChange={(e) => update('name', e.target.value)} autoComplete="name" required /></label>
      <label className="field">Work email<input type="email" value={form.email} onChange={(e) => update('email', e.target.value)} autoComplete="email" required /></label>
      <label className="field">Your role<select value={form.role} onChange={(e) => update('role', e.target.value)}>{ROLES.map((role) => <option key={role.value} value={role.value}>{role.label}</option>)}</select></label>
      <label className="field">Create password<input type="password" value={form.password} onChange={(e) => update('password', e.target.value)} autoComplete="new-password" minLength={8} required /></label>
      {message && <p className="auth-error">{message}</p>}
      <button className="btn primary auth-submit" type="submit">Create workspace</button>
    </form>
    <p className="auth-switch">Already have an account? <Link to="/login">Sign in</Link></p>
  </AuthFrame>
}