import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Overview from './pages/Overview'
import {
  ActivityData, Calculations, Factors, Governance, Organization, ScopePage,
} from './pages/Accounting'
import {
  Campaigns, EcoDesign, PCFPage, Procurement, Products, Scorecards,
  SupplierDirectory, SupplierNetwork,
} from './pages/Modules'
import {
  Anomalies, DataQuality, Drilldown, Finance, Reduction, Scenarios,
} from './pages/Modules2'
import {
  Access, BulkOps, Compliance, Integrations, Notifications,
} from './pages/Modules3'
import './styles.css'

function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/organization" element={<Organization />} />
          <Route path="/accounting/scope/:scope" element={<ScopePage />} />
          <Route path="/accounting/activity" element={<ActivityData />} />
          <Route path="/accounting/calculations" element={<Calculations />} />
          <Route path="/accounting/factors" element={<Factors />} />
          <Route path="/accounting/governance" element={<Governance />} />
          <Route path="/lca/products" element={<Products />} />
          <Route path="/lca/pcf" element={<PCFPage />} />
          <Route path="/lca/eco-design" element={<EcoDesign />} />
          <Route path="/suppliers" element={<SupplierDirectory />} />
          <Route path="/suppliers/campaigns" element={<Campaigns />} />
          <Route path="/suppliers/scorecards" element={<Scorecards />} />
          <Route path="/suppliers/network" element={<SupplierNetwork />} />
          <Route path="/suppliers/procurement" element={<Procurement />} />
          <Route path="/analytics/quality" element={<DataQuality />} />
          <Route path="/analytics/anomalies" element={<Anomalies />} />
          <Route path="/analytics/scenarios" element={<Scenarios />} />
          <Route path="/analytics/reduction" element={<Reduction />} />
          <Route path="/dashboards/drilldown" element={<Drilldown />} />
          <Route path="/finance" element={<Finance />} />
          <Route path="/compliance" element={<Compliance />} />
          <Route path="/integrations" element={<Integrations />} />
          <Route path="/platform/notifications" element={<Notifications />} />
          <Route path="/platform/bulk" element={<BulkOps />} />
          <Route path="/platform/access" element={<Access />} />
          <Route path="*" element={<Overview />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><App /></React.StrictMode>,
)
