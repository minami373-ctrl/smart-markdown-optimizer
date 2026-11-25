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
        <div className="brand">見切り品ダイナミックプライシング</div>
        <nav>
          <NavLink to="/" end>
            シミュレーション
          </NavLink>
          <NavLink to="/products">商品設定</NavLink>
          <NavLink to="/history">履歴</NavLink>
          <NavLink to="/opportunities">機会損失分析</NavLink>
          <NavLink to="/overstock">過剰在庫分析</NavLink>
          <NavLink to="/compare">固定スケジュール比較</NavLink>
          <NavLink to="/timing">値引きタイミング傾向</NavLink>
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
