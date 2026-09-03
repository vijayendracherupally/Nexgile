import React, { useState } from 'react'
import { api, fmt, post, useApi } from '../lib/api'
import {
  ActionButton, Bar, BarChart, Card, DQBadge, Data, Donut, GeoMap, KPI, LineChart,
  LineageDrawer, Page, StatusBadge, Table,
} from '../components/ui'

/* ================= D · Analytics & reduction planning =================== */

export function DataQuality() {
  const q = useApi('/analytics/data-quality/scores?year=2025')
  const assess = useApi('/analytics/data-quality/assessments?page_size=25')
  const changes = useApi('/analytics/change-history?page_size=25')
  return (
    <Page title="Data quality" req="FR-3.D.4 / FR-7.4"
          sub="Completeness, validation, anomaly flags, estimation and gap filling, uncertainty, confidence scoring, remediation tasks and evidence status."
          actions={<ActionButton label="Run validation pass"
                                 run={() => post('/analytics/data-quality/validate',
                                                 { entity_id: 2, year: 2025 })}
                                 onDone={() => assess.reload()} />}>
      <Data of={q}>{(d: any) => (
        <div className="stack">
          <div className="grid g4">
            <KPI label="Average confidence" value={fmt.t(d.average_confidence_score, 1)}
                 detail="0–100 across all reported values" />
            <KPI label="Factor confidence" value={fmt.t(d.average_factor_confidence, 1)}
                 detail="derived from factor uncertainty" />
            <KPI label="Completeness" value={fmt.pct(d.completeness_pct, 1)}
                 detail={`${fmt.pct(d.estimated_share_pct)} of tonnes are estimated`} />
            <KPI label="Open findings" value={d.open_anomalies + d.open_gaps}
                 detail={`${d.open_anomalies} anomalies · ${d.open_gaps} gaps`} />
          </div>

          <div className="grid g2">
            <Card title="Emissions by data-quality rating" note={d.pedigree_model}>
              <Table cols={[
                { h: 'Rating', cell: (r: any) => <DQBadge rating={r.rating} /> },
                { h: 'Records', num: true, cell: (r: any) => fmt.n(r.count) },
                { h: 'tCO2e', num: true, cell: (r: any) => fmt.t(r.tco2e, 0) },
                { h: 'Share', num: true, cell: (r: any) => fmt.pct(r.share_pct) },
                { h: '', cell: (r: any) => <Bar pct={r.share_pct} /> },
              ]} rows={d.by_rating} />
            </Card>
            <Card title="By data origin" note="measured beats estimated">
              <Table cols={[
                { h: 'Origin', cell: (r: any) => fmt.label(r.data_origin) },
                { h: 'tCO2e', num: true, cell: (r: any) => fmt.t(r.tco2e, 0) },
                { h: 'Share', num: true, cell: (r: any) => fmt.pct(r.share_pct) },
                { h: '', cell: (r: any) => <Bar pct={r.share_pct} color="var(--accent)" /> },
              ]} rows={d.by_data_origin} />
            </Card>
          </div>

          <Card title="Validation findings" note="FR-7.4">
            <Data of={assess}>{(a: any) => (
              <Table cols={[
                { h: 'Object', cell: (r: any) => `${fmt.label(r.object_type)} #${r.object_id}` },
                { h: 'Scope', cell: (r: any) => fmt.label(r.scope) },
                { h: 'Completeness', num: true, cell: (r: any) => fmt.pct(r.completeness_pct, 0) },
                { h: 'Passed', cell: (r: any) => r.validation_passed
                    ? <span className="badge ok">passed</span> : <span className="badge bad">failed</span> },
                { h: 'Messages', cell: (r: any) => (
                    <span className="small muted">
                      {(r.validation_messages || []).map((m: any) => m.message).join(' · ')}</span>) },
                { h: 'Evidence', cell: (r: any) => <StatusBadge status={r.evidence_status} /> },
                { h: 'Confidence', num: true, cell: (r: any) => fmt.t(r.confidence_score, 0) },
              ]} rows={a.items} empty="No findings — run a validation pass." />
            )}</Data>
          </Card>

          <Card title="Change history" note="FR-3.D.4 / FR-7.2">
            <Data of={changes}>{(c: any) => (
              <Table cols={[
                { h: 'When', cell: (r: any) => String(r.at).replace('T', ' ').slice(0, 19) },
                { h: 'Action', cell: (r: any) => <StatusBadge status={r.action} /> },
                { h: 'Object', cell: (r: any) => `${fmt.label(r.object_type)} #${r.object_id ?? ''}` },
                { h: 'User', cell: (r: any) => r.user_email || 'system' },
                { h: 'Reason', cell: (r: any) => r.reason },
              ]} rows={c.items} />
            )}</Data>
          </Card>
        </div>
      )}</Data>
    </Page>
  )
}

export function Anomalies() {
  const anomalies = useApi('/analytics/anomalies?page_size=30')
  const gaps = useApi('/analytics/gaps')
  const [forecast, setForecast] = useState<any>(null)
  const [spend, setSpend] = useState<any>(null)
  return (
    <Page title="Anomalies, gaps & forecasting" req="FR-3.D.1"
          sub="Automated spend categorization, invoice/document extraction, emissions anomaly detection, gap identification and predictive forecasting."
          actions={
            <div className="row">
              <ActionButton label="Detect anomalies" run={() => post('/analytics/anomalies/detect', {})}
                            onDone={() => anomalies.reload()} />
              <ActionButton label="Identify gaps"
                            run={() => post('/analytics/gaps/identify', { entity_id: 2, year: 2025 })}
                            onDone={() => gaps.reload()} />
              <ActionButton label="Categorize spend" run={() => post('/analytics/spend/categorize', {})}
                            onDone={setSpend} />
              <ActionButton label="Forecast" run={() => api('/analytics/forecast?entity_id=1&horizon_years=6')}
                            onDone={setForecast} />
            </div>}>
      <div className="stack">
        {spend && (
          <Card title="Spend categorization result" note="FR-3.D.1">
            <div className="row" style={{ marginBottom: 8 }}>
              <span className="badge">{spend.examined} examined</span>
              <span className="badge ok">{spend.categorized} categorized</span>
              <span className="badge warn">{spend.requires_human_review} need review</span>
              <span className="badge">{fmt.pct(spend.coverage_pct, 0)} coverage</span>
            </div>
            <Table cols={[
              { h: '#', num: true, cell: (r: any) => r.category_number },
              { h: 'Category', cell: (r: any) => r.category },
              { h: 'Transactions', num: true, cell: (r: any) => r.transaction_count },
              { h: 'Amount', num: true, cell: (r: any) => fmt.money(r.amount) },
              { h: 'Avg confidence', num: true, cell: (r: any) => fmt.t(r.avg_confidence * 100, 0) },
            ]} rows={spend.by_category} />
          </Card>
        )}

        {forecast && (
          <Card title="Predictive forecast" note={`${fmt.label(forecast.method)} · R² ${forecast.r_squared} · confidence ${forecast.confidence}`}>
            <LineChart series={[
              { name: 'History', color: 'var(--accent-2)',
                points: (forecast.history || []).map((p: any) => ({ x: p.year, y: p.tco2e })) },
              { name: 'Projection', color: 'var(--warn)', dashed: true,
                points: (forecast.projection || []).map((p: any) => ({ x: p.year, y: p.tco2e })) },
              { name: 'Upper band', color: 'var(--dim)', dashed: true,
                points: (forecast.projection || []).map((p: any) => ({ x: p.year, y: p.high })) },
              { name: 'Lower band', color: 'var(--dim)', dashed: true,
                points: (forecast.projection || []).map((p: any) => ({ x: p.year, y: p.low })) },
            ]} />
            <div className="row small muted" style={{ marginTop: 8 }}>
              Trend {fmt.t(forecast.annual_trend_tco2e, 1)} tCO2e/yr ({fmt.t(forecast.annual_trend_pct, 2)}%/yr)
            </div>
          </Card>
        )}

        <Card title="Anomaly inbox" note="FR-3.D.1">
          <Data of={anomalies}>{(d: any) => (
            <Table cols={[
              { h: 'Detected', cell: (r: any) => fmt.date(r.detected_at) },
              { h: 'Type', cell: (r: any) => <StatusBadge status={r.anomaly_type} /> },
              { h: 'Severity', cell: (r: any) => <StatusBadge status={r.severity} /> },
              { h: 'Object', cell: (r: any) => `${fmt.label(r.object_type)} #${r.object_id}` },
              { h: 'Observed', num: true, cell: (r: any) => fmt.n(r.observed_value, 1) },
              { h: 'Expected', num: true, cell: (r: any) => fmt.n(r.expected_value, 1) },
              { h: 'Deviation', num: true, cell: (r: any) => fmt.pct(r.deviation_pct) },
              { h: 'z', num: true, cell: (r: any) => fmt.t(r.z_score, 2) },
              { h: 'Explanation', cell: (r: any) => <span className="small muted">{r.explanation}</span> },
              { h: 'Status', cell: (r: any) => <StatusBadge status={r.status} /> },
            ]} rows={d.items} />
          )}</Data>
        </Card>

        <Card title="Data gaps & estimation basis" note="FR-3.D.1 / FR-7.4">
          <Data of={gaps}>{(rows: any[]) => (
            <Table cols={[
              { h: 'Gap type', cell: (r: any) => <StatusBadge status={r.gap_type} /> },
              { h: 'Scope', cell: (r: any) => fmt.label(r.scope) },
              { h: 'Period', cell: (r: any) => r.period_label },
              { h: 'Description', cell: (r: any) => r.description },
              { h: 'Estimated tCO2e', num: true, cell: (r: any) => fmt.t(r.estimated_co2e_kg / 1000, 2) },
              { h: 'Method', cell: (r: any) => <span className="small muted">{r.estimation_method}</span> },
              { h: 'Status', cell: (r: any) => <StatusBadge status={r.status} /> },
            ]} rows={rows} />
          )}</Data>
        </Card>
      </div>
    </Page>
  )
}

export function Scenarios() {
  const list = useApi('/analytics/scenarios')
  const [open, setOpen] = useState<number | null>(null)
  const detail = useApi(open ? `/analytics/scenarios/${open}` : null, [open])
  const [compare, setCompare] = useState<any>(null)
  const sbti = useApi('/analytics/pathways/sbti?entity_id=1&base_year=2022')
  return (
    <Page title="Scenarios & what-if" req="FR-3.D.2 / FR-7.8"
          sub="What-if modelling, Monte Carlo uncertainty, sensitivity analysis, internal carbon price impacts and SBTi-aligned pathway optimization — always isolated from approved actuals."
          actions={<Data of={list}>{(rows: any[]) => (
            <ActionButton label="Compare all scenarios"
                          run={() => post('/analytics/scenarios/compare',
                                          { scenario_ids: rows.map((r: any) => r.id) })}
                          onDone={setCompare} />
          )}</Data>}>
      <div className="stack">
        <Card title="Scenario isolation" note="FR-7.8">
          <p className="small muted" style={{ margin: 0 }}>
            Scenarios live in a separate address space. Every scenario-touchable row carries a
            <code> scenario_id</code>; <code>NULL</code> means approved actuals, and a write made
            inside a scenario cannot target <code>NULL</code>. Forecasts and what-ifs therefore
            <b> never alter approved actuals</b>. Switch context with the Scenario selector in the top bar.
          </p>
        </Card>

        <Card title="Scenarios">
          <Data of={list}>{(rows: any[]) => (
            <Table cols={[
              { h: 'Scenario', cell: (r: any) => <span className="link" onClick={() => setOpen(r.id)}>{r.name}</span> },
              { h: 'Type', cell: (r: any) => <StatusBadge status={r.scenario_type} /> },
              { h: 'Base', num: true, cell: (r: any) => r.base_year },
              { h: 'Horizon', num: true, cell: (r: any) => r.horizon_year },
              { h: 'Levers', num: true, cell: (r: any) => (r.selected_lever_ids || []).length },
              { h: 'Carbon price', num: true, cell: (r: any) => fmt.money(r.internal_carbon_price) },
              { h: 'Method', cell: (r: any) => r.method_version },
              { h: 'Factor lib', cell: (r: any) => r.factor_library_version },
              { h: 'Status', cell: (r: any) => <StatusBadge status={r.status} /> },
              { h: '', cell: (r: any) => (
                  <ActionButton label="Run" run={() => post(`/analytics/scenarios/${r.id}/run`)}
                                onDone={() => { setOpen(r.id); list.reload() }} />) },
            ]} rows={rows} />
          )}</Data>
        </Card>

        {compare && (
          <Card title="Scenario comparison" note="assumptions, versions, uncertainty and levers"
                right={<button className="btn sm" onClick={() => setCompare(null)}>Close</button>}>
            <p className="small muted">{compare.comparison_note}</p>
            <LineChart series={compare.scenarios.map((s: any, i: number) => ({
              name: s.name,
              color: ['var(--accent-2)', 'var(--accent)', 'var(--s1)', 'var(--s3)'][i % 4],
              points: (s.trajectory || []).map((p: any) => ({ x: p.year, y: p.projected_tco2e })),
            }))} />
            <Table cols={[
              { h: 'Scenario', cell: (r: any) => r.name },
              { h: 'Baseline', num: true, cell: (r: any) => fmt.t(r.baseline_tco2e, 0) },
              { h: 'At horizon', num: true, cell: (r: any) => fmt.t(r.final_projected_tco2e, 0) },
              { h: 'Reduction', num: true, cell: (r: any) => fmt.pct(r.total_reduction_pct) },
              { h: 'Capex', num: true, cell: (r: any) => fmt.money(r.total_capex) },
              { h: '/tCO2e', num: true, cell: (r: any) => fmt.money(r.cost_per_tonne_abated) },
              { h: 'Levers', num: true, cell: (r: any) => (r.levers_applied || []).length },
              { h: 'Uncertainty', num: true, cell: (r: any) => fmt.pct(r.uncertainty?.uncertainty_pct) },
              { h: 'SBTi', cell: (r: any) => r.sbti_on_track
                  ? <span className="badge ok">on track</span> : <span className="badge bad">off track</span> },
              { h: 'Versions', cell: (r: any) => (
                  <span className="small muted">{r.method_version} · {r.factor_library_version}</span>) },
            ]} rows={compare.scenarios} />
          </Card>
        )}

        {open && (
          <Data of={detail}>{(s: any) => {
            const r = s.results || {}
            const mc = s.uncertainty?.monte_carlo || {}
            return (
              <div className="stack">
                <Card title={`${s.name} — results`}
                      right={<button className="btn sm" onClick={() => setOpen(null)}>Close</button>}>
                  <div className="grid g4">
                    <KPI label="Baseline" value={fmt.t(r.baseline_tco2e, 0)} detail={`tCO2e in ${r.baseline_year}`} />
                    <KPI label={`Projected ${r.horizon_year}`} value={fmt.t(r.final_projected_tco2e, 0)}
                         detail={`−${fmt.t(r.total_reduction_pct, 1)}% vs baseline`} tone="down" />
                    <KPI label="Capex" value={fmt.money(r.total_capex)}
                         detail={`${fmt.money(r.cost_per_tonne_abated)} per tCO2e abated`} />
                    <KPI label="SBTi gap" value={fmt.t(r.sbti?.gap_to_pathway_tco2e, 0)}
                         detail={r.sbti?.on_track ? 'within the 1.5C pathway' : 'above the pathway'}
                         tone={r.sbti?.on_track ? 'down' : 'up'} />
                  </div>
                </Card>

                <Card title="Trajectory vs business as usual vs SBTi pathway">
                  <LineChart series={[
                    { name: 'Business as usual', color: 'var(--danger)',
                      points: (r.trajectory || []).map((p: any) => ({ x: p.year, y: p.business_as_usual_tco2e })) },
                    { name: 'Scenario projection', color: 'var(--accent)',
                      points: (r.trajectory || []).map((p: any) => ({ x: p.year, y: p.projected_tco2e })) },
                    { name: 'SBTi allowed', color: 'var(--accent-2)', dashed: true,
                      points: (r.sbti?.pathway || []).filter((p: any) => p.year <= r.horizon_year)
                        .map((p: any) => ({ x: p.year, y: p.allowed_tco2e })) },
                  ]} />
                </Card>

                <div className="grid g2">
                  <Card title="Monte Carlo uncertainty" note="FR-3.D.2">
                    <div className="row" style={{ marginBottom: 8 }}>
                      <span className="badge">p5 {fmt.t(mc.p5, 0)}</span>
                      <span className="badge info">p50 {fmt.t(mc.p50, 0)}</span>
                      <span className="badge">p95 {fmt.t(mc.p95, 0)}</span>
                      <span className="badge warn">σ {fmt.t(mc.std_dev, 0)}</span>
                      <span className="badge">{fmt.n(mc.iterations)} iterations</span>
                    </div>
                    <BarChart data={(mc.histogram || []).map((h: any) => ({
                      b: fmt.t(h.bin_start, 0), c: h.count }))} x="b" y="c" height={150} />
                  </Card>
                  <Card title="Sensitivity (tornado)" note="FR-3.D.2">
                    <Table cols={[
                      { h: 'Driver', cell: (x: any) => x.driver },
                      { h: 'Contribution', num: true, cell: (x: any) => fmt.t(x.contribution, 0) },
                      { h: 'Share', num: true, cell: (x: any) => fmt.pct(x.share_pct) },
                      { h: 'Swing ±10%', num: true, cell: (x: any) => fmt.t(x.swing, 0) },
                      { h: '', cell: (x: any) => <Bar pct={Math.abs(x.share_pct)} color="var(--s1)" /> },
                    ]} rows={s.uncertainty?.sensitivity || []} />
                  </Card>
                </div>

                <div className="grid g2">
                  <Card title="Assumptions used">
                    <Table cols={[
                      { h: 'Assumption', cell: (x: any) => fmt.label(x[0]) },
                      { h: 'Value', num: true, cell: (x: any) => String(x[1]) },
                    ]} rows={Object.entries(r.assumptions_used || {})} />
                  </Card>
                  <Card title="Levers applied">
                    <Table cols={[
                      { h: 'Lever', cell: (x: any) => x.name },
                      { h: 'tCO2e/yr', num: true, cell: (x: any) => fmt.t(x.annual_abatement_tco2e, 0) },
                      { h: 'Capex', num: true, cell: (x: any) => fmt.money(x.capex) },
                    ]} rows={r.levers_applied || []} empty="No levers selected." />
                  </Card>
                </div>
              </div>
            )
          }}</Data>
        )}

        <Card title="SBTi pathway vs actuals" note="FR-3.D.2">
          <Data of={sbti}>{(d: any) => (
            <>
              <div className="row" style={{ marginBottom: 8 }}>
                <span className="badge info">{d.ambition}</span>
                <span className="badge">{fmt.pct(d.annual_linear_reduction_pct)} linear annual reduction</span>
                <span className="badge">−{fmt.pct(d.required_reduction_by_2030_pct, 0)} required by 2030</span>
              </div>
              <LineChart series={[
                { name: 'Allowed (1.5C)', color: 'var(--accent-2)', dashed: true,
                  points: d.pathway.filter((p: any) => p.year <= 2040)
                    .map((p: any) => ({ x: p.year, y: p.allowed_tco2e })) },
                { name: 'Actual', color: 'var(--warn)',
                  points: d.pathway.filter((p: any) => p.actual_tco2e != null)
                    .map((p: any) => ({ x: p.year, y: p.actual_tco2e })) },
              ]} />
            </>
          )}</Data>
        </Card>
      </div>
    </Page>
  )
}

export function Reduction() {
  const macc = useApi('/analytics/macc')
  const roadmap = useApi('/analytics/roadmap?entity_id=1')
  const progress = useApi('/analytics/progress?entity_id=1')
  const pareto = useApi('/analytics/hotspots/pareto?year=2025&dimension=category')
  const [dim, setDim] = useState('category')
  const paretoDim = useApi(`/analytics/hotspots/pareto?year=2025&dimension=${dim}`, [dim])
  return (
    <Page title="Reduction levers, MACC & roadmap" req="FR-3.D.3"
          sub="Hotspot Pareto analysis, reduction levers, technology roadmaps, marginal abatement comparisons, investment priority, ROI and progress tracking.">
      <div className="stack">
        <Card title="Hotspot Pareto analysis" note="FR-3.D.3"
              right={
                <div className="row">
                  {['category', 'facility', 'supplier', 'scope', 'entity'].map((d) => (
                    <span key={d} className={`chip ${dim === d ? 'on' : ''}`} onClick={() => setDim(d)}>
                      {fmt.label(d)}</span>))}
                </div>}>
          <Data of={paretoDim}>{(d: any) => (
            <>
              <p className="small muted">{d.interpretation}</p>
              <Table cols={[
                { h: fmt.label(d.dimension), cell: (r: any) => r.name },
                { h: 'tCO2e', num: true, cell: (r: any) => fmt.t(r.tco2e, 0) },
                { h: 'Share', num: true, cell: (r: any) => fmt.pct(r.share_pct) },
                { h: 'Cumulative', num: true, cell: (r: any) => fmt.pct(r.cumulative_pct) },
                { h: '', cell: (r: any) => <Bar pct={r.cumulative_pct}
                    color={r.in_vital_few ? 'var(--danger)' : 'var(--line)'} /> },
                { h: '', cell: (r: any) => r.in_vital_few
                    ? <span className="badge bad">vital few</span> : '' },
              ]} rows={d.items.slice(0, 15)} />
            </>
          )}</Data>
        </Card>

        <Card title="Marginal abatement cost curve" note="FR-3.D.3">
          <Data of={macc}>{(d: any) => (
            <div className="stack">
              <div className="grid g3">
                <KPI label="Total annual abatement" value={fmt.t(d.total_annual_abatement_tco2e, 0)} detail="tCO2e/yr" />
                <KPI label="Total capex" value={fmt.money(d.total_capex)} detail="across all levers" />
                <KPI label="Negative-cost abatement" value={fmt.t(d.negative_cost_abatement_tco2e, 0)}
                     detail="tCO2e/yr that pays for itself" tone="down" />
              </div>
              <p className="small muted">{d.note}</p>
              <Table cols={[
                { h: '#', num: true, cell: (r: any) => r.investment_priority },
                { h: 'Lever', cell: (r: any) => r.name },
                { h: 'Category', cell: (r: any) => fmt.label(r.lever_category) },
                { h: 'Scope', cell: (r: any) => fmt.label(r.scope) },
                { h: 'tCO2e/yr', num: true, cell: (r: any) => fmt.t(r.annual_abatement_tco2e, 0) },
                { h: 'MAC €/t', num: true, cell: (r: any) => (
                    <span className={r.is_negative_cost ? 'down' : ''}>{fmt.t(r.marginal_abatement_cost, 0)}</span>) },
                { h: 'Capex', num: true, cell: (r: any) => fmt.money(r.capex) },
                { h: 'Payback yr', num: true, cell: (r: any) => fmt.t(r.payback_years, 1) },
                { h: 'ROI', num: true, cell: (r: any) => fmt.pct(r.roi_pct, 0) },
                { h: 'Readiness', cell: (r: any) => <StatusBadge status={r.technology_readiness} /> },
                { h: 'Status', cell: (r: any) => <StatusBadge status={r.status} /> },
              ]} rows={d.curve} />
            </div>
          )}</Data>
        </Card>

        <div className="grid g2">
          <Card title="Technology roadmap" note="FR-3.D.3">
            <Data of={roadmap}>{(d: any) => (
              <>
                <BarChart data={(d.timeline || []).filter((t: any) => t.year <= 2040)}
                          x="year" y="cumulative_abatement_tco2e" color="var(--accent)"
                          format={(v: number) => `${fmt.t(v, 0)} tCO2e`} height={160} />
                {(d.lanes || []).map((lane: any) => (
                  <div key={lane.readiness} style={{ marginTop: 10 }}>
                    <div className="navgroup" style={{ padding: '4px 0' }}>{fmt.label(lane.readiness)}</div>
                    {lane.initiatives.map((i: any) => (
                      <div key={i.id} className="row small" style={{ padding: '2px 0' }}>
                        <span>{i.name}</span>
                        <div className="spacer" />
                        <span className="muted">{i.start_year}–{i.end_year}</span>
                        <span className="badge">{fmt.t(i.annual_abatement_tco2e, 0)} t/yr</span>
                      </div>
                    ))}
                  </div>
                ))}
              </>
            )}</Data>
          </Card>
          <Card title="Progress tracking" note="FR-3.D.3">
            <Data of={progress}>{(d: any) => (
              <>
                <div className="row" style={{ marginBottom: 10 }}>
                  <span className="badge">Delivery {fmt.pct(d.delivery_pct)}</span>
                  <span className="badge ok">{fmt.t(d.realized_annual_abatement_tco2e, 0)} realized</span>
                  <span className="badge info">{fmt.t(d.planned_annual_abatement_tco2e, 0)} planned</span>
                </div>
                <Table cols={[
                  { h: 'Initiative', cell: (r: any) => r.name },
                  { h: 'Status', cell: (r: any) => <StatusBadge status={r.status} /> },
                  { h: 'Planned', num: true, cell: (r: any) => fmt.t(r.planned_tco2e, 0) },
                  { h: 'Realized', num: true, cell: (r: any) => fmt.t(r.realized_tco2e, 0) },
                  { h: 'Progress', cell: (r: any) => <Bar pct={r.progress_pct} color="var(--accent)" /> },
                ]} rows={d.initiatives} />
              </>
            )}</Data>
          </Card>
        </div>
      </div>
    </Page>
  )
}

/* ================== E · Dashboards & carbon finance ===================== */

export function Drilldown() {
  const [dim, setDim] = useState('entity')
  const q = useApi(`/dashboards/drilldown?dimension=${dim}&year=2025`, [dim])
  const geo = useApi('/dashboards/geography?year=2025')
  const trend = useApi('/dashboards/trend?group_by=scope')
  const [lineage, setLineage] = useState<number | null>(null)
  return (
    <Page title="Operational drill-down" req="FR-3.E.2"
          sub="By entity, facility, cost center, product, supplier, project, category, geography, period and data-quality status.">
      <div className="stack">
        <Card title="Dimension" right={
          <div className="row">
            {['entity', 'facility', 'cost_center', 'product', 'supplier', 'project',
              'category', 'geography', 'period', 'data_quality'].map((d) => (
              <span key={d} className={`chip ${dim === d ? 'on' : ''}`} onClick={() => setDim(d)}>
                {fmt.label(d)}</span>))}
          </div>}>
          <Data of={q}>{(d: any) => (
            <>
              <div className="row" style={{ marginBottom: 10 }}>
                <span className="badge info">{fmt.t(d.total_tco2e, 0)} tCO2e</span>
                <span className="badge">{fmt.n(d.record_count)} records</span>
                <span className="badge">{d.items.length} groups</span>
              </div>
              <Table cols={[
                { h: fmt.label(d.dimension), cell: (r: any) => r.key },
                { h: 'tCO2e', num: true, cell: (r: any) => fmt.t(r.tco2e, 1) },
                { h: 'Share', num: true, cell: (r: any) => fmt.pct(r.share_pct) },
                { h: '', cell: (r: any) => <Bar pct={r.share_pct} /> },
                { h: 'Records', num: true, cell: (r: any) => r.record_count },
                { h: 'Avg confidence', num: true, cell: (r: any) => fmt.t(r.average_confidence, 0) },
                { h: 'Estimated', num: true, cell: (r: any) => fmt.pct(r.estimated_share_pct) },
              ]} rows={d.items} />
            </>
          )}</Data>
        </Card>

        <div className="grid g2">
          <Card title="Emissions by geography" note="FR-3.E.2">
            <Data of={geo}>{(d: any) => (
              <>
                <GeoMap points={d.facilities} height={230} />
                <Table cols={[
                  { h: 'Country', cell: (r: any) => r.country },
                  { h: 'tCO2e', num: true, cell: (r: any) => fmt.t(r.tco2e, 0) },
                  { h: 'Share', num: true, cell: (r: any) => fmt.pct(r.share_pct) },
                ]} rows={d.countries.slice(0, 10)} />
              </>
            )}</Data>
          </Card>
          <Card title="Trend by scope" note="FR-3.E.2">
            <Data of={trend}>{(d: any) => (
              <LineChart series={['scope_1', 'scope_2', 'scope_3'].map((s, i) => ({
                name: fmt.label(s),
                color: ['var(--s1)', 'var(--s2)', 'var(--s3)'][i],
                points: d.series.map((p: any) => ({ x: p.year, y: p[s] || 0 })),
              }))} />
            )}</Data>
          </Card>
        </div>
      </div>
      {lineage && <LineageDrawer emissionId={lineage} onClose={() => setLineage(null)} />}
    </Page>
  )
}

export function Finance() {
  const budgets = useApi('/dashboards/carbon-budgets')
  const prices = useApi('/dashboards/internal-pricing')
  const credits = useApi('/dashboards/credits?page_size=30')
  const summary = useApi('/dashboards/credits/summary?organization_id=1')
  const economics = useApi('/dashboards/project-economics')
  const tcfd = useApi('/dashboards/tcfd/financial-impacts')
  const [priceImpact, setPriceImpact] = useState<any>(null)
  return (
    <Page title="Carbon finance" req="FR-3.E.3"
          sub="Carbon budgets, internal pricing, credit/offset registry, retirement evidence, project economics, TCFD financial impacts and investment prioritization."
          actions={<ActionButton label="Model carbon price impact"
                                 run={() => post('/analytics/carbon-price/impact',
                                                 { year: 2025, prices: [0, 50, 90, 150, 250] })}
                                 onDone={setPriceImpact} />}>
      <div className="stack">
        <Data of={summary}>{(s: any) => (
          <div className="grid g4">
            <KPI label="Gross emissions" value={fmt.t(s.gross_emissions_tco2e, 0)} detail="tCO2e before offsets" />
            <KPI label="Credits retired" value={fmt.t(s.retired_tco2e, 0)}
                 detail={`${fmt.pct(s.offset_coverage_pct)} of gross · ${fmt.pct(s.removals_share_pct, 0)} removals`} />
            <KPI label="Credits held" value={fmt.t(s.held_tco2e, 0)} detail={fmt.money(s.held_value)} />
            <KPI label="Retirement evidence"
                 value={s.retirement_evidence_complete ? 'Complete' : 'Incomplete'}
                 detail="every retired credit carries a certificate" />
          </div>
        )}</Data>

        {priceImpact && (
          <Card title="Internal carbon price impact" note="FR-3.D.2"
                right={<button className="btn sm" onClick={() => setPriceImpact(null)}>Close</button>}>
            <Table cols={[
              { h: 'Price €/tCO2e', num: true, cell: (r: any) => fmt.money(r.price_per_tonne) },
              { h: 'Total carbon cost', num: true, cell: (r: any) => fmt.money(r.total_carbon_cost) },
              { h: 'Scope 1', num: true, cell: (r: any) => fmt.money(r.by_scope?.scope_1) },
              { h: 'Scope 2', num: true, cell: (r: any) => fmt.money(r.by_scope?.scope_2) },
              { h: 'Scope 3', num: true, cell: (r: any) => fmt.money(r.by_scope?.scope_3) },
            ]} rows={priceImpact.scenarios} />
          </Card>
        )}

        <div className="grid g2">
          <Card title="Carbon budgets" note="FR-3.E.3">
            <Data of={budgets}>{(rows: any[]) => (
              <Table cols={[
                { h: 'Entity', cell: (r: any) => r.entity_name },
                { h: 'Year', num: true, cell: (r: any) => r.year },
                { h: 'Budget', num: true, cell: (r: any) => fmt.t(r.budget_tco2e, 0) },
                { h: 'Consumed', num: true, cell: (r: any) => fmt.t(r.consumed_tco2e, 0) },
                { h: 'Usage', cell: (r: any) => (
                    <div style={{ minWidth: 100 }}>
                      <Bar pct={r.usage_pct} color={r.usage_pct > 100 ? 'var(--danger)' : 'var(--accent)'} />
                      <span className="small muted">{fmt.pct(r.usage_pct)}</span>
                    </div>) },
                { h: 'Status', cell: (r: any) => <StatusBadge status={r.status} /> },
              ]} rows={rows} />
            )}</Data>
          </Card>
          <Card title="Internal carbon pricing" note="FR-3.E.3">
            <Data of={prices}>{(rows: any[]) => (
              <Table cols={[
                { h: 'Name', cell: (r: any) => r.name },
                { h: 'Type', cell: (r: any) => <StatusBadge status={r.price_type} /> },
                { h: '€/tCO2e', num: true, cell: (r: any) => fmt.money(r.price_per_tonne) },
                { h: 'From', cell: (r: any) => fmt.date(r.effective_from) },
                { h: 'Applies to', cell: (r: any) => fmt.label(r.applies_to) },
                { h: 'Active', cell: (r: any) => r.is_active
                    ? <span className="badge ok">active</span> : <span className="badge">inactive</span> },
              ]} rows={rows} />
            )}</Data>
          </Card>
        </div>

        <Card title="Credit / offset registry" note="FR-3.E.3 — retirement always carries evidence">
          <Data of={credits}>{(d: any) => (
            <Table cols={[
              { h: 'Project', cell: (r: any) => r.project_name },
              { h: 'Registry', cell: (r: any) => r.registry },
              { h: 'Serial', cell: (r: any) => <code className="small">{r.serial_number}</code> },
              { h: 'Vintage', num: true, cell: (r: any) => r.vintage_year },
              { h: 'tCO2e', num: true, cell: (r: any) => fmt.t(r.quantity_tco2e, 0) },
              { h: 'Price', num: true, cell: (r: any) => fmt.money(r.price_per_tonne) },
              { h: 'Value', num: true, cell: (r: any) => fmt.money(r.total_value) },
              { h: 'Type', cell: (r: any) => r.is_removal
                  ? <span className="badge ok">removal</span> : <span className="badge">avoidance</span> },
              { h: 'Status', cell: (r: any) => <StatusBadge status={r.status} /> },
              { h: 'Evidence', cell: (r: any) => r.has_retirement_evidence
                  ? <span className="badge ok">certificate</span>
                  : r.status === 'retired' ? <span className="badge bad">missing</span> : '—' },
              { h: '', cell: (r: any) => r.status === 'held'
                  ? <ActionButton label="Retire"
                      run={() => post(`/dashboards/credits/${r.id}/retire`,
                        { reason: 'Voluntary retirement against residual emissions' })}
                      onDone={() => { credits.reload(); summary.reload() }} />
                  : null },
            ]} rows={d.items} />
          )}</Data>
        </Card>

        <Card title="Project economics & investment prioritization" note="FR-3.E.3">
          <Data of={economics}>{(d: any) => (
            <>
              <div className="row" style={{ marginBottom: 10 }}>
                <span className="badge">Capex required {fmt.money(d.total_capex_required)}</span>
                <span className="badge ok">{d.self_funding_projects} projects fund themselves</span>
                <span className="badge info">at {fmt.money(d.internal_carbon_price)}/tCO2e</span>
              </div>
              <Table cols={[
                { h: 'Rank', num: true, cell: (r: any) => r.investment_rank },
                { h: 'Project', cell: (r: any) => r.name },
                { h: 'tCO2e/yr', num: true, cell: (r: any) => fmt.t(r.annual_abatement_tco2e, 0) },
                { h: 'Lifetime tCO2e', num: true, cell: (r: any) => fmt.t(r.lifetime_abatement_tco2e, 0) },
                { h: 'Net cost', num: true, cell: (r: any) => fmt.money(r.net_lifetime_cost) },
                { h: 'Carbon value', num: true, cell: (r: any) => fmt.money(r.carbon_value_at_internal_price) },
                { h: 'NPV', num: true, cell: (r: any) => (
                    <span className={r.npv_at_internal_price >= 0 ? 'down' : 'up'}>
                      {fmt.money(r.npv_at_internal_price)}</span>) },
                { h: 'Funds itself', cell: (r: any) => r.funds_itself
                    ? <span className="badge ok">yes</span> : <span className="badge warn">needs funding</span> },
              ]} rows={d.projects} />
            </>
          )}</Data>
        </Card>

        <Card title="TCFD financial impacts" note="FR-3.E.3 / FR-4.3">
          <Data of={tcfd}>{(d: any) => (
            <div className="stack">
              <div className="row">
                <span className="badge bad">{d.risk_count - d.opportunity_count} risks</span>
                <span className="badge ok">{d.opportunity_count} opportunities</span>
                <span className="badge">Net exposure {fmt.money(d.net_exposure.low)} – {fmt.money(d.net_exposure.high)}</span>
              </div>
              <div className="grid g2">
                <div>
                  <h3>By horizon</h3>
                  <Table cols={[
                    { h: 'Horizon', cell: (r: any) => fmt.label(r.horizon) },
                    { h: 'Risks', num: true, cell: (r: any) => r.count },
                    { h: 'Low', num: true, cell: (r: any) => fmt.money(r.low) },
                    { h: 'High', num: true, cell: (r: any) => fmt.money(r.high) },
                  ]} rows={d.by_horizon} />
                </div>
                <div>
                  <h3>By risk type</h3>
                  <Table cols={[
                    { h: 'Type', cell: (r: any) => fmt.label(r.risk_type) },
                    { h: 'Count', num: true, cell: (r: any) => r.count },
                    { h: 'High impact', num: true, cell: (r: any) => fmt.money(r.high) },
                  ]} rows={d.by_risk_type} />
                </div>
              </div>
            </div>
          )}</Data>
        </Card>
      </div>
    </Page>
  )
}
