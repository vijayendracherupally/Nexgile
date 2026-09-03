import React, { useEffect, useState } from 'react'
import { api, fmt, useApi } from '../lib/api'
import { DEMO_CHART_DATA, DEMO_TREND } from '../lib/demo'

export function Page({ title, sub, req, actions, children }: any) {
  return (
    <>
      <div className="row" style={{ marginBottom: 4 }}>
        <div>
          <h2 className="page-title">
            {title}
            {req && <span className="req">{req}</span>}
          </h2>
          {sub && <p className="page-sub">{sub}</p>}
        </div>
        <div className="spacer" />
        {actions}
      </div>
      {children}
    </>
  )
}

export function Loading() {
  return <div className="muted small" style={{ padding: 20 }}>Loading…</div>
}
export function ErrorBox({ error }: { error: string }) {
  return <div className="err">{error}</div>
}

/** Renders API state uniformly so no page has to repeat it. */
export function Data({ of, children }: { of: any; children: (d: any) => React.ReactNode }) {
  if (of.loading) return <Loading />
  if (of.error) return <ErrorBox error={of.error} />
  if (!of.data) return <div className="demo-empty">Representative demo data is unavailable for this view.</div>
  return <>{children(of.data)}</>
}

export function KPI({ label, value, detail, tone }: any) {
  return (
    <div className="card kpi">
      <div className="l">{label}</div>
      <div className="v">{value}</div>
      {detail && <div className={`d ${tone || ''}`}>{detail}</div>}
    </div>
  )
}

export function Card({ title, note, right, children }: any) {
  return (
    <div className="card">
      {(title || right) && (
        <div className="row">
          <h3>{title}{note && <small>{note}</small>}</h3>
          <div className="spacer" />
          {right}
        </div>
      )}
      {children}
    </div>
  )
}

export function Table({ cols, rows, empty = 'Nothing to show.' }: any) {
  if (!rows || rows.length === 0) return <div className="muted small">{empty}</div>
  return (
    <div className="tablewrap">
      <table>
        <thead>
          <tr>{cols.map((c: any, i: number) => (
            <th key={i} className={c.num ? 'num' : ''}>{c.h}</th>
          ))}</tr>
        </thead>
        <tbody>
          {rows.map((r: any, i: number) => (
            <tr key={i}>
              {cols.map((c: any, j: number) => (
                <td key={j} className={c.num ? 'num' : ''}>{c.cell(r, i)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** FR-7.4 — every value shows its data-quality state. */
export function DQBadge({ rating, confidence, estimated }: any) {
  if (!rating && confidence == null) return <span className="muted">—</span>
  const cls = (rating || '').toLowerCase()
  return (
    <span
      className={`badge ${cls}`}
      title={`Data quality ${rating || '?'} · confidence ${confidence ?? '?'}` +
        (estimated ? ' · estimated value' : ' · measured/primary')}
    >
      {rating || '?'}{confidence != null ? ` ${Math.round(confidence)}` : ''}
      {estimated ? ' ~' : ''}
    </span>
  )
}

export function StatusBadge({ status }: { status: string }) {
  const s = (status || '').toLowerCase()
  const cls = /approved|locked|verified|certified|completed|healthy|attested|filed|assured|on_track/.test(s)
    ? 'ok'
    : /draft|calculated|not_started|proposed|pending|requested|in_progress|in_review|queued|held/.test(s)
      ? 'info'
      : /superseded|restated|degraded|at_risk|warning|estimated/.test(s)
        ? 'warn'
        : /failed|rejected|exceeded|missing|overdue/.test(s)
          ? 'bad'
          : ''
  return <span className={`badge ${cls}`}>{fmt.label(status)}</span>
}

export function Bar({ pct, color }: { pct: number; color?: string }) {
  return (
    <div className="bar" title={`${(pct || 0).toFixed(1)}%`}>
      <i style={{ width: `${Math.max(0, Math.min(100, pct || 0))}%`, background: color }} />
    </div>
  )
}

/** FR-7.2 — click any number, see its whole origin. */
export function LineageDrawer({ calculationId, emissionId, onClose }: any) {
  const path = calculationId
    ? `/accounting/calculations/${calculationId}/lineage`
    : `/accounting/emissions/${emissionId}/lineage`
  const q = useApi(path)
  return (
    <>
      <div className="overlay" onClick={onClose} />
      <div className="drawer">
        <div className="row">
          <h2 className="page-title" style={{ fontSize: 17 }}>
            Audit lineage<span className="req">FR-7.2</span>
          </h2>
          <div className="spacer" />
          <button className="btn sm" onClick={onClose}>Close</button>
        </div>
        <p className="page-sub">
          Every reported value traces to its source activity, factor, method, unit
          conversion, allocation, assumptions, approvals and timestamped changes.
        </p>
        <Data of={q}>{(d: any) => <LineageBody d={d} />}</Data>
      </div>
    </>
  )
}

function Section({ title, children }: any) {
  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <h3>{title}</h3>
      {children}
    </div>
  )
}
function KV({ k, v }: any) {
  return (
    <div className="row" style={{ borderBottom: '1px solid var(--line)', padding: '4px 0' }}>
      <span className="muted small" style={{ width: 190, flexShrink: 0 }}>{k}</span>
      <span className="small" style={{ wordBreak: 'break-word' }}>{v ?? '—'}</span>
    </div>
  )
}

function LineageBody({ d }: { d: any }) {
  const c = d.calculation || {}
  const a = d.source_activity || {}
  const f = d.emission_factor || {}
  const m = d.method || {}
  const comp = d.completeness || {}
  return (
    <div>
      {d.reported_value && (
        <Section title="Reported value">
          <KV k="Value" v={`${fmt.t(d.reported_value.co2e_kg, 2)} kgCO2e`} />
          <KV k="Scope / year" v={`${fmt.label(d.reported_value.scope)} · ${d.reported_value.year}`} />
          <KV k="Entity" v={d.reported_value.entity} />
          <KV k="Facility" v={d.reported_value.facility} />
          <KV k="Supplier" v={d.reported_value.supplier} />
        </Section>
      )}

      <Section title="Audit-grade check">
        <div className="row" style={{ marginBottom: 8 }}>
          <span className={`badge ${comp.is_audit_grade ? 'ok' : 'bad'}`}>
            {comp.is_audit_grade ? 'Audit grade — complete chain' : 'Incomplete chain'}
          </span>
        </div>
        <div className="row">
          {Object.entries(comp.elements || {}).map(([k, v]: any) => (
            <span key={k} className={`badge ${v ? 'ok' : 'warn'}`}>{fmt.label(k)}</span>
          ))}
        </div>
      </Section>

      <Section title="1 · Source activity">
        <KV k="Activity data ID" v={a.activity_data_id} />
        <KV k="Activity key" v={a.activity_key} />
        <KV k="Description" v={a.description} />
        <KV k="Quantity" v={`${fmt.n(a.quantity, 2)} ${a.unit || ''}`} />
        <KV k="Period" v={`${fmt.date(a.period_start)} → ${fmt.date(a.period_end)}`} />
        <KV k="Data origin" v={fmt.label(a.data_origin)} />
        <KV k="Evidence status" v={fmt.label(a.evidence_status)} />
        <KV k="External reference" v={a.external_ref || '—'} />
      </Section>

      <Section title="2 · Emission factor">
        <KV k="Factor" v={f.name} />
        <KV k="Value" v={`${f.value_kgco2e} kgCO2e / ${f.unit}`} />
        <KV k="Country / region" v={`${f.country || '—'} ${f.region || ''}`} />
        <KV k="Validity" v={`${fmt.date(f.valid_from)} → ${f.valid_to ? fmt.date(f.valid_to) : 'open'}`} />
        <KV k="Library" v={f.library && `${f.library.provider} ${f.library.version}${f.library.is_locked ? ' (locked)' : ''}`} />
        <KV k="Source reference" v={f.source_reference} />
        <KV k="Factor uncertainty" v={fmt.pct(f.uncertainty_pct)} />
        {f.alternatives_considered?.length > 0 && (
          <>
            <div className="muted small" style={{ margin: '10px 0 4px' }}>
              Alternatives considered (why this factor won):
            </div>
            <Table
              cols={[
                { h: 'Factor', cell: (r: any) => r.name },
                { h: 'Country', cell: (r: any) => r.country },
                { h: 'Score', num: true, cell: (r: any) => r.score },
                { h: 'Reason', cell: (r: any) => (r.reasons || []).join('; ') },
              ]}
              rows={f.alternatives_considered}
            />
          </>
        )}
      </Section>

      <Section title="3 · Method">
        <KV k="Method" v={fmt.label(m.method)} />
        <KV k="Method version" v={m.method_version} />
        <KV k="GWP set" v={m.gwp_set} />
        {m.gas_detail && (
          <Table
            cols={[
              { h: 'Gas', cell: (r: any) => r[0] },
              { h: 'Mass (kg)', num: true, cell: (r: any) => fmt.n(r[1].mass_kg, 4) },
              { h: 'GWP', num: true, cell: (r: any) => r[1].gwp },
              { h: 'kgCO2e', num: true, cell: (r: any) => fmt.n(r[1].co2e_kg, 3) },
            ]}
            rows={Object.entries(m.gas_detail)}
          />
        )}
      </Section>

      <Section title="4 · Unit conversion">
        <Table
          cols={[
            { h: 'Step', cell: (r: any) => fmt.label(r.step) },
            { h: 'From', cell: (r: any) => r.from },
            { h: 'To', cell: (r: any) => r.to },
            { h: 'Factor', num: true, cell: (r: any) => r.factor },
          ]}
          rows={d.unit_conversion?.chain || []}
          empty="No conversion required."
        />
      </Section>

      <Section title="5 · Allocation">
        {d.allocation?.applied ? (
          <Table
            cols={[
              { h: 'Target', cell: (r: any) => `${fmt.label(r.target_type)} #${r.target_id}` },
              { h: 'Basis value', num: true, cell: (r: any) => fmt.n(r.basis_value, 2) },
              { h: 'Share', num: true, cell: (r: any) => fmt.pct(r.share * 100, 3) },
              { h: 'kgCO2e', num: true, cell: (r: any) => fmt.n(r.allocated_co2e_kg, 3) },
            ]}
            rows={d.allocation.splits || []}
          />
        ) : (
          <div className="muted small">{d.allocation?.note || 'No allocation applied.'}</div>
        )}
      </Section>

      <Section title="6 · Consolidation">
        <KV k="Method" v={fmt.label(d.consolidation?.method)} />
        <KV k="Ownership share" v={fmt.pct((d.consolidation?.share ?? 0) * 100, 2)} />
        <KV k="Explanation" v={d.consolidation?.explanation} />
      </Section>

      <Section title="7 · Data quality">
        <KV k="Rating" v={<DQBadge rating={d.data_quality?.rating} confidence={d.data_quality?.confidence_score} />} />
        <KV k="Uncertainty" v={fmt.pct(d.data_quality?.uncertainty_pct)} />
        <KV k="Pedigree" v={JSON.stringify(d.data_quality?.pedigree || {})} />
      </Section>

      <Section title="8 · Assumptions">
        {(d.assumptions || []).length === 0
          ? <div className="muted small">No assumptions recorded.</div>
          : <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
              {d.assumptions.map((s: string, i: number) => <li key={i}>{s}</li>)}
            </ul>}
      </Section>

      <Section title="9 · Approvals">
        <Table
          cols={[
            { h: 'Step', cell: (r: any) => fmt.label(r.step) },
            { h: 'Status', cell: (r: any) => <StatusBadge status={r.status} /> },
            { h: 'Decided', cell: (r: any) => fmt.date(r.decided_at) },
            { h: 'Comment', cell: (r: any) => r.comment },
          ]}
          rows={d.approvals || []}
          empty="Not yet submitted for approval."
        />
      </Section>

      <Section title="10 · Timestamped changes">
        <Table
          cols={[
            { h: 'When', cell: (r: any) => String(r.at).replace('T', ' ').slice(0, 19) },
            { h: 'Action', cell: (r: any) => fmt.label(r.action) },
            { h: 'User', cell: (r: any) => r.user || 'system' },
            { h: 'Reason', cell: (r: any) => r.reason },
          ]}
          rows={d.timestamped_changes || []}
        />
      </Section>

      <Section title="Calculation record">
        <KV k="Formula" v={<code className="small">{c.formula}</code>} />
        <KV k="Version" v={c.version} />
        <KV k="Status" v={<StatusBadge status={c.status} />} />
        <KV k="Scenario" v={c.scenario_id ? `Sandbox #${c.scenario_id}` : 'Approved actuals'} />
      </Section>
    </div>
  )
}

/** Lightweight inline SVG charts — no external chart dependency. */
export function BarChart({ data, x, y, color = 'var(--accent-2)', height = 200, format }: any) {
  const chartData = data?.length ? data : DEMO_CHART_DATA.map((d) => ({ [x]: d.label, [y]: d.value }))
  const max = Math.max(...chartData.map((d: any) => Number(d[y]) || 0), 0.0001)
  const w = 100 / chartData.length
  return (
    <div>
      <svg viewBox={`0 0 100 ${height / 3}`} preserveAspectRatio="none"
           style={{ width: '100%', height, display: 'block' }}>
        {chartData.map((d: any, i: number) => {
          const h = ((Number(d[y]) || 0) / max) * (height / 3 - 2)
          return (
            <rect key={i} x={i * w + w * 0.15} y={height / 3 - h}
                  width={w * 0.7} height={Math.max(h, 0.4)} fill={color}>
              <title>{`${d[x]}: ${format ? format(d[y]) : d[y]}`}</title>
            </rect>
          )
        })}
      </svg>
      <div className="row" style={{ fontSize: 10, color: 'var(--muted)', marginTop: 4 }}>
        {chartData.map((d: any, i: number) => (
          <span key={i} style={{ width: `${w}%`, textAlign: 'center', overflow: 'hidden' }}>
            {String(d[x]).slice(0, 10)}
          </span>
        ))}
      </div>
    </div>
  )
}

export function LineChart({ series, height = 220 }: any) {
  const chartSeries = series?.some((s: any) => s.points?.length)
    ? series
    : [{ name: 'Representative trend', color: 'var(--accent-2)', points: DEMO_TREND }]
  const all = chartSeries.flatMap((s: any) => s.points)
  const xs = all.map((p: any) => p.x)
  const ys = all.map((p: any) => p.y)
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  const maxY = Math.max(...ys, 0.0001), minY = Math.min(...ys, 0)
  const px = (x: number) => ((x - minX) / (maxX - minX || 1)) * 96 + 2
  const py = (y: number) => 98 - ((y - minY) / (maxY - minY || 1)) * 94
  return (
    <div>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none"
           style={{ width: '100%', height, display: 'block' }}>
        {[0, 25, 50, 75, 100].map((g) => (
          <line key={g} x1="0" x2="100" y1={g} y2={g} stroke="var(--line)" strokeWidth="0.3" />
        ))}
        {chartSeries.map((s: any, i: number) => (
          <g key={i}>
            <polyline
              points={s.points.map((p: any) => `${px(p.x)},${py(p.y)}`).join(' ')}
              fill="none" stroke={s.color} strokeWidth="0.9"
              strokeDasharray={s.dashed ? '2,1.5' : undefined}
              vectorEffect="non-scaling-stroke"
            />
            {s.points.map((p: any, j: number) => (
              <circle key={j} cx={px(p.x)} cy={py(p.y)} r="0.9" fill={s.color}>
                <title>{`${s.name} ${p.x}: ${p.y}`}</title>
              </circle>
            ))}
          </g>
        ))}
      </svg>
      <div className="row small" style={{ marginTop: 6 }}>
        {chartSeries.map((s: any, i: number) => (
          <span key={i} className="muted">
            <span style={{ display: 'inline-block', width: 10, height: 3,
                           background: s.color, marginRight: 5, verticalAlign: 'middle' }} />
            {s.name}
          </span>
        ))}
        <div className="spacer" />
        <span className="muted">{minX} – {maxX}</span>
      </div>
    </div>
  )
}

export function Donut({ items, size = 150 }: any) {
  const donutItems = items?.length ? items : [
    { label: 'Direct emissions', value: 35, color: 'var(--s1)' },
    { label: 'Purchased energy', value: 25, color: 'var(--s2)' },
    { label: 'Value chain', value: 40, color: 'var(--s3)' },
  ]
  const total = donutItems.reduce((s: number, i: any) => s + (i.value || 0), 0) || 1
  let acc = 0
  const r = 15.9155
  return (
    <div className="row" style={{ gap: 16 }}>
      <svg width={size} height={size} viewBox="0 0 42 42">
        <circle cx="21" cy="21" r={r} fill="none" stroke="var(--panel-2)" strokeWidth="5" />
        {donutItems.map((it: any, i: number) => {
          const pct = ((it.value || 0) / total) * 100
          const el = <circle key={i} cx="21" cy="21" r={r} fill="none" stroke={it.color}
            strokeWidth="5" strokeDasharray={`${pct} ${100 - pct}`}
            strokeDashoffset={25 - acc} transform="rotate(0)">
            <title>{`${it.label}: ${pct.toFixed(1)}%`}</title>
          </circle>
          acc += pct
          return el
        })}
      </svg>
      <div className="stack" style={{ gap: 5 }}>
        {items.map((it: any, i: number) => (
          <div key={i} className="row small">
            <span style={{ width: 9, height: 9, background: it.color, borderRadius: 2 }} />
            <span className="muted">{it.label}</span>
            <b>{fmt.t(it.value)}</b>
            <span className="muted">({(((it.value || 0) / total) * 100).toFixed(1)}%)</span>
          </div>
        ))}
      </div>
    </div>
  )
}

/** World map without tiles — an equirectangular projection of the points. */
export function GeoMap({ points, height = 300 }: any) {
  const valid = (points || []).filter((p: any) => p.latitude || p.longitude)
  const max = Math.max(...valid.map((p: any) => p.tco2e || 0), 1)
  const x = (lon: number) => ((lon + 180) / 360) * 100
  const y = (lat: number) => ((90 - lat) / 180) * 100
  return (
    <svg viewBox="0 0 100 50" style={{ width: '100%', height, background: 'var(--panel-2)',
                                        borderRadius: 6 }}>
      {Array.from({ length: 13 }, (_, i) => (
        <line key={`v${i}`} x1={i * 8.33} x2={i * 8.33} y1="0" y2="50"
              stroke="var(--line)" strokeWidth="0.15" />
      ))}
      {Array.from({ length: 7 }, (_, i) => (
        <line key={`h${i}`} x1="0" x2="100" y1={i * 8.33} y2={i * 8.33}
              stroke="var(--line)" strokeWidth="0.15" />
      ))}
      <line x1="0" x2="100" y1="25" y2="25" stroke="var(--dim)" strokeWidth="0.25" />
      {valid.map((p: any, i: number) => {
        const r = 0.6 + ((p.tco2e || 0) / max) * 2.2
        return (
          <g key={i}>
            <circle cx={x(p.longitude)} cy={y(p.latitude) / 2 + 12.5} r={r}
                    fill="var(--s1)" opacity="0.72" stroke="var(--s1)" strokeWidth="0.15">
              <title>{`${p.name} (${p.country}) — ${fmt.t(p.tco2e)} tCO2e`}</title>
            </circle>
          </g>
        )
      })}
    </svg>
  )
}

export function useToggle(initial = false) {
  const [on, setOn] = useState(initial)
  return [on, () => setOn((v) => !v), setOn] as const
}

export function ActionButton({ label, run, onDone }: any) {
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  return (
    <span className="row" style={{ gap: 6 }}>
      <button className="btn sm primary" disabled={busy} onClick={async () => {
        setBusy(true); setMsg(null)
        try { const r = await run(); onDone?.(r); setMsg('Done') }
        catch (e: any) { setMsg(e.message) }
        setBusy(false)
      }}>{busy ? 'Working…' : label}</button>
      {msg && <span className="small muted">{msg}</span>}
    </span>
  )
}
