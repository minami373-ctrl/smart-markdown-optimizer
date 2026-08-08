import { NavLink, Route, Routes } from 'react-router-dom'
import SimulationPage from './pages/SimulationPage'
import ProductsPage from './pages/ProductsPage'
import HistoryPage from './pages/HistoryPage'

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
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<SimulationPage />} />
          <Route path="/products" element={<ProductsPage />} />
          <Route path="/history" element={<HistoryPage />} />
        </Routes>
      </main>
    </div>
  )
}
