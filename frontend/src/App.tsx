import { NavLink, Route, Routes } from 'react-router-dom'
import SimulationPage from './pages/SimulationPage'
import ProductsPage from './pages/ProductsPage'
import HistoryPage from './pages/HistoryPage'
import OpportunitiesPage from './pages/OpportunitiesPage'
import OverstockPage from './pages/OverstockPage'
import ComparisonPage from './pages/ComparisonPage'
import TimingPage from './pages/TimingPage'
import InsightsBanner from './components/InsightsBanner'
import ThemeToggle from './components/ThemeToggle'

export default function App() {
  return (
    <div className="app">
      <header className="nav">
        <div className="brand">
          惣菜の値引きシステム
          <span className="brand-sub">見切り品の値引きを売れ行きで決めるシミュレーター</span>
        </div>
        <nav className="nav-main">
          <NavLink to="/" end>
            売り場
          </NavLink>
          <NavLink to="/products">商品</NavLink>
          <NavLink to="/history">履歴</NavLink>
        </nav>
        <nav className="nav-analysis" aria-label="振り返り">
          <span className="nav-label">振り返り</span>
          <NavLink to="/compare">固定時刻との比較</NavLink>
          <NavLink to="/timing">値引きの時間帯</NavLink>
          <NavLink to="/opportunities">早く売り切れた商品</NavLink>
          <NavLink to="/overstock">売れ残った商品</NavLink>
        </nav>
        <ThemeToggle />
      </header>
      <InsightsBanner />
      <main>
        <Routes>
          <Route path="/" element={<SimulationPage />} />
          <Route path="/products" element={<ProductsPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/opportunities" element={<OpportunitiesPage />} />
          <Route path="/overstock" element={<OverstockPage />} />
          <Route path="/compare" element={<ComparisonPage />} />
          <Route path="/timing" element={<TimingPage />} />
        </Routes>
      </main>
    </div>
  )
}
