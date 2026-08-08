import { useEffect, useState } from 'react'
import { createProduct, deleteProduct, fetchProducts } from '../api/products'
import type { Product } from '../api/types'

export default function ProductsPage() {
  const [products, setProducts] = useState<Product[]>([])
  const [error, setError] = useState<string | null>(null)

  const [name, setName] = useState('')
  const [initialStock, setInitialStock] = useState(20)
  const [elasticity, setElasticity] = useState(0.12)
  const [baseDemand, setBaseDemand] = useState(1.0)
  const [submitting, setSubmitting] = useState(false)

  function load() {
    fetchProducts()
      .then(setProducts)
      .catch((e) => setError(e.message))
  }

  useEffect(() => {
    load()
  }, [])

  async function handleAdd() {
    setError(null)
    setSubmitting(true)
    try {
      await createProduct({
        name,
        initial_stock: initialStock,
        elasticity,
        base_demand: baseDemand,
      })
      setName('')
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : '追加に失敗しました')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleDelete(id: number) {
    setError(null)
    try {
      await deleteProduct(id)
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : '削除に失敗しました')
    }
  }

  const canSubmit = name.trim().length > 0 && initialStock > 0 && elasticity > 0 && baseDemand > 0

  return (
    <div>
      <h1>商品設定</h1>
      <p>商品の事前分布（天気・曜日・イベント別の基準需要）を確認・追加・削除できます。</p>

      <div className="card">
        <h2>商品を追加</h2>
        <div className="form-row">
          <label>
            商品名
            <input type="text" value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label>
            初期在庫
            <input
              type="number"
              min={1}
              value={initialStock}
              onChange={(e) => setInitialStock(Number(e.target.value))}
            />
          </label>
          <label>
            弾力性
            <input
              type="number"
              min={0.01}
              step={0.01}
              value={elasticity}
              onChange={(e) => setElasticity(Number(e.target.value))}
            />
          </label>
          <label>
            基準需要（平日・晴れ・1stepの平均個数）
            <input
              type="number"
              min={0.1}
              step={0.1}
              value={baseDemand}
              onChange={(e) => setBaseDemand(Number(e.target.value))}
            />
          </label>
          <button className="primary" onClick={handleAdd} disabled={!canSubmit || submitting}>
            {submitting ? '追加中…' : '追加'}
          </button>
        </div>
        {error && <p className="error">{error}</p>}
      </div>

      {products.map((p) => (
        <div className="card" key={p.id}>
          <h2>
            {p.name}（初期在庫 {p.initial_stock}・弾力性 {p.elasticity}）
            <button className="link-danger" onClick={() => handleDelete(p.id)}>
              削除
            </button>
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
