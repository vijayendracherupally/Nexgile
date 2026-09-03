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
