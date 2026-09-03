import React, { useEffect, useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { SESSION, api, post, setScenario, setUser, useApi } from '../lib/api'

const NAV = [
  ['Overview', [['/', 'Executive scorecard']]],
  ['A · Carbon accounting', [
    ['/organization', 'Organization model'],
    ['/accounting/scope/scope_1', 'Scope 1'],
    ['/accounting/scope/scope_2', 'Scope 2'],
    ['/accounting/scope/scope_3', 'Scope 3'],
    ['/accounting/activity', 'Activity data'],
    ['/accounting/calculations', 'Calculations & lineage'],
    ['/accounting/factors', 'Factor libraries'],
    ['/accounting/governance', 'Recalculation & restatement'],
  ]],
  ['B · Product LCA & PCF', [
    ['/lca/products', 'Products & BOM'],
    ['/lca/pcf', 'PCF results'],
    ['/lca/eco-design', 'Eco-design & labels'],
  ]],
  ['C · Suppliers & Scope 3', [
    ['/suppliers', 'Supplier directory'],
    ['/suppliers/campaigns', 'Campaigns & submissions'],
    ['/suppliers/scorecards', 'Scorecards & plans'],
    ['/suppliers/network', 'Network & hotspots'],
    ['/suppliers/procurement', 'Procurement decisions'],
  ]],
  ['D · Analytics & planning', [
    ['/analytics/quality', 'Data quality'],
    ['/analytics/anomalies', 'Anomalies & gaps'],
    ['/analytics/scenarios', 'Scenarios & what-if'],
    ['/analytics/reduction', 'Levers, MACC & roadmap'],
  ]],
  ['E · Dashboards & finance', [
    ['/dashboards/drilldown', 'Operational drill-down'],
    ['/finance', 'Carbon finance'],
  ]],
  ['4 · Compliance', [['/compliance', 'Frameworks & disclosures']]],
  ['5 · Integrations', [['/integrations', 'Connectors & imports']]],
  ['7 · Platform', [
    ['/platform/notifications', 'Notifications & approvals'],
    ['/platform/bulk', 'Bulk operations & exports'],
    ['/platform/access', 'Access & roles'],
  ]],
]

export default function Layout({ children }: any) {
  const nav = useNavigate()
  const [users, setUsers] = useState<any[]>([])
  const [scenarios, setScenarios] = useState<any[]>([])
  const [scenarioId, setScenarioIdState] = useState<number | null>(SESSION.scenarioId)
  const [actingAs, setActingAs] = useState(SESSION.email)
  const [q, setQ] = useState('')
  const [results, setResults] = useState<any>(null)
  const [savedMessage, setSavedMessage] = useState('')
  const me = useApi<any>('/platform/me')
  const savedViews = useApi<any[]>('/platform/saved-views')

  const groupPermissions: Record<string, string> = {
    'A · Carbon accounting': 'accounting.read', 'B · Product LCA & PCF': 'lca.read',
    'C · Suppliers & Scope 3': 'suppliers.read', 'D · Analytics & planning': 'analytics.read',
    'E · Dashboards & finance': 'dashboards.read', '4 · Compliance': 'compliance.read',
    '5 · Integrations': 'integrations.read', '7 · Platform': 'platform.admin',
  }
  const canSeeGroup = (group: string) => group === 'Overview' || !me.data || me.data.is_unrestricted ||
    (me.data.permissions || []).includes(groupPermissions[group])

  useEffect(() => {
    api('/platform/users').then(setUsers).catch(() => {})
    api('/analytics/scenarios').then(setScenarios).catch(() => {})
  }, [])

  async function runSearch(e: React.FormEvent) {
    e.preventDefault()
    if (!q.trim()) return setResults(null)
    setResults(await api(`/platform/search?q=${encodeURIComponent(q)}`))
  }

  async function saveSearch() {
    if (!q.trim()) return
    try {
      await post('/platform/saved-views', { name: `Search: ${q}`, object_type: 'global', filters: { q } })
      setSavedMessage('Saved'); savedViews.reload()
    } catch (error: any) { setSavedMessage(error.message) }
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <h1>Nexgile · DecarbX</h1>
          <span>Environmental Intelligence Platform</span>
        </div>
        {NAV.filter(([group]: any) => canSeeGroup(group)).map(([group, links]: any) => (
          <div key={group}>
            <div className="navgroup">{group}</div>
            {links.map(([to, label]: any) => (
              <NavLink key={to} to={to} end={to === '/'}
                       className={({ isActive }) => `navlink ${isActive ? 'active' : ''}`}>
                {label}
              </NavLink>
            ))}
          </div>
        ))}
      </aside>

      <div className="main">
        <div className="topbar">
          <form className="searchform" onSubmit={runSearch}>
            <input placeholder="Search everything…  (FR-7.5)" value={q}
                   onChange={(e) => setQ(e.target.value)} />
            {results && (
              <div className="card" style={{ position: 'absolute', top: 36, left: 0,
                                             width: 460, zIndex: 50, maxHeight: 400,
                                             overflowY: 'auto' }}>
                <div className="row">
                  <b className="small">{results.result_count} results</b>
                  <div className="spacer" />
                  <button type="button" className="btn sm"
                          onClick={() => { setResults(null); setQ('') }}>Clear</button>
                </div>
                {Object.entries(results.results || {}).map(([kind, items]: any) =>
                  items.length ? (
                    <div key={kind} style={{ marginTop: 8 }}>
                      <div className="navgroup" style={{ padding: '4px 0' }}>{kind}</div>
                      {items.map((it: any) => (
                        <div key={it.id} className="small link" style={{ padding: '3px 0' }}
                             onClick={() => { nav(it.route); setResults(null); setQ('') }}>
                          {it.label} <span className="muted">· {it.sublabel}</span>
                        </div>
                      ))}
                    </div>
                  ) : null
                )}
              </div>
            )}
          </form>

          <div className="saved-views">
            <button className="btn sm" type="button" onClick={saveSearch} disabled={!q.trim()}>Save view</button>
            {savedViews.data?.length > 0 && <select aria-label="Saved views" value="" onChange={(e) => {
              const view = savedViews.data.find((item: any) => String(item.id) === e.target.value)
              if (view) setQ(view.filters?.q || '')
            }}>
              <option value="">Saved views</option>
              {savedViews.data.map((view: any) => <option key={view.id} value={view.id}>{view.name}</option>)}
            </select>}
            {savedMessage && <span className="small muted">{savedMessage}</span>}
          </div>

          <div className="spacer" />

          <label className="topbar-label" htmlFor="scenario-select">Scenario</label>
          <select id="scenario-select" value={scenarioId ?? ''} onChange={(e) => {
            const v = e.target.value ? Number(e.target.value) : null
            setScenarioIdState(v); setScenario(v)
          }}>
            <option value="">Approved actuals</option>
            {scenarios.map((s) => (
              <option key={s.id} value={s.id}>Sandbox: {s.name}</option>
            ))}
          </select>

          <label className="topbar-label" htmlFor="acting-as-select">Acting as</label>
          <select id="acting-as-select" value={actingAs} onChange={(e) => {
            setActingAs(e.target.value)
            setUser(e.target.value)
          }}>
            {users.map((u) => (
              <option key={u.email} value={u.email}>
                {u.full_name} — {u.role_name}
              </option>
            ))}
          </select>
        </div>

        {scenarioId != null && (
          <div className="sandbox">
            <b>Scenario sandbox active.</b> Everything below is a what-if. Approved
            actuals cannot be altered from here (FR-7.8).
          </div>
        )}
        {me.data && !me.data.is_unrestricted && (
          <div className="sandbox" style={{ background: '#0d2b3e', borderColor: '#1f4a7a',
                                            color: '#9fd0f5' }}>
            Restricted view for <b>{me.data.role_name}</b> — {me.data.scope.entities.length} entities,
            {' '}{me.data.scope.facilities.length} facilities, {me.data.scope.suppliers.length} suppliers
            visible (FR-7.1).
          </div>
        )}

        <div className="content">{children}</div>
      </div>
    </div>
  )
}
