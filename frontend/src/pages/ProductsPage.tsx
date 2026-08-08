import { useEffect, useState } from 'react'
import { fetchProducts } from '../api/products'
import type { Product } from '../api/types'

export default function ProductsPage() {
  const [products, setProducts] = useState<Product[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchProducts()
      .then(setProducts)
      .catch((e) => setError(e.message))
  }, [])

  if (error) return <p className="error">{error}</p>

  return (
    <div>
      <h1>商品設定</h1>
      <p>3商品の事前分布（天気・曜日・イベント別の基準需要）です。編集は今回対象外です。</p>
      {products.map((p) => (
        <div className="card" key={p.id}>
          <h2>
            {p.name}（初期在庫 {p.initial_stock}・弾力性 {p.elasticity}）
          </h2>
          <table>
            <thead>
              <tr>
                <th>条件</th>
                <th>alpha</th>
                <th>beta</th>
                <th>平均需要/step</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(p.prior_demand).map(([key, v]) => (
                <tr key={key}>
                  <td>{key.replace(/_/g, ' / ')}</td>
                  <td>{v.alpha}</td>
                  <td>{v.beta}</td>
                  <td>{Math.round((v.alpha / v.beta) * 100) / 100}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  )
}
