import React, { useState } from 'react'
import { api, fmt, post, useApi } from '../lib/api'
import {
  ActionButton, Bar, BarChart, Card, DQBadge, Data, Donut, GeoMap, KPI, LineChart,
  LineageDrawer, Page, StatusBadge, Table,
} from '../components/ui'

/* ============================ B · Product LCA & PCF ====================== */

export function Products() {
  const q = useApi('/lca/products?page_size=50')
  const [open, setOpen] = useState<number | null>(null)
  const bom = useApi(open ? `/lca/products/${open}/bom` : null, [open])
  const proc = useApi(open ? `/lca/products/${open}/processes` : null, [open])
  const routes = useApi(open ? `/lca/products/${open}/routes` : null, [open])
  return (
    <Page title="Products & bill of materials" req="FR-3.B.1 / FR-3.B.2"
          sub="Multi-level BOM with material composition, component-supplier mapping and alternative materials; process model for energy, scrap, defects, packaging, warehousing and multimodal logistics.">
      <div className="stack">
        <Card title="Product portfolio">
          <Data of={q}>{(d: any) => (
            <Table cols={[
              { h: 'SKU', cell: (r: any) => <span className="link" onClick={() => setOpen(r.id)}>{r.sku}</span> },
              { h: 'Product', cell: (r: any) => r.name },
              { h: 'Category', cell: (r: any) => r.category },
              { h: 'Mass', num: true, cell: (r: any) => `${fmt.t(r.mass_kg)} kg` },
              { h: 'Volume/yr', num: true, cell: (r: any) => fmt.n(r.annual_volume) },
              { h: 'PCF kgCO2e', num: true, cell: (r: any) => fmt.t(r.pcf_kgco2e, 2) },
              { h: 'Boundary', cell: (r: any) => fmt.label(r.pcf_boundary) },
              { h: 'Status', cell: (r: any) => <StatusBadge status={r.pcf_status} /> },
              { h: 'ISO 14067', cell: (r: any) => r.iso14067_ready
                  ? <span className="badge ok">ready</span> : <span className="badge warn">not ready</span> },
            ]} rows={d.items} />
          )}</Data>
        </Card>

        {open && (
          <>
            <Card title="Multi-level bill of materials" note="FR-3.B.1">
              <Data of={bom}>{(d: any) => (
                <Table cols={[
                  { h: 'Lvl', num: true, cell: (r: any) => r.level },
                  { h: 'Component', cell: (r: any) => (
                      <span style={{ paddingLeft: (r.level - 1) * 16 }}>{r.component_name}</span>) },
                  { h: 'Material', cell: (r: any) => r.material_name },
                  { h: 'Supplier', cell: (r: any) => `${r.supplier_name || '—'}${r.supplier_tier ? ` (T${r.supplier_tier})` : ''}` },
                  { h: 'Mass kg', num: true, cell: (r: any) => fmt.t(r.mass_kg, 3) },
                  { h: 'Scrap %', num: true, cell: (r: any) => fmt.t(r.scrap_pct, 1) },
                  { h: 'Recycled %', num: true, cell: (r: any) => fmt.t(r.recycled_content_pct, 0) },
                  { h: 'Alternatives', cell: (r: any) => (r.alternatives || []).length
                      ? r.alternatives.map((a: any) => a.material_name).join(', ')
                      : '—' },
                ]} rows={d.flat || []} />
              )}</Data>
            </Card>
            <div className="grid g2">
              <Card title="Process model" note="FR-3.B.2">
                <Data of={proc}>{(rows: any[]) => (
                  <Table cols={[
                    { h: 'Step', cell: (r: any) => r.name },
                    { h: 'Mode', cell: (r: any) => fmt.label(r.production_mode) },
                    { h: 'kWh/unit', num: true, cell: (r: any) => fmt.t(r.energy_kwh_per_unit, 2) },
                    { h: 'MJ/unit', num: true, cell: (r: any) => fmt.t(r.thermal_mj_per_unit, 1) },
                    { h: 'Scrap %', num: true, cell: (r: any) => fmt.t(r.scrap_rate_pct, 1) },
                    { h: 'Defect %', num: true, cell: (r: any) => fmt.t(r.defect_rate_pct, 1) },
                    { h: 'Yield %', num: true, cell: (r: any) => fmt.t(r.yield_pct, 1) },
                  ]} rows={rows} />
                )}</Data>
              </Card>
              <Card title="Multimodal logistics" note="FR-3.B.2">
                <Data of={routes}>{(rows: any[]) => (
                  <Table cols={[
                    { h: 'Stage', cell: (r: any) => fmt.label(r.stage) },
                    { h: 'Mode', cell: (r: any) => <span className="badge">{fmt.label(r.mode)}</span> },
                    { h: 'Route', cell: (r: any) => `${r.origin} → ${r.destination}` },
                    { h: 'km', num: true, cell: (r: any) => fmt.n(r.distance_km) },
                    { h: 'Load %', num: true, cell: (r: any) => fmt.t(r.load_factor_pct, 0) },
                    { h: 'Warehouse d', num: true, cell: (r: any) => fmt.t(r.warehouse_days, 0) },
                  ]} rows={rows} />
                )}</Data>
              </Card>
            </div>
          </>
        )}
      </div>
    </Page>
  )
}

export function PCFPage() {
  const q = useApi('/lca/pcf?page_size=50')
  const summary = useApi('/lca/pcf/portfolio/summary')
  const [open, setOpen] = useState<number | null>(null)
  const iso = useApi(open ? `/lca/pcf/${open}/iso14067-report` : null, [open])
  const pack = useApi(open ? `/lca/pcf/${open}/certification-pack` : null, [open])
  const [exchange, setExchange] = useState<any>(null)
  return (
    <Page title="Product carbon footprints" req="FR-3.B.3 / FR-3.B.4"
          sub="Cradle-to-gate, gate-to-gate and cradle-to-grave boundaries with functional units, allocation, circularity, uncertainty, peer review, verification and certification packs.">
      <div className="stack">
        <Data of={summary}>{(s: any) => (
          <div className="grid g4">
            <KPI label="Products" value={s.product_count} detail={`${s.with_pcf} with a PCF`} />
            <KPI label="Coverage" value={fmt.pct(s.coverage_pct, 0)} detail="of the portfolio" />
            <KPI label="Verified" value={s.verified_count} detail="verified or certified" />
            <KPI label="Annual footprint" value={fmt.t(s.total_annual_tco2e, 0)}
                 detail="tCO2e from product volumes" />
          </div>
        )}</Data>

        <Card title="PCF results">
          <Data of={q}>{(d: any) => (
            <Table cols={[
              { h: 'SKU', cell: (r: any) => <span className="link" onClick={() => setOpen(r.id)}>{r.sku}</span> },
              { h: 'Product', cell: (r: any) => r.product_name },
              { h: 'Boundary', cell: (r: any) => fmt.label(r.boundary) },
              { h: 'kgCO2e total', num: true, cell: (r: any) => fmt.t(r.total_kgco2e, 2) },
              { h: 'Per FU', num: true, cell: (r: any) => fmt.t(r.per_functional_unit_kgco2e, 2) },
              { h: 'Unc.', num: true, cell: (r: any) => fmt.pct(r.uncertainty_pct, 0) },
              { h: 'Circularity', num: true, cell: (r: any) => fmt.t(r.circularity_score, 0) },
              { h: 'v', num: true, cell: (r: any) => r.version },
              { h: 'Status', cell: (r: any) => <StatusBadge status={r.status} /> },
              { h: '', cell: (r: any) => (
                  <span className="row" style={{ gap: 8 }}>
                    <span className="link small" onClick={async () =>
                      setExchange(await api(`/lca/pcf/${r.id}/exchange?format=pact`))}>PACT</span>
                    <span className="link small" onClick={async () =>
                      setExchange(await api(`/lca/pcf/${r.id}/exchange?format=tfs`))}>TfS</span>
                  </span>) },
            ]} rows={d.items} />
          )}</Data>
        </Card>

        {exchange && (
          <Card title="B2B exchange document" note="FR-3.B.5 / FR-5.4"
                right={<button className="btn sm" onClick={() => setExchange(null)}>Close</button>}>
            <pre>{JSON.stringify(exchange, null, 2)}</pre>
          </Card>
        )}

        {open && (
          <>
            <Card title="ISO 14067 report" note="FR-3.B.4">
              <Data of={iso}>{(r: any) => (
                <div className="stack">
                  <div className="row">
                    <span className={`badge ${r.ready ? 'ok' : 'warn'}`}>
                      {r.ready ? 'ISO 14067 ready' : 'Not yet ISO 14067 ready'}</span>
                    <span className="badge info">{r['1_goal_and_scope'].system_boundary}</span>
                    <span className="badge">FU: {r['1_goal_and_scope'].functional_unit.name}</span>
                  </div>
                  <Card title="Life cycle stages">
                    <Table cols={[
                      { h: 'Stage', cell: (x: any) => fmt.label(x[0]) },
                      { h: 'kgCO2e', num: true, cell: (x: any) => fmt.t(x[1], 3) },
                    ]} rows={Object.entries(r['2_life_cycle_inventory'].stage_breakdown_kgco2e)} />
                  </Card>
                  <Card title="Interpretation — assumptions, uncertainty, sensitivity">
                    <div className="row" style={{ marginBottom: 8 }}>
                      <span className="badge warn">Uncertainty {fmt.pct(r['4_interpretation'].uncertainty_pct)}</span>
                      <span className="badge">Recycled content {fmt.pct(r['4_interpretation'].circularity.recycled_content_pct, 0)}</span>
                      <span className="badge">Recyclability {fmt.pct(r['4_interpretation'].circularity.recyclability_pct, 0)}</span>
                      <span className="badge">EOL: {fmt.label(r['4_interpretation'].circularity.end_of_life_scenario)}</span>
                    </div>
                    <Table cols={[
                      { h: 'Driver', cell: (x: any) => x.driver },
                      { h: 'Contribution', num: true, cell: (x: any) => fmt.t(x.contribution, 3) },
                      { h: 'Share', num: true, cell: (x: any) => fmt.pct(x.share_pct) },
                      { h: 'Swing ±10%', num: true, cell: (x: any) => fmt.t(x.swing, 3) },
                    ]} rows={r['4_interpretation'].sensitivity_analysis || []} />
                    <ul className="small muted" style={{ marginTop: 10, paddingLeft: 18 }}>
                      {(r['4_interpretation'].assumptions || []).map((a: string, i: number) =>
                        <li key={i}>{a}</li>)}
                    </ul>
                  </Card>
                  <Card title="Verification chain">
                    <div className="row">
                      <span className="badge">Peer reviewer: {r['5_verification'].peer_reviewer || '—'}</span>
                      <span className="badge">Verifier: {r['5_verification'].verifier || '—'}</span>
                      <span className="badge">Cert: {r['5_verification'].certification_ref || '—'}</span>
                    </div>
                  </Card>
                </div>
              )}</Data>
            </Card>
            <Card title="Certification pack" note="FR-3.B.4">
              <Data of={pack}>{(p: any) => (
                <div className="row">
                  <span className="badge info">{p.pack_id}</span>
                  <span className="badge">{p.evidence_count} evidence documents</span>
                  <span className="badge">{(p.assumptions || []).length} assumptions</span>
                  <span className="badge warn">uncertainty {fmt.pct(p.uncertainty_pct)}</span>
                </div>
              )}</Data>
            </Card>
          </>
        )}
      </div>
    </Page>
  )
}

export function EcoDesign() {
  const products = useApi('/lca/products?page_size=20')
  const materials = useApi('/lca/materials?alternatives_only=true')
  const [result, setResult] = useState<any>(null)
  const [declaration, setDeclaration] = useState<any>(null)
  const pcfs = useApi('/lca/pcf?page_size=20')
  return (
    <Page title="Eco-design, labels & declarations" req="FR-3.B.5"
          sub="Alternative-material scenarios, eco-design comparisons, environmental labels, QR declarations and marketing-claim evidence.">
      <div className="stack">
        <Card title="Eco-design comparison"
              right={<Data of={products}>{(d: any) => (
                <ActionButton label="Compare recycled-route variants" run={async () => {
                  const pid = d.items[0].id
                  const bom = await api(`/lca/products/${pid}/bom`)
                  const alts = (bom.flat || []).flatMap((i: any) =>
                    (i.alternatives || []).map((a: any) => [i.id, a.material_id]))
                  return post('/lca/eco-design/compare', {
                    product_id: pid,
                    variants: [
                      { name: 'Recycled materials', material_substitutions:
                          Object.fromEntries(alts) },
                      { name: 'Recycled + recycling EOL',
                        material_substitutions: Object.fromEntries(alts),
                        end_of_life_scenario: 'recycling' },
                      { name: 'Landfill EOL (worst case)',
                        material_substitutions: {}, end_of_life_scenario: 'landfill' },
                    ],
                  })
                }} onDone={setResult} />
              )}</Data>}>
          {result ? (
            <div className="stack">
              <div className="row">
                <span className="badge ok">Best option: {result.best_option}</span>
                <span className="badge">Max reduction {fmt.t(result.max_reduction_kgco2e, 2)} kgCO2e</span>
              </div>
              <Table cols={[
                { h: 'Variant', cell: (r: any) => r.name },
                { h: 'kgCO2e', num: true, cell: (r: any) => fmt.t(r.total_kgco2e, 2) },
                { h: 'Delta', num: true, cell: (r: any) => (
                    <span className={r.delta_kgco2e > 0 ? 'up' : 'down'}>
                      {r.delta_kgco2e > 0 ? '+' : ''}{fmt.t(r.delta_kgco2e, 2)}</span>) },
                { h: 'Delta %', num: true, cell: (r: any) => fmt.pct(r.delta_pct) },
                { h: 'Recycled %', num: true, cell: (r: any) => fmt.t(r.recycled_content_pct, 0) },
                { h: 'Circularity', num: true, cell: (r: any) => fmt.t(r.circularity_score, 0) },
              ]} rows={result.variants} />
            </div>
          ) : (
            <div className="muted small">
              Run a comparison to model alternative-material scenarios against the baseline design.
            </div>
          )}
        </Card>

        <Card title="Environmental labels & QR declarations" note="FR-3.B.5">
          <Data of={pcfs}>{(d: any) => (
            <Table cols={[
              { h: 'SKU', cell: (r: any) => r.sku },
              { h: 'Status', cell: (r: any) => <StatusBadge status={r.status} /> },
              { h: 'kgCO2e/FU', num: true, cell: (r: any) => fmt.t(r.per_functional_unit_kgco2e, 2) },
              { h: '', cell: (r: any) => (
                  <span className="link small" onClick={async () =>
                    setDeclaration(await api(`/lca/pcf/${r.id}/declaration`))}>
                    view declaration</span>) },
            ]} rows={d.items} />
          )}</Data>
          {declaration && (
            <div className="card" style={{ marginTop: 12 }}>
              <div className="row">
                <b>{declaration.label.claim}</b>
                <span className={`badge ${declaration.label.substantiated ? 'ok' : 'bad'}`}>
                  {declaration.label.substantiated ? 'substantiated' : 'NOT substantiated'}
                </span>
                <div className="spacer" />
                <button className="btn sm" onClick={() => setDeclaration(null)}>Close</button>
              </div>
              <p className="small muted">{declaration.label.substantiation_note}</p>
              <div className="row small">
                <span className="badge">Recycled {fmt.pct(declaration.label.recycled_content_pct, 0)}</span>
                <span className="badge">Recyclable {fmt.pct(declaration.label.recyclability_pct, 0)}</span>
                <span className="badge info">QR: {declaration.qr_url.slice(0, 46)}…</span>
              </div>
            </div>
          )}
        </Card>

        <Card title="Alternative materials available" note="FR-3.B.1">
          <Data of={materials}>{(rows: any[]) => (
            <Table cols={[
              { h: 'Material', cell: (r: any) => r.name },
              { h: 'Class', cell: (r: any) => r.material_class },
              { h: 'Recycled %', num: true, cell: (r: any) => fmt.t(r.recycled_content_pct, 0) },
              { h: 'Recyclable', cell: (r: any) => r.recyclable ? 'yes' : 'no' },
            ]} rows={rows} />
          )}</Data>
        </Card>
      </div>
    </Page>
  )
}

/* ======================= C · Suppliers & Scope 3 ======================== */

export function SupplierDirectory() {
  const [q, setQ] = useState('')
  const [tier, setTier] = useState('')
  const list = useApi(`/suppliers?page_size=50${q ? `&q=${encodeURIComponent(q)}` : ''}${tier ? `&tier=${tier}` : ''}`, [q, tier])
  const langs = useApi('/suppliers/languages')
  const [open, setOpen] = useState<number | null>(null)
  const detail = useApi(open ? `/suppliers/${open}` : null, [open])
  return (
    <Page title="Supplier directory" req="FR-3.C.1"
          sub="Onboarding with invitations, 25+ languages, reminders, progress tracking and materiality-based questionnaires."
          actions={
            <div className="row">
              <input placeholder="Search suppliers…" value={q} onChange={(e) => setQ(e.target.value)} />
              {['', '1', '2', '3'].map((t) => (
                <span key={t} className={`chip ${tier === t ? 'on' : ''}`} onClick={() => setTier(t)}>
                  {t ? `Tier ${t}` : 'All tiers'}</span>
              ))}
            </div>}>
      <div className="stack">
        <Data of={langs}>{(l: any) => (
          <Card title={`${l.count} supported languages`} note="FR-3.C.1">
            <div className="row">{l.languages.map((x: string) =>
              <span key={x} className="badge">{x}</span>)}</div>
          </Card>
        )}</Data>

        <Card title="Suppliers">
          <Data of={list}>{(d: any) => (
            <Table cols={[
              { h: 'Supplier', cell: (r: any) => <span className="link" onClick={() => setOpen(r.id)}>{r.name}</span> },
              { h: 'Tier', num: true, cell: (r: any) => r.tier },
              { h: 'Category', cell: (r: any) => r.category },
              { h: 'Country', cell: (r: any) => r.country },
              { h: 'Lang', cell: (r: any) => r.language },
              { h: 'Spend', num: true, cell: (r: any) => fmt.money(r.annual_spend) },
              { h: 'tCO2e', num: true, cell: (r: any) => fmt.t(r.tco2e, 0) },
              { h: 'Score', num: true, cell: (r: any) => fmt.t(r.score, 1) },
              { h: 'Maturity', cell: (r: any) => <StatusBadge status={r.maturity_level || 'unknown'} /> },
              { h: 'Onboarding', cell: (r: any) => <StatusBadge status={r.onboarding_status} /> },
              { h: 'Critical', cell: (r: any) => r.is_critical ? <span className="badge warn">critical</span> : '' },
            ]} rows={d.items} />
          )}</Data>
        </Card>

        {open && (
          <Data of={detail}>{(s: any) => (
            <Card title={s.name} note={`Tier ${s.tier} · ${s.country}`}
                  right={<button className="btn sm" onClick={() => setOpen(null)}>Close</button>}>
              <div className="grid g2">
                <div>
                  <h3>Sub-tier suppliers (FR-3.C.4)</h3>
                  <Table cols={[
                    { h: 'Supplier', cell: (r: any) => r.name },
                    { h: 'Tier', num: true, cell: (r: any) => r.tier },
                    { h: 'Country', cell: (r: any) => r.country },
                  ]} rows={s.sub_tier_suppliers} empty="No sub-tier suppliers mapped." />
                </div>
                <div>
                  <h3>Scorecard history (FR-3.C.3)</h3>
                  <Table cols={[
                    { h: 'Year', num: true, cell: (r: any) => r.period_year },
                    { h: 'Score', num: true, cell: (r: any) => fmt.t(r.overall_score, 1) },
                    { h: 'YoY', num: true, cell: (r: any) => fmt.t(r.yoy_delta, 1) },
                    { h: 'Maturity', cell: (r: any) => <StatusBadge status={r.maturity_level} /> },
                    { h: 'Rank', num: true, cell: (r: any) => r.rank },
                  ]} rows={s.scorecards} />
                </div>
              </div>
              <h3 style={{ marginTop: 14 }}>Action plans (FR-3.C.3)</h3>
              <Table cols={[
                { h: 'Plan', cell: (r: any) => r.title },
                { h: 'Type', cell: (r: any) => <StatusBadge status={r.plan_type} /> },
                { h: 'Assistance', cell: (r: any) => r.assistance_offered },
                { h: 'Due', cell: (r: any) => fmt.date(r.due_date) },
                { h: 'Abatement', num: true, cell: (r: any) => `${fmt.t(r.expected_abatement_tco2e, 0)} t` },
                { h: 'Progress', cell: (r: any) => <Bar pct={r.progress_pct} color="var(--accent)" /> },
              ]} rows={s.action_plans} empty="No action plans." />
            </Card>
          )}</Data>
        )}
      </div>
    </Page>
  )
}

export function Campaigns() {
  const list = useApi('/suppliers/campaigns/list')
  const [open, setOpen] = useState<number | null>(null)
  const detail = useApi(open ? `/suppliers/campaigns/${open}` : null, [open])
  return (
    <Page title="Campaigns & submissions" req="FR-3.C.1 / FR-3.C.2"
          sub="Invitations, reminders and progress tracking; primary-data collection through forms, documents/OCR, APIs and mobile capture with validations and attestations.">
      <div className="stack">
        <Card title="Campaigns">
          <Data of={list}>{(rows: any[]) => (
            <Table cols={[
              { h: 'Campaign', cell: (r: any) => <span className="link" onClick={() => setOpen(r.id)}>{r.name}</span> },
              { h: 'Due', cell: (r: any) => fmt.date(r.due_date) },
              { h: 'Invited', num: true, cell: (r: any) => r.progress.invited },
              { h: 'Responded', num: true, cell: (r: any) => r.progress.responded },
              { h: 'Response rate', cell: (r: any) => (
                  <div style={{ minWidth: 120 }}>
                    <Bar pct={r.progress.response_rate_pct} color="var(--accent)" />
                    <span className="small muted">{fmt.pct(r.progress.response_rate_pct)}</span>
                  </div>) },
              { h: 'Reminders', num: true, cell: (r: any) => r.progress.reminders_sent },
              { h: 'Languages', cell: (r: any) => (r.progress.languages_used || []).join(', ') },
              { h: '', cell: (r: any) => (
                  <ActionButton label="Send reminders"
                                run={() => post(`/suppliers/campaigns/${r.id}/remind`)}
                                onDone={() => list.reload()} />) },
            ]} rows={rows} />
          )}</Data>
        </Card>

        {open && (
          <Card title="Invitations & submissions"
                right={<button className="btn sm" onClick={() => setOpen(null)}>Close</button>}>
            <Data of={detail}>{(d: any) => (
              <Table cols={[
                { h: 'Supplier', cell: (r: any) => r.supplier_name },
                { h: 'Country', cell: (r: any) => r.supplier_country },
                { h: 'Category', cell: (r: any) => r.supplier_category },
                { h: 'Language', cell: (r: any) => r.language },
                { h: 'Status', cell: (r: any) => <StatusBadge status={r.submission_status} /> },
                { h: 'Completeness', cell: (r: any) => (
                    <div style={{ minWidth: 110 }}>
                      <Bar pct={r.completeness_pct} />
                      <span className="small muted">{fmt.pct(r.completeness_pct)}</span>
                    </div>) },
                { h: 'Reminders', num: true, cell: (r: any) => r.reminders_sent },
              ]} rows={d.invitations} />
            )}</Data>
          </Card>
        )}
      </div>
    </Page>
  )
}

export function Scorecards() {
  const list = useApi('/suppliers/scorecards/list?year=2025&page_size=50')
  const plans = useApi('/suppliers/action-plans/list')
  return (
    <Page title="Supplier scorecards & plans" req="FR-3.C.3"
          sub="Scorecards, maturity assessments, rankings, year-over-year performance, improvement plans, assistance and joint reduction projects."
          actions={<ActionButton label="Recompute scorecards"
                                 run={() => post('/suppliers/scorecards/compute',
                                                 { organization_id: 1, year: 2025 })}
                                 onDone={() => list.reload()} />}>
      <div className="stack">
        <Card title="Rankings">
          <Data of={list}>{(d: any) => (
            <Table cols={[
              { h: 'Rank', num: true, cell: (r: any) => r.rank },
              { h: 'Supplier', cell: (r: any) => r.supplier_name },
              { h: 'Category', cell: (r: any) => r.supplier_category },
              { h: 'Cat. rank', num: true, cell: (r: any) => r.category_rank },
              { h: 'Overall', num: true, cell: (r: any) => fmt.t(r.overall_score, 1) },
              { h: 'Disclosure', num: true, cell: (r: any) => fmt.t(r.disclosure_score, 0) },
              { h: 'Performance', num: true, cell: (r: any) => fmt.t(r.performance_score, 0) },
              { h: 'Data quality', num: true, cell: (r: any) => fmt.t(r.data_quality_score, 0) },
              { h: 'Targets', num: true, cell: (r: any) => fmt.t(r.target_score, 0) },
              { h: 'Maturity', cell: (r: any) => <StatusBadge status={r.maturity_level} /> },
              { h: 'YoY', num: true, cell: (r: any) => (
                  <span className={r.yoy_delta >= 0 ? 'down' : 'up'}>
                    {r.yoy_delta >= 0 ? '+' : ''}{fmt.t(r.yoy_delta, 1)}</span>) },
              { h: 'tCO2e', num: true, cell: (r: any) => fmt.t(r.emissions_tco2e, 0) },
            ]} rows={d.items} />
          )}</Data>
        </Card>
        <Card title="Improvement plans & joint projects">
          <Data of={plans}>{(rows: any[]) => (
            <Table cols={[
              { h: 'Plan', cell: (r: any) => r.title },
              { h: 'Type', cell: (r: any) => <StatusBadge status={r.plan_type} /> },
              { h: 'Owner', cell: (r: any) => r.owner },
              { h: 'Assistance offered', cell: (r: any) => r.assistance_offered },
              { h: 'Due', cell: (r: any) => fmt.date(r.due_date) },
              { h: 'Priority', cell: (r: any) => <StatusBadge status={r.priority} /> },
              { h: 'Abatement', num: true, cell: (r: any) => `${fmt.t(r.expected_abatement_tco2e, 0)} t` },
              { h: 'Progress', cell: (r: any) => <Bar pct={r.progress_pct} color="var(--accent)" /> },
            ]} rows={rows} />
          )}</Data>
        </Card>
      </div>
    </Page>
  )
}

export function SupplierNetwork() {
  const net = useApi('/suppliers/network/map?organization_id=1&year=2025')
  const res = useApi('/suppliers/network/resilience-scenarios?organization_id=1&year=2025')
  return (
    <Page title="Supply network & hotspots" req="FR-3.C.4"
          sub="Multi-tier network maps, geographic heat maps, supplier and category hotspots, outliers, alternative sourcing and resilience/emissions scenarios.">
      <Data of={net}>{(d: any) => (
        <div className="stack">
          <div className="grid g4">
            <KPI label="Suppliers mapped" value={d.supplier_count} detail={`${d.tiers.length} tiers`} />
            <KPI label="Supply-chain emissions" value={fmt.t(d.total_tco2e, 0)} detail="tCO2e" />
            <KPI label="Countries" value={d.geographic_heatmap.length} detail="in the heat map" />
            <KPI label="Outliers" value={d.outliers.length} detail="beyond 2σ intensity" />
          </div>

          <Card title="Geographic heat map" note="FR-3.C.4">
            <GeoMap points={d.nodes.map((n: any) => ({ ...n, name: n.name }))} />
          </Card>

          <div className="grid g2">
            <Card title="Multi-tier structure">
              <Table cols={[
                { h: 'Tier', cell: (r: any) => `Tier ${r.tier}` },
                { h: 'Suppliers', num: true, cell: (r: any) => r.supplier_count },
                { h: 'tCO2e', num: true, cell: (r: any) => fmt.t(r.tco2e, 0) },
              ]} rows={d.tiers} />
              <h3 style={{ marginTop: 14 }}>Tier links</h3>
              <Table cols={[
                { h: 'Sub-tier supplier', cell: (r: any) => (
                    d.nodes.find((n: any) => n.id === r.source)?.name) },
                { h: 'Supplies', cell: (r: any) => (
                    d.nodes.find((n: any) => n.id === r.target)?.name) },
                { h: 'Step', cell: (r: any) => r.tier_step },
              ]} rows={d.edges} empty="No multi-tier links mapped." />
            </Card>
            <Card title="Category hotspots">
              <Table cols={[
                { h: 'Category', cell: (r: any) => r.category },
                { h: 'tCO2e', num: true, cell: (r: any) => fmt.t(r.tco2e, 0) },
                { h: 'Share', num: true, cell: (r: any) => fmt.pct(r.share_pct) },
                { h: '', cell: (r: any) => <Bar pct={r.share_pct} color="var(--s3)" /> },
                { h: 'Suppliers', num: true, cell: (r: any) => r.supplier_count },
              ]} rows={d.category_hotspots} />
            </Card>
          </div>

          <div className="grid g2">
            <Card title="Supplier hotspots">
              <Table cols={[
                { h: 'Supplier', cell: (r: any) => r.name },
                { h: 'Country', cell: (r: any) => r.country },
                { h: 'tCO2e', num: true, cell: (r: any) => fmt.t(r.tco2e, 0) },
                { h: 'Share', num: true, cell: (r: any) => fmt.pct(r.share_pct) },
              ]} rows={d.supplier_hotspots.slice(0, 10)} />
            </Card>
            <Card title="Outliers" note="emission intensity beyond 2 standard deviations">
              <Table cols={[
                { h: 'Supplier', cell: (r: any) => r.name },
                { h: 'Intensity', num: true, cell: (r: any) => fmt.t(r.intensity_tco2e_per_m_spend, 1) },
                { h: 'Peer mean', num: true, cell: (r: any) => fmt.t(r.peer_mean, 1) },
                { h: 'z', num: true, cell: (r: any) => fmt.t(r.z_score, 2) },
                { h: '', cell: (r: any) => (
                    <span className={`badge ${r.direction === 'high' ? 'bad' : 'ok'}`}>{r.direction}</span>) },
              ]} rows={d.outliers} empty="No statistical outliers." />
            </Card>
          </div>

          <Card title="Alternative sourcing & resilience scenarios" note="FR-3.C.4">
            <Data of={res}>{(r: any) => (
              <Table cols={[
                { h: 'Scenario', cell: (x: any) => x.scenario },
                { h: 'Current', cell: (x: any) => `${x.current_supplier} (${x.current_country})` },
                { h: 'tCO2e now', num: true, cell: (x: any) => fmt.t(x.current_tco2e, 0) },
                { h: 'Alternative', cell: (x: any) => x.alternative_supplier
                    ? `${x.alternative_supplier} (${x.alternative_country})` : '—' },
                { h: 'Projected', num: true, cell: (x: any) => fmt.t(x.projected_tco2e, 0) },
                { h: 'Delta', num: true, cell: (x: any) => (
                    <span className={x.delta_tco2e > 0 ? 'up' : 'down'}>{fmt.t(x.delta_tco2e, 0)}</span>) },
                { h: 'Single source', cell: (x: any) => x.single_source_risk
                    ? <span className="badge warn">risk</span> : '' },
              ]} rows={r.scenarios} />
            )}</Data>
          </Card>
        </div>
      )}</Data>
    </Page>
  )
}

export function Procurement() {
  const list = useApi('/suppliers/procurement/decisions')
  const [open, setOpen] = useState<number | null>(1)
  const detail = useApi(open ? `/suppliers/procurement/decisions/${open}` : null, [open])
  const strategy = useApi('/suppliers/procurement/category-strategy?organization_id=1&year=2025')
  return (
    <Page title="Procurement decisions" req="FR-3.C.5"
          sub="Carbon-weighted bids, carbon-inclusive TCO, category strategies, contract clauses, KPIs, audits and data agreements.">
      <div className="stack">
        <Card title="Tenders">
          <Data of={list}>{(rows: any[]) => (
            <Table cols={[
              { h: 'Decision', cell: (r: any) => <span className="link" onClick={() => setOpen(r.id)}>{r.title}</span> },
              { h: 'Category', cell: (r: any) => r.category },
              { h: 'Carbon weight', num: true, cell: (r: any) => fmt.pct(r.carbon_weight_pct, 0) },
              { h: 'Internal price', num: true, cell: (r: any) => fmt.money(r.internal_carbon_price) },
              { h: 'Bids', num: true, cell: (r: any) => r.bid_count },
              { h: 'Status', cell: (r: any) => <StatusBadge status={r.status} /> },
            ]} rows={rows} />
          )}</Data>
        </Card>

        {open && (
          <Card title="Carbon-weighted bid evaluation" note="FR-3.C.5">
            <Data of={detail}>{(d: any) => (
              <div className="stack">
                <p className="small muted">{d.explanation}</p>
                <Table cols={[
                  { h: 'Rank', num: true, cell: (r: any) => r.rank },
                  { h: 'Supplier', cell: (r: any) => r.supplier_name },
                  { h: 'Country', cell: (r: any) => r.supplier_country },
                  { h: 'Financial TCO', num: true, cell: (r: any) => fmt.money(r.financial_tco) },
                  { h: 'Carbon tCO2e', num: true, cell: (r: any) => fmt.t(r.total_carbon_tco2e, 1) },
                  { h: 'Carbon cost', num: true, cell: (r: any) => fmt.money(r.carbon_cost) },
                  { h: 'Carbon-inclusive TCO', num: true, cell: (r: any) => fmt.money(r.carbon_inclusive_tco) },
                  { h: 'Quality', num: true, cell: (r: any) => fmt.t(r.quality_score, 0) },
                  { h: 'Weighted score', num: true, cell: (r: any) => (
                      <b className={r.rank === 1 ? 'down' : ''}>{fmt.t(r.weighted_score, 1)}</b>) },
                ]} rows={d.bids} />
              </div>
            )}</Data>
          </Card>
        )}

        <Card title="Category strategies, KPIs & contract clauses" note="FR-3.C.5">
          <Data of={strategy}>{(s: any) => (
            <Table cols={[
              { h: 'Category', cell: (r: any) => r.category },
              { h: 'Priority', cell: (r: any) => <StatusBadge status={r.priority} /> },
              { h: 'tCO2e', num: true, cell: (r: any) => fmt.t(r.tco2e, 0) },
              { h: 'Share', num: true, cell: (r: any) => fmt.pct(r.share_pct) },
              { h: 'Spend', num: true, cell: (r: any) => fmt.money(r.spend) },
              { h: 'Intensity', num: true, cell: (r: any) => fmt.t(r.intensity_tco2e_per_m_spend, 1) },
              { h: 'Data agreements', num: true, cell: (r: any) => fmt.pct(r.kpis.data_agreement_coverage_pct, 0) },
              { h: 'Engagement', num: true, cell: (r: any) => fmt.pct(r.kpis.engagement_coverage_pct, 0) },
              { h: 'Audits due', num: true, cell: (r: any) => r.kpis.audit_due },
              { h: 'Recommended clauses', cell: (r: any) => (
                  <span className="small muted">{r.recommended_clauses.join(' · ')}</span>) },
            ]} rows={s.strategies} />
          )}</Data>
        </Card>
      </div>
    </Page>
  )
}
