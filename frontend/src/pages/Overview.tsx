import React from 'react'
import { fmt, useApi } from '../lib/api'
import { DEMO_SCORECARD } from '../lib/demo'
import { Card, Data, Donut, KPI, LineChart, Page, Table, Bar, StatusBadge } from '../components/ui'

export default function Overview() {
  const q = useApi('/dashboards/scorecard/executive?year=2025')
  const isDemo = !q.loading && !q.data
  const display = isDemo ? { ...q, data: DEMO_SCORECARD, error: null } : q
  return (
    <Page title="Executive scorecard" req="FR-3.E.1"
          sub="Total emissions, intensity, targets, trajectories, peer benchmarks, exposure, risks and reduction performance.">
      {isDemo && (
        <div className="demo-banner">
          <span className="demo-pulse" />
          <span><b>Interactive demo data</b> · Showing a representative executive scorecard while the live API wakes up.</span>
        </div>
      )}
      <Data of={display}>{(d: any) => {
        const t = d.total_emissions
        const scopeColors: any = { scope_1: 'var(--s1)', scope_2: 'var(--s2)', scope_3: 'var(--s3)' }
        return (
          <div className="stack">
            <div className="grid g4">
              <KPI label="Total emissions" value={`${fmt.t(t.tco2e, 0)}`}
                   detail={`tCO2e · ${t.yoy_delta_pct >= 0 ? '+' : ''}${fmt.t(t.yoy_delta_pct)}% vs ${d.year - 1}`}
                   tone={t.yoy_delta_pct >= 0 ? 'up' : 'down'} />
              <KPI label="Intensity" value={fmt.t(d.intensity.per_million_revenue, 1)}
                   detail={`tCO2e per ${d.intensity.currency}m revenue`} />
              <KPI label="Carbon liability" value={fmt.money(d.exposure.carbon_liability)}
                   detail={`at ${d.exposure.internal_carbon_price}/tCO2e internal price`} />
              <KPI label="Planned abatement"
                   value={fmt.t(d.reduction_performance.planned_annual_abatement_tco2e, 0)}
                   detail={`tCO2e/yr across ${d.reduction_performance.initiative_count} initiatives`} />
            </div>

            <div className="grid g2">
              <Card title="Emissions by scope" note="FR-3.A.1/.2/.3">
                <Donut items={t.by_scope.map((s: any) => ({
                  label: fmt.label(s.scope), value: s.tco2e, color: scopeColors[s.scope],
                }))} />
              </Card>

              <Card title="Trajectory vs targets" note="FR-3.E.1">
                <LineChart series={[
                  { name: 'Actual', color: 'var(--accent-2)',
                    points: d.trajectory.map((p: any) => ({ x: p.year, y: p.tco2e })) },
                  ...(d.targets[0]?.computed_trajectory ? [] : []),
                ]} />
              </Card>
            </div>

            <Card title="Targets" note="FR-3.E.1">
              <Table
                cols={[
                  { h: 'Target', cell: (r: any) => r.name },
                  { h: 'Type', cell: (r: any) => <StatusBadge status={r.target_type} /> },
                  { h: 'SBTi', cell: (r: any) => r.sbti_validated
                      ? <span className="badge ok">{r.sbti_ambition}</span>
                      : <span className="badge">not validated</span> },
                  { h: 'Base', num: true, cell: (r: any) => `${r.base_year}: ${fmt.t(r.base_value, 0)}` },
                  { h: 'Goal', num: true, cell: (r: any) => `${r.target_year}: −${fmt.t(r.reduction_pct, 0)}%` },
                  { h: 'Allowed now', num: true, cell: (r: any) => fmt.t(r.allowed_this_year_tco2e, 0) },
                  { h: 'Actual', num: true, cell: (r: any) => fmt.t(r.actual_tco2e, 0) },
                  { h: 'Status', cell: (r: any) => (
                      <span className={`badge ${r.on_track ? 'ok' : 'bad'}`}>
                        {r.on_track ? 'On track' : `Over by ${fmt.t(r.variance_tco2e, 0)}`}
                      </span>) },
                ]}
                rows={d.targets}
              />
            </Card>

            <div className="grid g2">
              <Card title="Peer benchmarks" note="FR-3.E.1">
                <Table
                  cols={[
                    { h: 'Metric', cell: (r: any) => r.metric },
                    { h: 'Peer best', num: true, cell: (r: any) => fmt.t(r.peer_best) },
                    { h: 'Median', num: true, cell: (r: any) => fmt.t(r.peer_median) },
                    { h: 'Us', num: true, cell: (r: any) => fmt.t(r.our_value) },
                    { h: 'vs median', num: true, cell: (r: any) =>
                        r.vs_median_pct == null ? '—' :
                        <span className={r.vs_median_pct > 0 ? 'up' : 'down'}>
                          {r.vs_median_pct > 0 ? '+' : ''}{fmt.t(r.vs_median_pct)}%
                        </span> },
                  ]}
                  rows={d.peer_benchmarks}
                />
              </Card>

              <Card title="Climate risks & opportunities" note="FR-3.E.1 / FR-4.3">
                <div className="row" style={{ marginBottom: 10 }}>
                  <span className="badge bad">{d.risks.count - d.risks.opportunities} risks</span>
                  <span className="badge ok">{d.risks.opportunities} opportunities</span>
                  <span className="badge warn">{d.risks.high_impact} high impact</span>
                  <div className="spacer" />
                  <span className="small muted">
                    Exposure {fmt.money(d.risks.financial_impact_range.low)} –
                    {' '}{fmt.money(d.risks.financial_impact_range.high)}
                  </span>
                </div>
                <Table
                  cols={[
                    { h: 'Risk', cell: (r: any) => r.title },
                    { h: 'Horizon', cell: (r: any) => fmt.label(r.horizon) },
                    { h: 'Impact', cell: (r: any) => <StatusBadge status={r.impact_rating} /> },
                    { h: 'Max financial', num: true, cell: (r: any) => fmt.money(r.financial_impact_high) },
                  ]}
                  rows={d.risks.top_risks}
                />
              </Card>
            </div>

            <div className="grid g2">
              <Card title="Reduction performance" note="FR-3.D.3">
                <div className="stack">
                  <div>
                    <div className="row small">
                      <span className="muted">Realized vs planned abatement</span>
                      <div className="spacer" />
                      <b>{fmt.t(d.reduction_performance.realized_annual_abatement_tco2e, 0)} /
                        {' '}{fmt.t(d.reduction_performance.planned_annual_abatement_tco2e, 0)} tCO2e</b>
                    </div>
                    <Bar pct={d.reduction_performance.planned_annual_abatement_tco2e
                      ? d.reduction_performance.realized_annual_abatement_tco2e /
                        d.reduction_performance.planned_annual_abatement_tco2e * 100 : 0}
                         color="var(--accent)" />
                  </div>
                  <div className="row small">
                    <span className="badge info">{d.reduction_performance.in_delivery} in delivery</span>
                    <span className="badge ok">{d.reduction_performance.completed} completed</span>
                    <span className="badge">Capex {fmt.money(d.reduction_performance.total_capex)}</span>
                  </div>
                </div>
              </Card>

              <Card title="Data quality of this scorecard" note="FR-7.4">
                <div className="stack">
                  <div className="row"><span className="muted small">Records</span>
                    <div className="spacer" /><b>{fmt.n(d.data_quality.record_count)}</b></div>
                  <div>
                    <div className="row small"><span className="muted">Average confidence</span>
                      <div className="spacer" /><b>{fmt.t(d.data_quality.average_confidence)}/100</b></div>
                    <Bar pct={d.data_quality.average_confidence} color="var(--accent)" />
                  </div>
                  <div>
                    <div className="row small"><span className="muted">Estimated share</span>
                      <div className="spacer" /><b>{fmt.pct(d.data_quality.estimated_share_pct)}</b></div>
                    <Bar pct={d.data_quality.estimated_share_pct} color="var(--warn)" />
                  </div>
                </div>
              </Card>
            </div>
          </div>
        )
      }}</Data>
    </Page>
  )
}
