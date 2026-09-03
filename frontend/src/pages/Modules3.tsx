import React, { useState } from 'react'
import { api, fmt, post, useApi } from '../lib/api'
import {
  ActionButton, Bar, Card, Data, KPI, Page, StatusBadge, Table,
} from '../components/ui'

/* ================= 4 · Regulatory compliance & disclosure =============== */

export function Compliance() {
  const [tab, setTab] = useState('readiness')
  const TABS = [
    ['readiness', 'Readiness'], ['csrd', 'CSRD / ESRS'], ['cbam', 'CBAM'],
    ['tcfd', 'TCFD'], ['taxonomy', 'EU Taxonomy'], ['sec', 'SEC climate'],
    ['cdp', 'CDP'], ['assurance', 'Assurance & evidence'],
  ]
  return (
    <Page title="Regulatory compliance & disclosure" req="FR-4.1 – FR-4.5"
          sub="CSRD/ESRS, CBAM, TCFD, EU Taxonomy, SEC climate and CDP — each populated from the same audited ledger."
          actions={
            <div className="row">
              {TABS.map(([k, l]) => (
                <span key={k} className={`chip ${tab === k ? 'on' : ''}`} onClick={() => setTab(k)}>{l}</span>
              ))}
            </div>}>
      {tab === 'readiness' && <Readiness />}
      {tab === 'csrd' && <CSRD />}
      {tab === 'cbam' && <CBAM />}
      {tab === 'tcfd' && <TCFD />}
      {tab === 'taxonomy' && <Taxonomy />}
      {tab === 'sec' && <SEC />}
      {tab === 'cdp' && <CDP />}
      {tab === 'assurance' && <Assurance />}
    </Page>
  )
}

function Readiness() {
  const q = useApi('/compliance/readiness?entity_id=1&reporting_year=2025')
  return (
    <Card title="Framework readiness">
      <Data of={q}>{(d: any) => (
        <Table cols={[
          { h: 'Framework', cell: (r: any) => r.framework_name },
          { h: 'Code', cell: (r: any) => <span className="badge info">{r.framework_code}</span> },
          { h: 'Jurisdiction', cell: (r: any) => r.jurisdiction },
          { h: 'Status', cell: (r: any) => <StatusBadge status={r.status} /> },
          { h: 'Completeness', cell: (r: any) => (
              <div style={{ minWidth: 120 }}>
                <Bar pct={r.completeness_pct} color="var(--accent)" />
                <span className="small muted">{fmt.pct(r.completeness_pct)}</span>
              </div>) },
          { h: 'Assurance ready', cell: (r: any) => r.assurance_ready
              ? <span className="badge ok">ready</span> : <span className="badge warn">not ready</span> },
        ]} rows={d.frameworks} />
      )}</Data>
    </Card>
  )
}

function CSRD() {
  const dm = useApi('/compliance/csrd/double-materiality?entity_id=1&reporting_year=2025')
  const vc = useApi('/compliance/csrd/value-chain?entity_id=1&reporting_year=2025')
  const plan = useApi('/compliance/csrd/transition-plan?entity_id=1')
  const disclosures = useApi('/compliance/disclosures?framework_code=CSRD_ESRS')
  const [built, setBuilt] = useState<any>(null)
  const [xbrl, setXbrl] = useState<any>(null)
  return (
    <div className="stack">
      <Card title="Build the ESRS disclosure from the ledger" note="FR-4.1"
            right={<ActionButton label="Build / refresh"
                                 run={() => post('/compliance/csrd/disclosures/build',
                                                 { entity_id: 1, reporting_year: 2025 })}
                                 onDone={(r: any) => { setBuilt(r); disclosures.reload() }} />}>
        {built ? (
          <div className="grid g4">
            <KPI label="Data points" value={built.data_point_count} detail={`${built.data_points_created} created`} />
            <KPI label="Completeness" value={fmt.pct(built.completeness_pct)} detail="populated data points" />
            <KPI label="Assurance ready" value={built.assurance_ready ? 'Yes' : 'No'}
                 detail="≥90% completeness required" />
            <KPI label="Total GHG" value={fmt.t(built.totals.total, 0)} detail="tCO2e (ESRS E1-6-5)" />
          </div>
        ) : <div className="muted small">Build the disclosure to populate ESRS E1 data points from calculated emissions.</div>}
      </Card>

      <Card title="Disclosures" right={
        <Data of={disclosures}>{(d: any) => d.items?.[0] ? (
          <ActionButton label="Generate XBRL"
                        run={() => api(`/compliance/csrd/disclosures/${d.items[0].id}/xbrl`)}
                        onDone={setXbrl} />) : null}</Data>}>
        <Data of={disclosures}>{(d: any) => (
          <Table cols={[
            { h: 'Disclosure', cell: (r: any) => r.title },
            { h: 'Year', num: true, cell: (r: any) => r.reporting_year },
            { h: 'Status', cell: (r: any) => <StatusBadge status={r.status} /> },
            { h: 'Data points', num: true, cell: (r: any) => r.data_point_count },
            { h: 'Verified', num: true, cell: (r: any) => `${r.verified_count} (${fmt.pct(r.verification_pct, 0)})` },
            { h: 'Completeness', num: true, cell: (r: any) => fmt.pct(r.completeness_pct) },
            { h: 'Assurance', cell: (r: any) => r.assurance_ready
                ? <span className="badge ok">ready</span> : <span className="badge warn">not ready</span> },
          ]} rows={d.items} />
        )}</Data>
      </Card>

      {xbrl && (
        <Card title="XBRL mapping & instance document" note="FR-4.1"
              right={<button className="btn sm" onClick={() => setXbrl(null)}>Close</button>}>
          <Table cols={[
            { h: 'Code', cell: (r: any) => r.code },
            { h: 'Label', cell: (r: any) => r.label },
            { h: 'Value', num: true, cell: (r: any) => typeof r.value === 'number' ? fmt.t(r.value, 2) : (r.value || '—') },
            { h: 'Unit', cell: (r: any) => r.unit },
            { h: 'XBRL tag', cell: (r: any) => <code className="small">{r.xbrl_tag}</code> },
            { h: 'Verification', cell: (r: any) => <StatusBadge status={r.verification_status} /> },
          ]} rows={xbrl.mapping} />
          <h3 style={{ marginTop: 12 }}>Instance document ({xbrl.fact_count} facts)</h3>
          <pre>{xbrl.document}</pre>
        </Card>
      )}

      <div className="grid g2">
        <Card title="Double materiality" note="FR-4.1">
          <Data of={dm}>{(d: any) => (
            <Table cols={[
              { h: 'Topic', cell: (r: any) => `${r.topic_code} · ${r.topic}` },
              { h: 'Impact', num: true, cell: (r: any) => fmt.t(r.impact_score, 1) },
              { h: 'Financial', num: true, cell: (r: any) => fmt.t(r.financial_score, 1) },
              { h: 'Quadrant', cell: (r: any) => <StatusBadge status={r.quadrant} /> },
              { h: 'Value chain', cell: (r: any) => fmt.label(r.value_chain_stage) },
            ]} rows={d.matrix} />
          )}</Data>
        </Card>
        <Card title="Value-chain disclosure" note="FR-4.1">
          <Data of={vc}>{(d: any) => (
            <div className="stack">
              <div className="grid g3">
                <KPI label="Upstream" value={fmt.t(d.upstream_tco2e, 0)} detail="tCO2e" />
                <KPI label="Own operations" value={fmt.t(d.own_operations_tco2e, 0)} detail="tCO2e" />
                <KPI label="Downstream" value={fmt.t(d.downstream_tco2e, 0)} detail="tCO2e" />
              </div>
              <div className="row small muted">
                Primary-data coverage {fmt.pct(d.primary_data_coverage_pct)} —
                {' '}{d.suppliers_engaged}/{d.suppliers_total} suppliers engaged
              </div>
            </div>
          )}</Data>
        </Card>
      </div>

      <Card title="Transition plan" note="FR-4.1">
        <Data of={plan}>{(d: any) => (
          <Table cols={[
            { h: 'Plan', cell: (r: any) => r.name },
            { h: 'Ambition', cell: (r: any) => <StatusBadge status={r.ambition} /> },
            { h: 'Target year', num: true, cell: (r: any) => r.target_year },
            { h: 'Capex aligned', num: true, cell: (r: any) => fmt.pct(r.capex_aligned_pct) },
            { h: 'Milestones', cell: (r: any) => (
                <span className="small muted">
                  {(r.milestones || []).map((m: any) => `${m.year}: ${m.milestone}`).join(' · ')}</span>) },
          ]} rows={d.plans} />
        )}</Data>
      </Card>
    </div>
  )
}

function CBAM() {
  const list = useApi('/compliance/cbam/declarations')
  const [open, setOpen] = useState<number | null>(null)
  const detail = useApi(open ? `/compliance/cbam/declarations/${open}` : null, [open])
  return (
    <div className="stack">
      <Card title="Quarterly declarations" note="FR-4.2">
        <Data of={list}>{(rows: any[]) => (
          <Table cols={[
            { h: 'Year', num: true, cell: (r: any) => r.reporting_year },
            { h: 'Quarter', cell: (r: any) => <span className="link" onClick={() => setOpen(r.id)}>Q{r.quarter}</span> },
            { h: 'Goods lines', num: true, cell: (r: any) => r.goods_count },
            { h: 'Actual data', num: true, cell: (r: any) => fmt.pct(r.actual_data_pct, 0) },
            { h: 'Embedded tCO2e', num: true, cell: (r: any) => fmt.t(r.total_embedded_tco2e, 1) },
            { h: 'Certificates', num: true, cell: (r: any) => fmt.t(r.certificates_required, 1) },
            { h: 'Payment due', num: true, cell: (r: any) => fmt.money(r.payment_due) },
            { h: 'Payment', cell: (r: any) => <StatusBadge status={r.payment_status} /> },
            { h: 'Status', cell: (r: any) => <StatusBadge status={r.status} /> },
            { h: '', cell: (r: any) => (
                <ActionButton label="Recompute"
                  run={() => post('/compliance/cbam/declarations/compute',
                    { entity_id: r.entity_id, reporting_year: r.reporting_year, quarter: r.quarter })}
                  onDone={() => list.reload()} />) },
          ]} rows={rows} />
        )}</Data>
      </Card>

      {open && (
        <Card title="Imported goods & embedded emissions" note="FR-4.2"
              right={<button className="btn sm" onClick={() => setOpen(null)}>Close</button>}>
          <Data of={detail}>{(d: any) => (
            <>
              {(d.adjustments || []).length > 0 && (
                <div className="row" style={{ marginBottom: 10 }}>
                  {d.adjustments.map((a: any, i: number) => (
                    <span key={i} className="badge info">
                      {fmt.label(a.type)}: {fmt.money(a.amount)}</span>))}
                </div>
              )}
              <Table cols={[
                { h: 'CN code', cell: (r: any) => <code className="small">{r.cn_code}</code> },
                { h: 'Category', cell: (r: any) => r.goods_category },
                { h: 'Description', cell: (r: any) => r.description },
                { h: 'Supplier', cell: (r: any) => r.supplier_name },
                { h: 'Origin', cell: (r: any) => r.origin_country },
                { h: 'Tonnes', num: true, cell: (r: any) => fmt.t(r.quantity_tonnes, 1) },
                { h: 'Direct t/t', num: true, cell: (r: any) => fmt.t(r.direct_embedded_tco2e_per_t, 2) },
                { h: 'Indirect t/t', num: true, cell: (r: any) => fmt.t(r.indirect_embedded_tco2e_per_t, 2) },
                { h: 'Total tCO2e', num: true, cell: (r: any) => fmt.t(r.total_embedded_tco2e, 1) },
                { h: 'Basis', cell: (r: any) => (
                    <span className={`badge ${r.data_basis === 'actual' ? 'ok' : 'warn'}`}>
                      {r.data_basis}</span>) },
                { h: 'Supplier request', cell: (r: any) => <StatusBadge status={r.supplier_request_status} /> },
                { h: 'Evidence', cell: (r: any) => r.evidence
                    ? <span className="badge ok">attached</span> : <span className="badge">—</span> },
                { h: '', cell: (r: any) => r.data_basis === 'default'
                    ? <ActionButton label="Request actual data"
                        run={() => post(`/compliance/cbam/goods/${r.id}/request-supplier-data`)}
                        onDone={() => detail.reload()} />
                    : null },
              ]} rows={d.goods} />
            </>
          )}</Data>
        </Card>
      )}
    </div>
  )
}

function TCFD() {
  const q = useApi('/compliance/tcfd/report?entity_id=1&reporting_year=2025')
  return (
    <Data of={q}>{(d: any) => (
      <div className="stack">
        <div className="grid g4">
          <KPI label="Disclosure completeness" value={fmt.pct(d.disclosure_completeness_pct, 0)}
               detail="across the four pillars" />
          <KPI label="Risks" value={d.strategy.risks.length} detail="registered with financial impact" />
          <KPI label="Opportunities" value={d.strategy.opportunities.length} detail="quantified" />
          <KPI label="Controls documented" value={fmt.pct(d.risk_management.controls_documented_pct, 0)}
               detail="of registered risks" />
        </div>
        <Card title="Governance">
          <div className="small">{d.governance.board_oversight}</div>
          <div className="small muted">{d.governance.management_role}</div>
        </Card>
        <Card title="Strategy — risks & opportunities">
          <Table cols={[
            { h: 'Title', cell: (r: any) => r.title },
            { h: 'Type', cell: (r: any) => fmt.label(r.risk_type) },
            { h: 'Horizon', cell: (r: any) => fmt.label(r.horizon) },
            { h: 'Likelihood', cell: (r: any) => fmt.label(r.likelihood) },
            { h: 'Impact', cell: (r: any) => <StatusBadge status={r.impact_rating} /> },
            { h: 'Financial low', num: true, cell: (r: any) => fmt.money(r.financial_impact_low) },
            { h: 'Financial high', num: true, cell: (r: any) => fmt.money(r.financial_impact_high) },
            { h: 'Scenario', cell: (r: any) => r.scenario_ref },
          ]} rows={[...d.strategy.risks, ...d.strategy.opportunities]} />
        </Card>
        <Card title="Climate scenarios">
          <Table cols={[
            { h: 'Scenario', cell: (r: any) => r.name },
            { h: 'Pathway', cell: (r: any) => <span className="badge info">{r.pathway}</span> },
            { h: 'Horizon', num: true, cell: (r: any) => r.horizon_year },
            { h: 'Carbon price', num: true, cell: (r: any) => fmt.money(r.carbon_price_assumption) },
            { h: 'Narrative', cell: (r: any) => <span className="small muted">{r.narrative}</span> },
          ]} rows={d.strategy.scenarios} />
        </Card>
        <div className="grid g2">
          <Card title="Risk management — controls">
            <Table cols={[
              { h: 'Risk', cell: (r: any) => r.risk },
              { h: 'Control', cell: (r: any) => <span className="small muted">{r.control}</span> },
            ]} rows={d.risk_management.controls} />
          </Card>
          <Card title="Metrics & targets">
            <Table cols={[
              { h: 'Metric', cell: (r: any) => fmt.label(r[0]) },
              { h: 'tCO2e', num: true, cell: (r: any) => fmt.t(r[1], 1) },
            ]} rows={Object.entries(d.metrics_and_targets.emissions)} />
            <div className="small muted" style={{ marginTop: 8 }}>
              Internal carbon price: {fmt.money(d.metrics_and_targets.internal_carbon_price)}/tCO2e
            </div>
          </Card>
        </div>
      </div>
    )}</Data>
  )
}

function Taxonomy() {
  const q = useApi('/compliance/taxonomy/kpis?entity_id=1&reporting_year=2025')
  return (
    <Data of={q}>{(d: any) => (
      <div className="stack">
        <div className="grid g3">
          {['revenue', 'capex', 'opex'].map((k) => (
            <Card key={k} title={fmt.label(k)}>
              <div className="stack">
                <div>
                  <div className="row small"><span className="muted">Eligible</span>
                    <div className="spacer" /><b>{fmt.pct(d.kpis[k].eligible_pct)}</b></div>
                  <Bar pct={d.kpis[k].eligible_pct} />
                </div>
                <div>
                  <div className="row small"><span className="muted">Aligned</span>
                    <div className="spacer" /><b>{fmt.pct(d.kpis[k].aligned_pct)}</b></div>
                  <Bar pct={d.kpis[k].aligned_pct} color="var(--accent)" />
                </div>
                <div className="small muted">Total {fmt.money(d.kpis[k].total)}</div>
              </div>
            </Card>
          ))}
        </div>
        <Card title="Activities — eligibility, alignment, technical criteria, DNSH & safeguards"
              note="FR-4.4">
          <Table cols={[
            { h: 'Code', cell: (r: any) => r.activity_code },
            { h: 'Activity', cell: (r: any) => r.activity_name },
            { h: 'Objective', cell: (r: any) => fmt.label(r.objective) },
            { h: 'Eligible', cell: (r: any) => r.is_eligible
                ? <span className="badge ok">yes</span> : <span className="badge">no</span> },
            { h: 'Substantial contribution', cell: (r: any) => r.substantial_contribution_met
                ? <span className="badge ok">met</span> : <span className="badge warn">not met</span> },
            { h: 'DNSH', cell: (r: any) => (
                <span className="row" style={{ gap: 3 }}>
                  {Object.entries(r.dnsh_checks || {}).map(([k, v]: any) => (
                    <span key={k} className={`badge ${v ? 'ok' : 'bad'}`} title={fmt.label(k)}>
                      {k.slice(0, 2)}</span>))}
                </span>) },
            { h: 'Safeguards', cell: (r: any) => r.minimum_safeguards_met
                ? <span className="badge ok">met</span> : <span className="badge bad">not met</span> },
            { h: 'Aligned', cell: (r: any) => r.is_aligned
                ? <span className="badge ok">aligned</span> : <span className="badge warn">eligible only</span> },
            { h: 'Revenue', num: true, cell: (r: any) => fmt.money(r.revenue_amount) },
            { h: 'CapEx', num: true, cell: (r: any) => fmt.money(r.capex_amount) },
            { h: 'OpEx', num: true, cell: (r: any) => fmt.money(r.opex_amount) },
          ]} rows={d.activities} />
        </Card>
      </div>
    )}</Data>
  )
}

function SEC() {
  const q = useApi('/compliance/sec/disclosure?entity_id=1&reporting_year=2025')
  return (
    <Data of={q}>{(d: any) => (
      <div className="stack">
        <div className="grid g4">
          <KPI label="Readiness" value={fmt.pct(d.readiness_pct, 0)} detail="SEC climate disclosure" />
          <KPI label="Scope 1" value={fmt.t(d.scope_disclosures.scope_1_tco2e, 0)} detail="tCO2e" />
          <KPI label="Scope 2 (location)" value={fmt.t(d.scope_disclosures.scope_2_location_tco2e, 0)} detail="tCO2e" />
          <KPI label="Evidence library" value={fmt.n(d.evidence_library_size)} detail="documents" />
        </div>
        <div className="grid g2">
          <Card title="Scope disclosures">
            <Table cols={[
              { h: 'Disclosure', cell: (r: any) => fmt.label(r[0]) },
              { h: 'Value', num: true, cell: (r: any) => typeof r[1] === 'number' ? fmt.t(r[1], 1) : String(r[1]) },
            ]} rows={Object.entries(d.scope_disclosures)} />
          </Card>
          <Card title="Materiality & attestation">
            <div className="row" style={{ marginBottom: 8 }}>
              <span className="badge info">{d.materiality.assessment_count} material topics</span>
              <span className="badge">{d.attestation.highest_level} assurance</span>
              <span className="badge ok">{d.attestation.completed} completed</span>
            </div>
            <div className="row">{d.materiality.material_topics.map((t: string) =>
              <span key={t} className="badge">{t}</span>)}</div>
          </Card>
        </div>
      </div>
    )}</Data>
  )
}

function CDP() {
  const q = useApi('/compliance/cdp/responses?entity_id=1&reporting_year=2025')
  return (
    <Data of={q}>{(d: any) => (
      <div className="stack">
        <div className="grid g4">
          <KPI label="Questions" value={d.question_count} detail={`${d.answered} answered`} />
          <KPI label="Completeness" value={fmt.pct(d.completeness_pct)} detail="of the questionnaire" />
          <KPI label="In review" value={d.review_workflow.in_review}
               detail={`${d.review_workflow.approved} approved · ${d.review_workflow.draft} draft`} />
          <KPI label="Modules" value={d.by_module.length} detail={d.by_module.join(', ')} />
        </div>
        <Card title="Responses, scores & peer benchmarks" note="FR-4.5">
          <Table cols={[
            { h: 'Code', cell: (r: any) => r.question_code },
            { h: 'Module', cell: (r: any) => r.module },
            { h: 'Question', cell: (r: any) => <span className="small">{r.question}</span> },
            { h: 'Answer', cell: (r: any) => (
                <span className="small muted">{r.answer ? r.answer.slice(0, 70) + '…' : '—'}</span>) },
            { h: 'Status', cell: (r: any) => <StatusBadge status={r.status} /> },
            { h: 'Score', cell: (r: any) => <span className="badge ok">{r.score}</span> },
            { h: 'Peer', cell: (r: any) => <span className="badge">{r.peer_benchmark_score}</span> },
          ]} rows={d.responses} />
        </Card>
        <div className="grid g2">
          <Card title="Response history">
            <Table cols={[
              { h: 'Year', num: true, cell: (r: any) => r.year },
              { h: 'Questions', num: true, cell: (r: any) => r.question_count },
            ]} rows={d.response_history} />
          </Card>
          <Card title="Peer benchmarks">
            <Table cols={[
              { h: 'Metric', cell: (r: any) => r.metric },
              { h: 'Best', num: true, cell: (r: any) => fmt.t(r.peer_best) },
              { h: 'Median', num: true, cell: (r: any) => fmt.t(r.peer_median) },
              { h: 'Worst', num: true, cell: (r: any) => fmt.t(r.peer_worst) },
            ]} rows={d.peer_benchmarks} />
          </Card>
        </div>
      </div>
    )}</Data>
  )
}

function Assurance() {
  const list = useApi('/compliance/assurance-requests')
  const evidence = useApi('/compliance/evidence?page_size=30')
  return (
    <div className="stack">
      <Card title="Assurance requests" note="FR-4.1 / FR-4.5">
        <Data of={list}>{(rows: any[]) => (
          <Table cols={[
            { h: 'Assurer', cell: (r: any) => r.assurer },
            { h: 'Level', cell: (r: any) => <StatusBadge status={r.assurance_level} /> },
            { h: 'Scope', cell: (r: any) => <span className="small muted">{r.scope_description}</span> },
            { h: 'Requested', cell: (r: any) => fmt.date(r.requested_at) },
            { h: 'Due', cell: (r: any) => fmt.date(r.due_date) },
            { h: 'Evidence pack', cell: (r: any) => <code className="small">{r.evidence_pack_ref}</code> },
            { h: 'Status', cell: (r: any) => <StatusBadge status={r.status} /> },
          ]} rows={rows} empty="No assurance requests yet." />
        )}</Data>
      </Card>
      <Card title="Evidence library" note="FR-4.5 / FR-7.4">
        <Data of={evidence}>{(d: any) => (
          <Table cols={[
            { h: 'Title', cell: (r: any) => r.title },
            { h: 'Type', cell: (r: any) => <span className="badge">{fmt.label(r.evidence_type)}</span> },
            { h: 'Linked to', cell: (r: any) => `${fmt.label(r.object_type)} #${r.object_id}` },
            { h: 'Status', cell: (r: any) => <StatusBadge status={r.status} /> },
            { h: 'Extracted fields', cell: (r: any) => (
                <span className="small muted">
                  {Object.keys(r.extracted_fields || {}).join(', ') || '—'}</span>) },
            { h: 'Added', cell: (r: any) => fmt.date(r.created_at) },
          ]} rows={d.items} />
        )}</Data>
      </Card>
    </div>
  )
}

/* ================== 5 · Integrations & data sources ===================== */

export function Integrations() {
  const status = useApi('/integrations/sync-status')
  const catalog = useApi('/integrations/catalog')
  const connectors = useApi('/integrations/connectors')
  const imports = useApi('/integrations/imports')
  const versions = useApi('/integrations/factor-libraries/versions')
  const [logs, setLogs] = useState<any>(null)
  const [importResult, setImportResult] = useState<any>(null)
  return (
    <Page title="Integrations & data sources" req="FR-5.1 – FR-5.5"
          sub="Enterprise systems, operational sources and external data; REST/GraphQL, webhooks, batch/streaming, JSON/XML/CSV, PACT and TfS exchange, schema mapping, import validation and error queues.">
      <div className="stack">
        <Data of={status}>{(d: any) => (
          <div className="grid g4">
            <KPI label="Connectors" value={d.connector_count} detail={`${d.unconfigured} unconfigured`} />
            <KPI label="Average health" value={fmt.t(d.average_health, 1)} detail="0–100 health score" />
            <KPI label="Healthy" value={d.by_status?.healthy || 0} detail="connectors reporting healthy" />
            <KPI label="Degraded" value={d.by_status?.degraded || 0} detail="need attention" />
          </div>
        )}</Data>

        <Data of={catalog}>{(c: any) => (
          <Card title="Connector catalogue" note="FR-5.1 / .2 / .3">
            <div className="grid g3">
              {Object.entries(c.categories).map(([cat, systems]: any) => (
                <div key={cat}>
                  <div className="navgroup" style={{ padding: '2px 0' }}>{fmt.label(cat)}</div>
                  <div className="row">{systems.map((s: string) =>
                    <span key={s} className="badge">{s}</span>)}</div>
                </div>
              ))}
            </div>
            <div className="row" style={{ marginTop: 12 }}>
              <span className="muted small">Protocols:</span>
              {c.protocols.map((p: string) => <span key={p} className="badge info">{p}</span>)}
              <span className="muted small">Formats:</span>
              {c.data_formats.map((p: string) => <span key={p} className="badge">{p}</span>)}
              <span className="muted small">PCF exchange:</span>
              {c.pcf_exchange_formats.map((p: string) => <span key={p} className="badge ok">{p}</span>)}
            </div>
          </Card>
        )}</Data>

        <Card title="Connectors — credentials, mappings, schedules, sync status & health" note="FR-5.5">
          <Data of={connectors}>{(rows: any[]) => (
            <Table cols={[
              { h: 'Connector', cell: (r: any) => r.name },
              { h: 'System', cell: (r: any) => r.system },
              { h: 'Category', cell: (r: any) => <span className="badge">{fmt.label(r.category)}</span> },
              { h: 'Protocol', cell: (r: any) => `${r.protocol}/${r.data_format}` },
              { h: 'Credentials', cell: (r: any) => <StatusBadge status={r.credential_status} /> },
              { h: 'Mappings', num: true, cell: (r: any) => r.mapping_count },
              { h: 'Schedule', cell: (r: any) => <code className="small">{r.schedule_cron}</code> },
              { h: 'Version', cell: (r: any) => r.data_version || '—' },
              { h: 'Health', cell: (r: any) => (
                  <div style={{ minWidth: 80 }}>
                    <Bar pct={r.health_score} color={r.health_score > 95 ? 'var(--accent)' : 'var(--warn)'} />
                    <span className="small muted">{fmt.t(r.health_score, 0)}</span>
                  </div>) },
              { h: 'Last sync', cell: (r: any) => fmt.date(r.last_sync_at) },
              { h: 'Records', num: true, cell: (r: any) => fmt.n(r.records_synced) },
              { h: 'Status', cell: (r: any) => <StatusBadge status={r.status} /> },
              { h: '', cell: (r: any) => (
                  <ActionButton label="Sync now" run={() => post(`/integrations/connectors/${r.id}/sync`)}
                                onDone={(res: any) => { setLogs(res); connectors.reload(); status.reload() }} />) },
            ]} rows={rows} />
          )}</Data>
        </Card>

        {logs && (
          <Card title="Sync transaction log" note="FR-5.5"
                right={<button className="btn sm" onClick={() => setLogs(null)}>Close</button>}>
            <div className="row" style={{ marginBottom: 8 }}>
              <StatusBadge status={logs.status} />
              <span className="badge">read {logs.records_read}</span>
              <span className="badge ok">written {logs.records_written}</span>
              <span className="badge bad">failed {logs.records_failed}</span>
              <span className="badge">reconciliation delta {logs.reconciliation_delta}</span>
            </div>
            <Table cols={[
              { h: 'When', cell: (r: any) => String(r.at).slice(11, 19) },
              { h: 'Step', cell: (r: any) => fmt.label(r.step) },
              { h: 'Level', cell: (r: any) => <StatusBadge status={r.level} /> },
              { h: 'Detail', cell: (r: any) => r.detail },
            ]} rows={logs.log} />
          </Card>
        )}

        <Card title="Imports — validation & error queue" note="FR-5.4 / FR-7.7"
              right={<ActionButton label="Run a validating import (dry run)"
                run={() => post('/integrations/imports', {
                  organization_id: 1, import_type: 'supplier', format: 'csv', dry_run: true,
                  filename: 'suppliers-demo.csv',
                  payload: 'organization_id,name,code,tier,category,country,annual_spend\n' +
                    '1,Demo Supplier A,SUP-900,1,Metals,DE,1200000\n' +
                    '1,,SUP-901,1,Metals,FR,900000\n' +
                    '1,Demo Supplier C,SUP-902,notanumber,Polymers,PL,450000\n',
                })} onDone={(r: any) => { setImportResult(r); imports.reload() }} />}>
          {importResult && (
            <div className="row" style={{ marginBottom: 10 }}>
              <StatusBadge status={importResult.status} />
              <span className="badge">{importResult.rows_total} rows</span>
              <span className="badge ok">{importResult.rows_valid} valid</span>
              <span className="badge bad">{importResult.rows_invalid} invalid</span>
              <span className="badge warn">error queue: {importResult.error_queue_size}</span>
            </div>
          )}
          {importResult?.errors?.length > 0 && (
            <Table cols={[
              { h: 'Row', num: true, cell: (r: any) => r.row },
              { h: 'Messages', cell: (r: any) => (r.messages || []).join('; ') },
            ]} rows={importResult.errors} />
          )}
          <Data of={imports}>{(d: any) => (
            <Table cols={[
              { h: 'Type', cell: (r: any) => fmt.label(r.import_type) },
              { h: 'File', cell: (r: any) => r.filename },
              { h: 'Format', cell: (r: any) => r.format },
              { h: 'Rows', num: true, cell: (r: any) => r.rows_total },
              { h: 'Valid', num: true, cell: (r: any) => r.rows_valid },
              { h: 'Invalid', num: true, cell: (r: any) => r.rows_invalid },
              { h: 'Imported', num: true, cell: (r: any) => r.rows_imported },
              { h: 'Status', cell: (r: any) => <StatusBadge status={r.status} /> },
            ]} rows={d.items} empty="No imports yet." />
          )}</Data>
        </Card>

        <Card title="Factor / data versions" note="FR-5.5">
          <Data of={versions}>{(rows: any[]) => (
            <Table cols={[
              { h: 'Library', cell: (r: any) => r.name },
              { h: 'Provider', cell: (r: any) => r.provider },
              { h: 'Version', cell: (r: any) => r.version },
              { h: 'Factors', num: true, cell: (r: any) => fmt.n(r.factor_count) },
              { h: 'Locked', cell: (r: any) => r.is_locked
                  ? <span className="badge ok">locked</span> : <span className="badge">open</span> },
              { h: 'Fed by', cell: (r: any) => (r.fed_by || []).join(', ') || '—' },
            ]} rows={rows} />
          )}</Data>
        </Card>
      </div>
    </Page>
  )
}

/* ========================== 7 · Platform =============================== */

export function Notifications() {
  const list = useApi('/platform/notifications?page_size=50')
  const approvals = useApi('/platform/approvals')
  return (
    <Page title="Notifications & approvals" req="FR-7.6"
          sub="Missing data, supplier deadlines, validation failures, target deviations, factor updates, approvals, assurance requests and regulatory updates."
          actions={<ActionButton label="Scan all triggers"
                                 run={() => post('/platform/notifications/scan', { organization_id: 1 })}
                                 onDone={() => list.reload()} />}>
      <div className="stack">
        <Card title="Notification centre">
          <Data of={list}>{(d: any) => (
            <Table cols={[
              { h: 'Trigger', cell: (r: any) => <span className="badge info">{fmt.label(r.trigger)}</span> },
              { h: 'Severity', cell: (r: any) => <StatusBadge status={r.severity} /> },
              { h: 'Title', cell: (r: any) => r.title },
              { h: 'Detail', cell: (r: any) => <span className="small muted">{r.body}</span> },
              { h: 'Due', cell: (r: any) => fmt.date(r.due_at) },
              { h: 'Read', cell: (r: any) => r.is_read
                  ? <span className="badge">read</span>
                  : <ActionButton label="Mark read"
                      run={() => post(`/platform/notifications/${r.id}/read`)}
                      onDone={() => list.reload()} /> },
            ]} rows={d.items} empty="No notifications — run a trigger scan." />
          )}</Data>
        </Card>
        <Card title="Approval queue" note="FR-7.3 / FR-7.6">
          <Data of={approvals}>{(rows: any[]) => (
            <Table cols={[
              { h: 'Object', cell: (r: any) => `${fmt.label(r.object_type)} #${r.object_id}` },
              { h: 'Step', cell: (r: any) => fmt.label(r.step) },
              { h: 'Status', cell: (r: any) => <StatusBadge status={r.status} /> },
              { h: 'Decided', cell: (r: any) => fmt.date(r.decided_at) },
              { h: 'Comment', cell: (r: any) => r.comment },
            ]} rows={rows} empty="No approval requests outstanding." />
          )}</Data>
        </Card>
      </div>
    </Page>
  )
}

export function BulkOps() {
  const ops = useApi('/platform/bulk/operations')
  const jobs = useApi('/platform/bulk/jobs')
  const reports = useApi('/platform/reports')
  const [result, setResult] = useState<any>(null)
  return (
    <Page title="Bulk operations & exports" req="FR-7.7"
          sub="Activity/factor imports, supplier campaigns, calculation batches, evidence packs, PCF exchange, disclosure tables and scheduled reports.">
      <div className="stack">
        <Data of={ops}>{(o: any) => (
          <Card title="Run a bulk operation">
            <div className="row">
              {o.operations.map((op: string) => (
                <ActionButton key={op} label={fmt.label(op)}
                  run={() => post('/platform/bulk/jobs',
                                  { organization_id: 1, job_type: op,
                                    params: op === 'evidence_pack' ? { entity_id: 2, year: 2025 }
                                          : op === 'pcf_exchange' ? { format: 'pact' }
                                          : op === 'supplier_campaign' ? { campaign_id: 1 }
                                          : op === 'disclosure_table' ? { disclosure_id: 1 }
                                          : {} })}
                  onDone={(r: any) => { setResult(r); jobs.reload() }} />
              ))}
            </div>
          </Card>
        )}</Data>

        {result && (
          <Card title={`Job result — ${fmt.label(result.job_type)}`}
                right={<button className="btn sm" onClick={() => setResult(null)}>Close</button>}>
            <div className="row" style={{ marginBottom: 8 }}>
              <StatusBadge status={result.status} />
              {result.error && <span className="badge bad">{result.error}</span>}
            </div>
            <pre>{JSON.stringify(result.result, null, 2).slice(0, 6000)}</pre>
          </Card>
        )}

        <Card title="Job history">
          <Data of={jobs}>{(d: any) => (
            <Table cols={[
              { h: 'ID', num: true, cell: (r: any) => r.id },
              { h: 'Type', cell: (r: any) => fmt.label(r.job_type) },
              { h: 'Label', cell: (r: any) => r.label },
              { h: 'Status', cell: (r: any) => <StatusBadge status={r.status} /> },
              { h: 'Progress', cell: (r: any) => <Bar pct={r.progress_pct} color="var(--accent)" /> },
              { h: 'Started', cell: (r: any) => fmt.date(r.started_at) },
              { h: 'Error', cell: (r: any) => <span className="small muted">{r.error}</span> },
            ]} rows={d.items} empty="No jobs run yet." />
          )}</Data>
        </Card>

        <Card title="Exports" note="FR-7.7 — scoped by your permissions (FR-7.1)">
          <div className="row">
            {['emissions', 'activity_data', 'calculations', 'suppliers', 'products',
              'emission_factors', 'credits', 'evidence', 'reduction_initiatives'].map((ds) => (
              <a key={ds} className="btn sm" href={`/api/platform/exports/${ds}?format=csv`}
                 target="_blank" rel="noreferrer">{fmt.label(ds)} CSV</a>
            ))}
          </div>
        </Card>

        <Card title="Scheduled reports" note="FR-7.7">
          <Data of={reports}>{(rows: any[]) => (
            <Table cols={[
              { h: 'Report', cell: (r: any) => r.name },
              { h: 'Type', cell: (r: any) => fmt.label(r.report_type) },
              { h: 'Year', num: true, cell: (r: any) => r.reporting_year },
              { h: 'Scheduled', cell: (r: any) => r.is_scheduled
                  ? <span className="badge ok">{r.schedule_cron}</span> : <span className="badge">ad hoc</span> },
              { h: 'Last generated', cell: (r: any) => fmt.date(r.last_generated_at) },
              { h: 'Status', cell: (r: any) => <StatusBadge status={r.status} /> },
            ]} rows={rows} empty="No reports defined yet." />
          )}</Data>
        </Card>
      </div>
    </Page>
  )
}

export function Access() {
  const check = useApi('/platform/access-check')
  const roles = useApi('/platform/roles')
  const users = useApi('/platform/users')
  const coverage = useApi('/requirements/coverage')
  return (
    <Page title="Access, roles & requirement coverage" req="FR-7.1 / FR-2"
          sub="Users see only permitted organizations, facilities, suppliers, products, calculations, evidence and reports — enforced at the repository layer.">
      <div className="stack">
        <Card title="What the current principal can see">
          <Data of={check}>{(d: any) => (
            <>
              <div className="row" style={{ marginBottom: 10 }}>
                <b>{d.principal.full_name}</b>
                <span className="badge info">{d.principal.role_name}</span>
                <span className="badge">{fmt.label(d.principal.role_group)}</span>
                {d.principal.is_unrestricted && <span className="badge ok">unrestricted</span>}
              </div>
              <Table cols={[
                { h: 'Object family', cell: (r: any) => fmt.label(r[0]) },
                { h: 'Visible', num: true, cell: (r: any) => fmt.n(r[1].visible) },
                { h: 'Total', num: true, cell: (r: any) => fmt.n(r[1].total) },
                { h: '', cell: (r: any) => <Bar pct={r[1].total ? r[1].visible / r[1].total * 100 : 0} /> },
                { h: 'Restricted', cell: (r: any) => r[1].restricted
                    ? <span className="badge warn">restricted</span> : <span className="badge ok">full</span> },
              ]} rows={Object.entries(d.visibility)} />
              <p className="small muted" style={{ marginTop: 8 }}>Enforced by {d.enforced_by}</p>
              <div className="row" style={{ marginTop: 8 }}>
                {d.principal.permissions.map((p: string) => <span key={p} className="badge">{p}</span>)}
              </div>
            </>
          )}</Data>
        </Card>

        <Card title="Roles & role-based views" note="FR-2.1 / .2 / .3">
          <Data of={roles}>{(d: any) => (
            <Table cols={[
              { h: 'Role', cell: (r: any) => r.name },
              { h: 'Group', cell: (r: any) => <span className="badge">{fmt.label(r.group)}</span> },
              { h: 'Landing view', cell: (r: any) => <code className="small">{r.landing_route}</code> },
              { h: 'Permissions', cell: (r: any) => (
                  <span className="small muted">
                    {(r.permissions || []).includes('*') ? 'all permissions'
                      : (r.permissions || []).join(', ')}</span>) },
            ]} rows={d.roles} />
          )}</Data>
        </Card>

        <Card title="Users">
          <Data of={users}>{(rows: any[]) => (
            <Table cols={[
              { h: 'Name', cell: (r: any) => r.full_name },
              { h: 'Email', cell: (r: any) => <code className="small">{r.email}</code> },
              { h: 'Role', cell: (r: any) => r.role_name },
              { h: 'Group', cell: (r: any) => <span className="badge">{fmt.label(r.role_group)}</span> },
              { h: 'Language', cell: (r: any) => r.language },
              { h: 'Grants', cell: (r: any) => (
                  <span className="small muted">
                    {(r.grants || []).map((g: any) => `${g.object_type}#${g.object_id}`).join(', ')}</span>) },
            ]} rows={rows} />
          )}</Data>
        </Card>

        <Card title="Requirement coverage map" note="every FR traced to its implementation">
          <Data of={coverage}>{(d: any) => (
            <Table cols={[
              { h: 'Requirement', cell: (r: any) => <b>{r[0]}</b> },
              { h: 'Implemented by', cell: (r: any) => <code className="small">{r[1]}</code> },
            ]} rows={Object.entries(d)} />
          )}</Data>
        </Card>
      </div>
    </Page>
  )
}
