// One API client. Carries the acting user (FR-7.1) and the scenario context (FR-7.8).
import { useEffect, useState } from 'react'

export const SESSION = {
  email: localStorage.getItem('decarbx.email') || 'ana.k@meridian.example',
  scenarioId: null as number | null,
}

const listeners = new Set<() => void>()
export function onSessionChange(fn: () => void) {
  listeners.add(fn)
  // React effect cleanups must return void (not Set.delete's boolean result).
  return () => { listeners.delete(fn) }
}
function notify() { listeners.forEach((fn) => fn()) }

export function setUser(email: string) {
  SESSION.email = email
  localStorage.setItem('decarbx.email', email)
  notify()
}
export function setScenario(id: number | null) {
  SESSION.scenarioId = id
  notify()
}

function url(path: string) {
  const u = new URL(`/api${path}`, window.location.origin)
  if (SESSION.scenarioId != null && !u.searchParams.has('scenario_id')) {
    u.searchParams.set('scenario_id', String(SESSION.scenarioId))
  }
  return u.pathname + u.search
}

export async function api<T = any>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url(path), {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      'X-User-Email': SESSION.email,
      ...(init?.headers || {}),
    },
  })
  if (!res.ok) {
    let detail: any = res.statusText
    try { detail = (await res.json()).detail ?? detail } catch { /* keep statusText */ }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  const text = await res.text()
  return text ? JSON.parse(text) : (null as any)
}

export const post = <T = any>(p: string, body?: any) =>
  api<T>(p, { method: 'POST', body: JSON.stringify(body ?? {}) })
export const patch = <T = any>(p: string, body?: any) =>
  api<T>(p, { method: 'PATCH', body: JSON.stringify(body ?? {}) })
export const put = <T = any>(p: string, body?: any) =>
  api<T>(p, { method: 'PUT', body: JSON.stringify(body ?? {}) })

/** Data hook that re-fetches whenever the user or the scenario changes. */
export function useApi<T = any>(path: string | null, deps: any[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [tick, setTick] = useState(0)

  useEffect(() => onSessionChange(() => setTick((t) => t + 1)), [])

  useEffect(() => {
    if (!path) { setLoading(false); return }
    let alive = true
    setLoading(true)
    setError(null)
    api<T>(path)
      .then((d) => { if (alive) { setData(d); setLoading(false) } })
      .catch((e) => { if (alive) { setError(e.message); setLoading(false) } })
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, tick, ...deps])

  return { data, error, loading, reload: () => setTick((t) => t + 1) }
}

export const fmt = {
  t: (v: number | null | undefined, d = 1) =>
    v == null ? '—' : v.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d }),
  n: (v: number | null | undefined, d = 0) =>
    v == null ? '—' : v.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d }),
  pct: (v: number | null | undefined, d = 1) => (v == null ? '—' : `${v.toFixed(d)}%`),
  money: (v: number | null | undefined, cur = 'EUR') =>
    v == null ? '—' : `${cur} ${Math.round(v).toLocaleString()}`,
  date: (v: string | null | undefined) => (v ? String(v).slice(0, 10) : '—'),
  label: (v: string | null | undefined) =>
    v == null ? '—' : String(v).replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
}
