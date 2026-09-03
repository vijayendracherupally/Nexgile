/** A presentable executive demo used only while the hosted API is unavailable. */
export const DEMO_SCORECARD = {
  year: 2025,
  total_emissions: {
    tco2e: 184260,
    yoy_delta_pct: -8.4,
    by_scope: [
      { scope: 'scope_1', tco2e: 21840 },
      { scope: 'scope_2', tco2e: 47620 },
      { scope: 'scope_3', tco2e: 114800 },
    ],
  },
  intensity: { per_million_revenue: 42.6, currency: 'EUR' },
  exposure: { carbon_liability: 15662100, internal_carbon_price: 85 },
  reduction_performance: {
    planned_annual_abatement_tco2e: 19200,
    realized_annual_abatement_tco2e: 12840,
    initiative_count: 14,
    in_delivery: 8,
    completed: 4,
    total_capex: 6850000,
  },
  trajectory: [
    { year: 2022, tco2e: 231400 }, { year: 2023, tco2e: 215900 },
    { year: 2024, tco2e: 201100 }, { year: 2025, tco2e: 184260 },
  ],
  targets: [{
    name: 'Net-zero operational pathway', target_type: 'absolute_reduction',
    sbti_validated: true, sbti_ambition: '1.5°C aligned', base_year: 2022,
    base_value: 231400, target_year: 2030, reduction_pct: 42,
    allowed_this_year_tco2e: 191500, actual_tco2e: 184260,
    variance_tco2e: -7240, on_track: true,
  }],
  peer_benchmarks: [
    { metric: 'Scope 1 + 2 intensity', peer_best: 26.8, peer_median: 48.2, our_value: 36.1, vs_median_pct: -25.1 },
    { metric: 'Scope 3 supplier coverage', peer_best: 91, peer_median: 66, our_value: 74, vs_median_pct: 12.1 },
    { metric: 'Renewable electricity', peer_best: 96, peer_median: 59, our_value: 68, vs_median_pct: 15.3 },
  ],
  risks: {
    count: 7, opportunities: 3, high_impact: 2,
    financial_impact_range: { low: 3400000, high: 12700000 },
    top_risks: [
      { title: 'Grid carbon-price exposure', horizon: 'medium_term', impact_rating: 'high', financial_impact_high: 5200000 },
      { title: 'Supplier energy volatility', horizon: 'short_term', impact_rating: 'medium', financial_impact_high: 3100000 },
      { title: 'Extreme-weather disruption', horizon: 'long_term', impact_rating: 'high', financial_impact_high: 4400000 },
    ],
  },
  data_quality: { record_count: 1286, average_confidence: 82.4, estimated_share_pct: 17.8 },
}

export const DEMO_CHART_DATA = [
  { label: 'Jan', value: 42 },
  { label: 'Feb', value: 48 },
  { label: 'Mar', value: 45 },
  { label: 'Apr', value: 53 },
  { label: 'May', value: 49 },
  { label: 'Jun', value: 57 },
]

export const DEMO_TREND = [
  { x: 2022, y: 231400 },
  { x: 2023, y: 215900 },
  { x: 2024, y: 201100 },
  { x: 2025, y: 184260 },
]

const SAMPLE_ROWS = [
  { id: 1, name: 'Stuttgart Plant', entity_name: 'Meridian Manufacturing GmbH', country: 'DE',
    scope: 'scope_1', status: 'approved', year: 2025, tco2e: 18420, tco2e_tonnes: 18420,
    co2e_tonnes: 18420, value: 18420, share_pct: 10.0, confidence_score: 88,
    data_quality_rating: 'high', description: 'Natural gas combustion and process energy', facilities: [],
    category: 'Stationary combustion', quantity: 285000, unit: 'kWh' },
  { id: 2, name: 'Lyon Assembly', entity_name: 'Meridian Components SAS', country: 'FR',
    scope: 'scope_2', status: 'in_progress', year: 2025, tco2e: 12780, tco2e_tonnes: 12780,
    co2e_tonnes: 12780, value: 12780, share_pct: 6.9, confidence_score: 81,
    data_quality_rating: 'medium', description: 'Purchased electricity', quantity: 196000, unit: 'kWh', facilities: [] },
  { id: 3, name: 'Wroclaw Foundry', entity_name: 'Meridian Polska Sp. z o.o.', country: 'PL',
    scope: 'scope_3', status: 'calculated', year: 2025, tco2e: 9650, tco2e_tonnes: 9650,
    co2e_tonnes: 9650, value: 9650, share_pct: 5.2, confidence_score: 76,
    data_quality_rating: 'medium', description: 'Purchased goods and services', quantity: 142000, unit: 'EUR', facilities: [] },
]

const SAMPLE_LIST = SAMPLE_ROWS.map((row) => ({ ...row }))
const SAMPLE_PAGE = { items: SAMPLE_LIST, page: 1, page_size: 25, total: SAMPLE_LIST.length, pages: 1 }

const SAMPLE_REPORT = {
  total_tco2e: 184260, record_count: 1286, average_confidence_score: 82.4,
  average_factor_confidence: 86.1, completeness_pct: 91.2, estimated_share_pct: 17.8,
  open_anomalies: 3, open_gaps: 4, total: SAMPLE_LIST.length, page: 1, pages: 1,
  items: SAMPLE_LIST, curve: SAMPLE_LIST, initiatives: SAMPLE_LIST,
  countries: SAMPLE_LIST, facilities: SAMPLE_LIST, projects: SAMPLE_LIST,
  by_rating: SAMPLE_LIST, by_data_origin: SAMPLE_LIST, by_horizon: SAMPLE_LIST,
  by_risk_type: SAMPLE_LIST, by_scope: SAMPLE_LIST, matrix: SAMPLE_LIST,
  categories: SAMPLE_LIST, activities: SAMPLE_LIST, responses: SAMPLE_LIST,
  disclosures: SAMPLE_LIST, controls: SAMPLE_LIST, risks: SAMPLE_LIST,
  opportunities: SAMPLE_LIST, series: [
    { year: 2022, scope_1: 28000, scope_2: 56000, scope_3: 147400 },
    { year: 2023, scope_1: 26000, scope_2: 52000, scope_3: 137900 },
    { year: 2024, scope_1: 23800, scope_2: 50000, scope_3: 127300 },
    { year: 2025, scope_1: 21840, scope_2: 47620, scope_3: 114800 },
  ],
  timeline: [2025, 2026, 2027, 2028, 2029, 2030].map((year, index) => ({
    year, cumulative_abatement_tco2e: index * 3200,
  })),
  by_entity: SAMPLE_LIST, by_entity_name: SAMPLE_LIST,
  net_exposure: { low: 3400000, high: 12700000 },
  strategy: { risks: SAMPLE_LIST, opportunities: SAMPLE_LIST, scenarios: SAMPLE_LIST },
  governance: { board_oversight: true, management_role: 'CSO-led climate steering group' },
  risk_management: { controls: SAMPLE_LIST },
  metrics_and_targets: { emissions: 184260, targets: SAMPLE_LIST },
  visibility: { entities: 6, facilities: 7, suppliers: 42 },
}

export function demoResponse(path: string): any {
  const clean = path.split('?')[0].replace(/\/\d+(?=\/|$)/g, '/1')
  if (clean === '/platform/me') {
    return { is_unrestricted: true, role_name: 'Chief Sustainability Officer',
      scope: { entities: [1, 2, 3], facilities: [1, 2, 3], suppliers: [1, 2, 3] } }
  }
  if (clean.includes('/scorecard/executive')) return DEMO_SCORECARD
  if (clean.includes('/entities/tree')) return [{ id: 1, name: 'Meridian Industrial Group', code: 'MIG', country: 'DE',
    ownership_pct: 100, consolidation_method: 'operational_control', is_consolidated: true,
    employees: 7400, facilities: SAMPLE_LIST, children: SAMPLE_LIST }]
  if (clean.includes('/scope1/summary')) return { ...SAMPLE_REPORT, total_tco2e: 21840,
    expected_source_types: ['stationary_combustion', 'mobile_combustion', 'process', 'fugitive'],
    source_types: SAMPLE_LIST, capture_methods: SAMPLE_LIST }
  if (clean.includes('/scope2/summary')) return { ...SAMPLE_REPORT, location_based_tco2e: 47620,
    market_based_tco2e: 39100, renewable_benefit_pct: 18.0, difference_tco2e: 8520,
    by_country: SAMPLE_LIST }
  if (clean.includes('/scope3/summary')) return { ...SAMPLE_REPORT, categories_reported: 15,
    categories_total: 15, coverage_pct: 100, data_methods: ['spend_based', 'supplier_specific'],
    categories: Array.from({ length: 15 }, (_, i) => ({ ...SAMPLE_ROWS[i % 3], number: i + 1,
      name: `Scope 3 category ${i + 1}`, is_reported: true, methods_used: ['activity_based'] })) }
  if (clean.includes('/grid-factors/countries')) return { country_count: 150, countries: SAMPLE_LIST }
  if (clean.includes('/suppliers/languages')) return { count: 25,
    languages: ['English', 'German', 'French', 'Spanish', 'Polish', 'Italian', 'Japanese'] }
  if (clean.includes('/compliance/readiness')) return { frameworks: SAMPLE_LIST }
  if (clean.includes('/double-materiality')) return { ...SAMPLE_REPORT, matrix: SAMPLE_LIST }
  if (clean.includes('/value-chain')) return { upstream_tco2e: 84200, own_operations_tco2e: 69460,
    downstream_tco2e: 30600, supplier_coverage_pct: 74 }
  if (clean.includes('/transition-plan')) return { entity_id: 1, plans: SAMPLE_LIST }
  if (clean.includes('/taxonomy/kpis')) return { kpis: { revenue: 420000000, capex: 6850000, opex: 9200000 },
    activities: SAMPLE_LIST, dnsh_objectives: SAMPLE_LIST }
  if (clean.includes('/sec/disclosure')) return { scope_disclosures: SAMPLE_LIST,
    materiality: SAMPLE_LIST, attestation: { status: 'in_review', provider: 'Northstar Assurance' } }
  if (clean.includes('/cdp/responses')) return { responses: SAMPLE_LIST, response_history: SAMPLE_LIST,
    peer_benchmarks: SAMPLE_LIST, review_workflow: SAMPLE_LIST }
  if (clean.includes('/platform/roles')) return { groups: SAMPLE_LIST,
    permissions: ['accounting.read', 'analytics.read', 'compliance.read'], roles: SAMPLE_LIST }
  if (clean.includes('/platform/users')) return [
    { id: 1, email: 'ana.k@meridian.example', full_name: 'Ana Kowalski', role_name: 'Chief Sustainability Officer', role_group: 'sustainability', language: 'English', grants: [] },
    { id: 2, email: 'iris.d@meridian.example', full_name: 'Iris Delacroix', role_name: 'Finance', role_group: 'business', language: 'French', grants: [] },
    { id: 3, email: 'carlos.m@meridian.example', full_name: 'Carlos Mendes', role_name: 'Supply Chain / Procurement', role_group: 'business', language: 'Spanish', grants: [] },
  ]
  if (clean.includes('/bom')) return { bom: { id: 1, name: 'Drive unit assembly' }, items: SAMPLE_LIST,
    flat: SAMPLE_LIST, levels: 2, total_mass_kg: 184.5 }
  if (clean.includes('/processes') || clean.includes('/routes') || clean.includes('/languages') ||
      clean.includes('/factor-libraries') || clean.includes('/reporting-boundaries') ||
      clean.includes('/baselines') || clean.includes('/materials') || clean.includes('/campaigns/list') ||
      clean.includes('/action-plans/list') || clean.includes('/procurement/decisions') ||
      clean.includes('/cbam/declarations') || clean.includes('/assurance-requests') ||
      clean.includes('/approvals') || clean.includes('/connectors') ||
      clean.includes('/users') || clean.includes('/reports')) return SAMPLE_LIST
  if (clean.includes('/catalog')) return { categories: { ERP: ['SAP S/4HANA', 'Oracle Fusion'],
      Utilities: ['GridWatch', 'EnergyCloud'], Procurement: ['Coupa', 'Ariba'] }, protocols: ['SFTP', 'API', 'CSV'],
    data_formats: ['CSV', 'JSON', 'XLSX'], pcf_exchange_formats: ['PACT', 'TfS'], import_types: SAMPLE_LIST }
  if (clean.includes('/sync-status')) return { connector_count: 4, healthy_count: 3, degraded_count: 1,
    by_status: SAMPLE_LIST, connectors: SAMPLE_LIST }
  if (clean.includes('/access-check')) return { principal: { full_name: 'Ana Kowalski',
      role_name: 'Chief Sustainability Officer', role_group: 'sustainability', is_unrestricted: true,
      permissions: ['accounting.read', 'analytics.read', 'compliance.read'] },
    visibility: { entities: { visible: 6, total: 6, restricted: false },
      facilities: { visible: 7, total: 7, restricted: false },
      suppliers: { visible: 42, total: 48, restricted: true } },
    enforced_by: 'tenant scope and role permissions' }
  if (clean.includes('/bulk/operations')) return { operations: ['export', 'recalculate', 'validate'],
    export_formats: ['CSV', 'JSON', 'XLSX'], note: 'Demo operations are ready.' }
  if (clean.includes('/coverage')) return { 'FR-3.A.1': 'covered', 'FR-3.D.3': 'covered', 'FR-7.4': 'covered' }
  if (clean.includes('/scenario')) return SAMPLE_LIST
  if (clean.includes('/activity-data') || clean.includes('/calculations') || clean.includes('/emission-factors') ||
      clean === '/lca/products' || clean === '/lca/pcf' || clean === '/suppliers' ||
      clean.includes('/data-quality/assessments') || clean.includes('/anomalies') || clean.includes('/credits') ||
      clean.includes('/notifications') || clean.includes('/bulk/jobs') || clean.includes('/imports') ||
      clean.includes('/evidence') || clean.includes('/disclosures')) return SAMPLE_PAGE
  if (clean.includes('/pcf/portfolio/summary')) return { product_count: 12, with_pcf: 9, coverage_pct: 75,
    verified_count: 6, total_annual_tco2e: 84200, products: SAMPLE_LIST }
  if (clean.includes('/pcf/') || clean.includes('/products/') || clean.includes('/suppliers/')) {
    return { ...SAMPLE_REPORT, id: 1, name: 'Meridian Drive Unit', product_name: 'Meridian Drive Unit',
      functional_unit: { name: 'one drive unit', quantity: 1, unit: 'piece' },
      bom: { id: 1, name: 'Drive unit assembly' }, evidence: SAMPLE_LIST,
      assumptions: ['Electricity mix based on facility location'], review: SAMPLE_LIST,
      exchange: { product_id: 'MIG-DRIVE-001', declared_unit: 'piece' },
      ready: true, '1_goal_and_scope': { system_boundary: 'cradle-to-gate', functional_unit: { name: 'one drive unit' } },
      '2_life_cycle_inventory': { stage_breakdown_kgco2e: SAMPLE_LIST },
      '4_interpretation': 'Primary hotspot is purchased aluminium.', '5_verification': SAMPLE_LIST,
      scorecards: SAMPLE_LIST, sub_tier_suppliers: SAMPLE_LIST, action_plans: SAMPLE_LIST, goods: SAMPLE_LIST }
  }
  return SAMPLE_REPORT
}
