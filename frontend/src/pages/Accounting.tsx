import React, { useState } from 'react'
import { useParams } from 'react-router-dom'
import { fmt, post, useApi } from '../lib/api'
import {
  ActionButton, Bar, Card, DQBadge, Data, KPI, LineageDrawer, Page, StatusBadge, Table,
  BarChart,
} from '../components/ui'

export function Organization() {
  const tree = useApi('/accounting/entities/tree')
  const boundaries = useApi('/accounting/reporting-boundaries')
  const baselines = useApi('/accounting/baselines')
  return (
    <Page title="Organization model" req="FR-3.A.5"
          sub="Entities, facilities, departments, cost centers, products, reporting boundaries, baseline years and ownership controls.">
      <div className="stack">
        <Card title="Entity hierarchy & ownership controls">
          <Data of={tree}>{(roots: any[]) => <EntityTree nodes={roots} />}</Data>
        </Card>
        <div className="grid g2">
          <Card title="Reporting boundaries">
            <Data of={boundaries}>{(rows: any[]) => (
              <Table cols={[
                { h: 'Boundary', cell: (r: any) => r.name },
                { h: 'Consolidation', cell: (r: any) => <StatusBadge status={r.consolidation_method} /> },
                { h: 'Baseline year', num: true, cell: (r: any) => r.baseline_year },
                { h: 'Entities', num: true, cell: (r: any) => r.included_entity_ids?.length },
                { h: 'Scopes', cell: (r: any) => (r.scopes_covered || []).map(fmt.label).join(', ') },
              ]} rows={rows} />
            )}</Data>
          </Card>
          <Card title="Baselines" note="locked baselines are immutable (FR-7.3)">
            <Data of={baselines}>{(rows: any[]) => (
              <Table cols={[
                { h: 'Year', num: true, cell: (r: any) => r.year },
                { h: 'Scope', cell: (r: any) => fmt.label(r.scope) },
                { h: 'tCO2e', num: true, cell: (r: any) => fmt.t(r.co2e_tonnes, 0) },
                { h: 'State', cell: (r: any) => (
                    <span className={`badge ${r.locked ? 'ok' : 'info'}`}>
                      {r.locked ? 'locked' : 'open'}{r.is_recalculated ? ' · recalculated' : ''}
                    </span>) },
              ]} rows={rows.slice(0, 25)} />
            )}</Data>
          </Card>
        </div>
      </div>
    </Page>
  )
}

function EntityTree({ nodes, depth = 0 }: any) {
  return (
    <div>
      {nodes.map((n: any) => (
        <div key={n.id}>
          <div className="row" style={{ padding: '5px 0', paddingLeft: depth * 20,
                                        borderBottom: '1px solid var(--line)' }}>
            <b>{n.name}</b>
            <span className="muted small">{n.code} · {n.country}</span>
            <span className="badge">{fmt.t(n.ownership_pct, 0)}% owned</span>
            <StatusBadge status={n.consolidation_method} />
            {!n.is_consolidated && <span className="badge warn">excluded from boundary</span>}
            <div className="spacer" />
            <span className="muted small">{n.facilities.length} facilities · {fmt.n(n.employees)} employees</span>
          </div>
          {n.facilities.map((f: any) => (
            <div key={f.id} className="row small muted"
                 style={{ paddingLeft: (depth + 1) * 20 + 14, padding: '3px 0 3px ' + ((depth + 1) * 20 + 14) + 'px' }}>
              ↳ {f.name} <span className="badge">{f.facility_type}</span> {f.country}
              <span>· {fmt.n(f.floor_area_m2)} m²</span>
            </div>
          ))}
          {n.children?.length > 0 && <EntityTree nodes={n.children} depth={depth + 1} />}
        </div>
      ))}
    </div>
  )
}

export function ScopePage() {
  const { scope } = useParams()
  const year = 2025
  const s = scope || 'scope_1'
  const path = s === 'scope_1' ? `/accounting/scope1/summary?year=${year}`
    : s === 'scope_2' ? `/accounting/scope2/summary?year=${year}`
    : `/accounting/scope3/summary?year=${year}`
  const q = useApi(path, [s])
  const grid = useApi(s === 'scope_2' ? '/accounting/grid-factors/countries' : null, [s])

  const meta: any = {
    scope_1: { title: 'Scope 1 — direct emissions', req: 'FR-3.A.1',
      sub: 'Stationary and mobile combustion, fleet, process and fugitive emissions, captured from meters, sensors and telematics.' },
    scope_2: { title: 'Scope 2 — purchased energy', req: 'FR-3.A.2',
      sub: 'Facility electricity and energy, computed both location-based and market-based, with renewable instruments and grid factors for 150+ countries.' },
    scope_3: { title: 'Scope 3 — value chain', req: 'FR-3.A.3',
      sub: 'All 15 GHG Protocol categories from spend-, activity-, supplier-, asset-, travel-, logistics-, use- and end-of-life data.' },
  }

  return (
    <Page title={meta[s].title} req={meta[s].req} sub={meta[s].sub}>
      <Data of={q}>{(d: any) => (
        <div className="stack">
          {s === 'scope_1' && (
            <>
              <div className="grid g3">
                <KPI label="Total Scope 1" value={fmt.t(d.total_tco2e, 0)} detail="tCO2e" />
                <KPI label="Records" value={fmt.n(d.record_count)} detail="calculated activity rows" />
                <KPI label="Source types" value={`${d.source_types.length}/${d.expected_source_types.length}`}
                     detail={d.expected_source_types.map(fmt.label).join(', ')} />
              </div>
              <div className="grid g2">
                <Card title="By source type" note="stationary · mobile · fleet · process · fugitive">
                  <Table cols={[
                    { h: 'Source type', cell: (r: any) => fmt.label(r.source_type) },
                    { h: 'tCO2e', num: true, cell: (r: any) => fmt.t(r.tco2e, 1) },
                  ]} rows={d.source_types} />
                </Card>
                <Card title="By capture method" note="meter · sensor · telematics">
                  <Table cols={[
                    { h: 'Data origin', cell: (r: any) => fmt.label(r.data_origin) },
                    { h: 'tCO2e', num: true, cell: (r: any) => fmt.t(r.tco2e, 1) },
                  ]} rows={d.capture_methods} />
                </Card>
              </div>
            </>
          )}

          {s === 'scope_2' && (
            <>
              <div className="grid g4">
                <KPI label="Location-based" value={fmt.t(d.location_based_tco2e, 0)} detail="tCO2e" />
                <KPI label="Market-based" value={fmt.t(d.market_based_tco2e, 0)} detail="tCO2e" />
                <KPI label="Renewable benefit" value={fmt.pct(d.renewable_benefit_pct)}
                     detail={`${fmt.t(d.difference_tco2e, 0)} tCO2e avoided`} tone="down" />
                <KPI label="Grid factor coverage" value={grid.data?.country_count ?? '…'}
                     detail="countries with grid factors" />
              </div>
              <Card title="Location-based emissions by country" note="FR-3.A.2">
                <BarChart data={d.by_country.slice(0, 14)} x="country" y="tco2e"
                          format={(v: number) => `${fmt.t(v)} tCO2e`} />
              </Card>
              <Card title="Grid factors loaded" note="FR-3.A.2 — 150+ countries">
                <Data of={grid}>{(g: any) => (
                  <>
                    <p className="small muted">
                      {g.country_count} countries carry a grid emission factor.
                    </p>
                    <Table cols={[
                      { h: 'Country', cell: (r: any) => r.country },
                      { h: 'kgCO2e/kWh', num: true, cell: (r: any) => fmt.t(r.min_kgco2e_per_kwh, 4) },
                    ]} rows={g.countries.slice(0, 30)} />
                  </>
                )}</Data>
              </Card>
            </>
          )}

          {s === 'scope_3' && (
            <>
              <div className="grid g3">
                <KPI label="Total Scope 3" value={fmt.t(d.total_tco2e, 0)} detail="tCO2e" />
                <KPI label="Category coverage"
                     value={`${d.categories_reported}/${d.categories_total}`}
                     detail={`${fmt.pct(d.coverage_pct, 0)} of GHG Protocol categories reported`} />
                <KPI label="Data methods" value={d.data_methods.length}
                     detail={d.data_methods.map(fmt.label).join(', ')} />
              </div>
              <Card title="All 15 GHG Protocol categories" note="every category listed, reported or not">
                <Table cols={[
                  { h: '#', num: true, cell: (r: any) => r.number },
                  { h: 'Category', cell: (r: any) => r.name },
                  { h: 'tCO2e', num: true, cell: (r: any) => fmt.t(r.tco2e, 0) },
                  { h: 'Share', num: true, cell: (r: any) => fmt.pct(r.share_pct) },
                  { h: '', cell: (r: any) => <Bar pct={r.share_pct * 3} color="var(--s3)" /> },
                  { h: 'Methods', cell: (r: any) => (r.methods_used || []).map(fmt.label).join(', ') },
                  { h: 'Status', cell: (r: any) => r.is_reported
                      ? <span className="badge ok">reported</span>
                      : <span className="badge bad">not reported</span> },
                ]} rows={d.categories} />
              </Card>
            </>
          )}
        </div>
      )}</Data>
    </Page>
  )
}

export function ActivityData() {
  const [scope, setScope] = useState('')
  const [page, setPage] = useState(1)
  const [capture, setCapture] = useState(false)
  const q = useApi(`/accounting/activity-data?page=${page}&page_size=25${scope ? `&scope=${scope}` : ''}`,
                   [scope, page])
  const [lineage, setLineage] = useState<number | null>(null)
  return (
    <Page title="Activity data" req="FR-3.A.1–.3 / FR-7.4"
          sub="The raw quantities everything is computed from, each carrying its origin and data-quality state."
          actions={
            <div className="row">
              <button className="btn sm primary" onClick={() => setCapture((v) => !v)}>
                {capture ? 'Close capture' : 'Add activity data'}
              </button>
              {['', 'scope_1', 'scope_2', 'scope_3'].map((s) => (
                <span key={s} className={`chip ${scope === s ? 'on' : ''}`}
                      onClick={() => { setScope(s); setPage(1) }}>
                  {s ? fmt.label(s) : 'All scopes'}
                </span>
              ))}
            </div>}>
          {capture && <ActivityCapture onDone={() => { setCapture(false); q.reload() }} />}
      <Data of={q}>{(d: any) => (
        <Card title={`${fmt.n(d.total)} rows`} right={
          <div className="row">
            <button className="btn sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Prev</button>
            <span className="small muted">{d.page} / {d.pages}</span>
            <button className="btn sm" disabled={page >= d.pages} onClick={() => setPage(page + 1)}>Next</button>
          </div>}>
          <Table cols={[
            { h: 'Period', cell: (r: any) => fmt.date(r.period_start) },
            { h: 'Scope', cell: (r: any) => fmt.label(r.scope) },
            { h: 'Description', cell: (r: any) => r.description || r.activity_key },
            { h: 'Entity', cell: (r: any) => r.entity_name },
            { h: 'Facility', cell: (r: any) => r.facility_name || '—' },
            { h: 'Quantity', num: true, cell: (r: any) => `${fmt.n(r.quantity, 1)} ${r.unit}` },
            { h: 'Origin', cell: (r: any) => <span className="badge">{fmt.label(r.data_origin)}</span> },
            { h: 'tCO2e', num: true, cell: (r: any) => fmt.t(r.co2e_tonnes, 2) },
            { h: 'DQ', cell: (r: any) => <DQBadge rating={r.data_quality_rating}
                                                  confidence={r.confidence_score}
                                                  estimated={r.is_estimated} /> },
            { h: 'Status', cell: (r: any) => <StatusBadge status={r.calculation_status} /> },
            { h: '', cell: (r: any) => r.calculation_id
                ? <span className="link small" onClick={() => setLineage(r.calculation_id)}>lineage</span>
                : null },
          ]} rows={d.items} />
        </Card>
      )}</Data>
      {lineage && <LineageDrawer calculationId={lineage} onClose={() => setLineage(null)} />}
    </Page>
  )
}

function ActivityCapture({ onDone }: { onDone: () => void }) {
  const [form, setForm] = useState({ entity_id: 2, scope: 'scope_1', activity_key: 'natural_gas',
    description: 'Natural gas used at Stuttgart Plant', quantity: 285000, unit: 'kWh',
    period_start: '2025-01-01', period_end: '2025-12-31', data_origin: 'meter' })
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const update = (key: string, value: string) => setForm((current) => ({ ...current, [key]: value }))
  async function save(e: React.FormEvent) {
    e.preventDefault(); setSaving(true); setMessage('')
    try { await post('/accounting/activity-data', { ...form, entity_id: Number(form.entity_id), quantity: Number(form.quantity) }); onDone() }
    catch (error: any) { setMessage(error.message) }
    setSaving(false)
  }
  return <form className="card capture-form" onSubmit={save}>
    <div className="row"><h3>Capture activity data</h3><div className="spacer" /><span className="small muted">Calculated with lineage</span></div>
    <div className="grid g3">
      <label className="field">Scope<select value={form.scope} onChange={(e) => update('scope', e.target.value)}><option>scope_1</option><option>scope_2</option><option>scope_3</option></select></label>
      <label className="field">Activity key<input value={form.activity_key} onChange={(e) => update('activity_key', e.target.value)} /></label>
      <label className="field">Quantity<input type="number" value={form.quantity} onChange={(e) => update('quantity', e.target.value)} /></label>
      <label className="field">Unit<input value={form.unit} onChange={(e) => update('unit', e.target.value)} /></label>
      <label className="field">Period start<input type="date" value={form.period_start} onChange={(e) => update('period_start', e.target.value)} /></label>
      <label className="field">Period end<input type="date" value={form.period_end} onChange={(e) => update('period_end', e.target.value)} /></label>
    </div>
    <label className="field">Description<input value={form.description} onChange={(e) => update('description', e.target.value)} /></label>
    <div className="row"><button className="btn sm primary" disabled={saving}>{saving ? 'Saving…' : 'Save and calculate'}</button>{message && <span className="small up">{message}</span>}</div>
  </form>
}

export function Calculations() {
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const q = useApi(`/accounting/calculations?page=${page}&page_size=25${status ? `&status=${status}` : ''}`,
                   [status, page])
  const [lineage, setLineage] = useState<number | null>(null)
  const [repro, setRepro] = useState<any>(null)
  return (
    <Page title="Calculations & lineage" req="FR-3.A.4 / FR-7.2 / FR-7.3"
          sub="Every calculation stores its factor, method, unit conversion, allocation, consolidation and assumptions. Approval freezes the value."
          actions={
            <div className="row">
              {['', 'calculated', 'approved', 'locked', 'superseded', 'restated'].map((s) => (
                <span key={s} className={`chip ${status === s ? 'on' : ''}`}
                      onClick={() => { setStatus(s); setPage(1) }}>{s ? fmt.label(s) : 'All'}</span>
              ))}
            </div>}>
      <Data of={q}>{(d: any) => (
        <Card title={`${fmt.n(d.total)} calculations`} right={
          <div className="row">
            <button className="btn sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Prev</button>
            <span className="small muted">{d.page} / {d.pages}</span>
            <button className="btn sm" disabled={page >= d.pages} onClick={() => setPage(page + 1)}>Next</button>
          </div>}>
          <Table cols={[
            { h: 'ID', num: true, cell: (r: any) => r.id },
            { h: 'Activity', cell: (r: any) => r.activity_description || r.activity_key },
            { h: 'Scope', cell: (r: any) => fmt.label(r.scope) },
            { h: 'Entity', cell: (r: any) => r.entity_name },
            { h: 'Factor lib', cell: (r: any) => r.factor_library_version },
            { h: 'GWP', cell: (r: any) => r.gwp_set },
            { h: 'tCO2e', num: true, cell: (r: any) => fmt.t(r.co2e_tonnes, 3) },
            { h: 'v', num: true, cell: (r: any) => r.version },
            { h: 'DQ', cell: (r: any) => <DQBadge rating={r.data_quality_rating}
                                                  confidence={r.confidence_score} /> },
            { h: 'Status', cell: (r: any) => <StatusBadge status={r.status} /> },
            { h: '', cell: (r: any) => (
                <span className="row" style={{ gap: 8 }}>
                  <span className="link small" onClick={() => setLineage(r.id)}>lineage</span>
                  <span className="link small" onClick={async () =>
                    setRepro(await (await fetch(`/api/accounting/calculations/${r.id}/reproduce`,
                      { headers: { 'X-User-Email': localStorage.getItem('decarbx.email') || 'ana.k@meridian.example' } })).json())
                  }>reproduce</span>
                </span>) },
          ]} rows={d.items} />
        </Card>
      )}</Data>

      {repro && (
        <Card title="Reproducibility check" note="FR-7.3">
          <div className="row">
            <span className={`badge ${repro.reproducible ? 'ok' : 'bad'}`}>
              {repro.reproducible ? 'Reproduced exactly' : 'Could not reproduce'}
            </span>
            <span className="small muted">
              stored {fmt.n(repro.stored_co2e_kg, 4)} kg · recomputed {fmt.n(repro.recomputed_co2e_kg, 4)} kg ·
              delta {repro.delta_kg} · {repro.method_version} · {repro.factor_library_version} · {repro.gwp_set}
            </span>
            <div className="spacer" />
            <button className="btn sm" onClick={() => setRepro(null)}>Dismiss</button>
          </div>
        </Card>
      )}
      {lineage && <LineageDrawer calculationId={lineage} onClose={() => setLineage(null)} />}
    </Page>
  )
}

export function Factors() {
  const libs = useApi('/accounting/factor-libraries')
  const [q, setQ] = useState('')
  const factors = useApi(`/accounting/emission-factors?page_size=40${q ? `&q=${encodeURIComponent(q)}` : ''}`, [q])
  return (
    <Page title="Factor libraries" req="FR-5.3 / FR-7.3"
          sub="Controlled factor libraries with methodology and version locking.">
      <div className="stack">
        <Card title="Libraries">
          <Data of={libs}>{(rows: any[]) => (
            <Table cols={[
              { h: 'Library', cell: (r: any) => r.name },
              { h: 'Provider', cell: (r: any) => r.provider },
              { h: 'Version', cell: (r: any) => r.version },
              { h: 'Released', cell: (r: any) => fmt.date(r.release_date) },
              { h: 'Factors', num: true, cell: (r: any) => fmt.n(r.factor_count) },
              { h: 'State', cell: (r: any) => (
                  <span className={`badge ${r.is_locked ? 'ok' : 'info'}`}>
                    {r.is_locked ? 'locked' : 'open'}{r.is_default ? ' · default' : ''}
                  </span>) },
              { h: '', cell: (r: any) => (
                  <ActionButton label={r.is_locked ? 'Unlock' : 'Lock'}
                    run={() => post(`/accounting/factor-libraries/${r.id}/lock`, { locked: !r.is_locked })}
                    onDone={() => libs.reload()} />) },
            ]} rows={rows} />
          )}</Data>
        </Card>
        <Card title="Emission factors" right={
          <input placeholder="Search factors…" value={q} onChange={(e) => setQ(e.target.value)} />}>
          <Data of={factors}>{(d: any) => (
            <Table cols={[
              { h: 'Activity key', cell: (r: any) => <code className="small">{r.activity_key}</code> },
              { h: 'Name', cell: (r: any) => r.name },
              { h: 'Country', cell: (r: any) => r.country },
              { h: 'Value', num: true, cell: (r: any) => `${r.value_kgco2e} kg/${r.unit}` },
              { h: 'Method', cell: (r: any) => fmt.label(r.method) },
              { h: 'Unc.', num: true, cell: (r: any) => fmt.pct(r.uncertainty_pct, 0) },
              { h: 'Valid from', cell: (r: any) => fmt.date(r.valid_from) },
              { h: 'Gases', cell: (r: any) => Object.keys(r.gas_breakdown || {}).join(', ') || 'CO2e' },
            ]} rows={d.items} />
          )}</Data>
        </Card>
      </div>
    </Page>
  )
}

export function Governance() {
  const [impact, setImpact] = useState<any>(null)
  const [gwp, setGwp] = useState('AR5')
  const libs = useApi('/accounting/factor-libraries')
  return (
    <Page title="Recalculation & restatement" req="FR-7.3"
          sub="A methodology or factor change never silently rewrites history: it produces an impact analysis first, then a documented restatement.">
      <div className="stack">
        <Card title="Recalculation impact analysis" note="dry run — changes nothing">
          <div className="row" style={{ marginBottom: 10 }}>
            <label className="field">Switch GWP set to</label>
            <select value={gwp} onChange={(e) => setGwp(e.target.value)}>
              <option>AR4</option><option>AR5</option><option>AR6</option>
            </select>
            <ActionButton label="Run impact analysis"
              run={() => post('/accounting/recalculation/impact', { new_gwp_set: gwp })}
              onDone={setImpact} />
          </div>
          {impact && (
            <div className="stack">
              <div className="grid g4">
                <KPI label="Driver" value={impact.calculations_impacted}
                     detail={`of ${impact.calculations_examined} calculations impacted`} />
                <KPI label="Current total" value={fmt.t(impact.total_old_tco2e, 0)} detail="tCO2e" />
                <KPI label="After change" value={fmt.t(impact.total_new_tco2e, 0)} detail="tCO2e" />
                <KPI label="Delta" value={`${impact.delta_tco2e >= 0 ? '+' : ''}${fmt.t(impact.delta_tco2e, 0)}`}
                     detail={`${fmt.t(impact.delta_pct, 2)}% · ${impact.restatement_recommended ? 'restatement recommended' : 'below restatement threshold'}`}
                     tone={impact.delta_tco2e >= 0 ? 'up' : 'down'} />
              </div>
              <Card title="Impact by entity">
                <Table cols={[
                  { h: 'Entity', cell: (r: any) => r.entity_name },
                  { h: 'Current', num: true, cell: (r: any) => fmt.t(r.old / 1000, 1) },
                  { h: 'After', num: true, cell: (r: any) => fmt.t(r.new / 1000, 1) },
                  { h: 'Delta tCO2e', num: true, cell: (r: any) => fmt.t(r.delta / 1000, 2) },
                  { h: 'Delta %', num: true, cell: (r: any) => fmt.pct(r.delta_pct, 2) },
                ]} rows={impact.by_entity} />
              </Card>
              <Card title="Largest single changes">
                <Table cols={[
                  { h: 'Calculation', num: true, cell: (r: any) => `#${r.calculation_id}` },
                  { h: 'Scope', cell: (r: any) => fmt.label(r.scope) },
                  { h: 'Year', num: true, cell: (r: any) => r.year },
                  { h: 'Old kg', num: true, cell: (r: any) => fmt.n(r.old_co2e_kg, 1) },
                  { h: 'New kg', num: true, cell: (r: any) => fmt.n(r.new_co2e_kg, 1) },
                  { h: 'Delta %', num: true, cell: (r: any) => fmt.pct(r.delta_pct, 2) },
                ]} rows={impact.top_changes.slice(0, 15)} />
              </Card>
              <div className="small muted">
                To apply this change, restate the affected calculations with a documented
                reason — the originals are marked superseded, never edited.
              </div>
            </div>
          )}
        </Card>

        <Card title="Version locking" note="FR-7.3">
          <Data of={libs}>{(rows: any[]) => (
            <Table cols={[
              { h: 'Library', cell: (r: any) => `${r.provider} ${r.version}` },
              { h: 'Locked', cell: (r: any) => (
                  <span className={`badge ${r.is_locked ? 'ok' : 'info'}`}>
                    {r.is_locked ? 'locked for open period' : 'open'}</span>) },
              { h: 'Factors', num: true, cell: (r: any) => fmt.n(r.factor_count) },
            ]} rows={rows} />
          )}</Data>
        </Card>
      </div>
    </Page>
  )
}
