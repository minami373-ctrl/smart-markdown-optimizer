import { useEffect, useState } from 'react'
import { createProduct, deleteProduct, fetchProducts, updateProduct } from '../api/products'
import type { Product } from '../api/types'

//: §5.4の倍率 晴れ1.2×平日1.0×イベントなし1.0×beta2.0 の逆算（docs/spec.md §4②）
const BASE_KEY = '晴れ_平日_なし'
const BASE_KEY_MULTIPLIER = 1.2 * 1.0 * 1.0 * 2.0

function estimateBaseDemand(p: Product): number {
  const alpha = p.prior_demand[BASE_KEY]?.alpha
  if (alpha == null) return 1.0
  return Math.round((alpha / BASE_KEY_MULTIPLIER) * 100) / 100
}

interface ProductFormValues {
  name: string
  initialStock: number
  elasticity: number
  baseDemand: number
}

function ProductForm({
  values,
  onChange,
  onSubmit,
  submitting,
  submitLabel,
  onCancel,
}: {
  values: ProductFormValues
  onChange: (values: ProductFormValues) => void
  onSubmit: () => void
  submitting: boolean
  submitLabel: string
  onCancel?: () => void
}) {
  const canSubmit =
    values.name.trim().length > 0 &&
    values.initialStock > 0 &&
    values.elasticity > 0 &&
    values.baseDemand > 0

  return (
    <div className="form-row">
      <label>
        商品名
        <input
          type="text"
          value={values.name}
          onChange={(e) => onChange({ ...values, name: e.target.value })}
        />
      </label>
      <label>
        初期在庫
        <input
          type="number"
          min={1}
          value={values.initialStock}
          onChange={(e) => onChange({ ...values, initialStock: Number(e.target.value) })}
        />
      </label>
      <label>
        値引き感度
        <input
          type="number"
          min={0.01}
          step={0.01}
          value={values.elasticity}
          onChange={(e) => onChange({ ...values, elasticity: Number(e.target.value) })}
        />
      </label>
      <label>
        基準需要（平日・晴れ・1stepの平均個数）
        <input
          type="number"
          min={0.1}
          step={0.1}
          value={values.baseDemand}
          onChange={(e) => onChange({ ...values, baseDemand: Number(e.target.value) })}
        />
      </label>
      <button className="primary" onClick={onSubmit} disabled={!canSubmit || submitting}>
        {submitting ? '保存中…' : submitLabel}
      </button>
      {onCancel && (
        <button onClick={onCancel} disabled={submitting}>
          キャンセル
        </button>
      )}
    </div>
  )
}

export default function ProductsPage() {
  const [products, setProducts] = useState<Product[]>([])
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const [addValues, setAddValues] = useState<ProductFormValues>({
    name: '',
    initialStock: 20,
    elasticity: 0.12,
    baseDemand: 1.0,
  })

  const [editingId, setEditingId] = useState<number | null>(null)
  const [editValues, setEditValues] = useState<ProductFormValues | null>(null)

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
        name: addValues.name,
        initial_stock: addValues.initialStock,
        elasticity: addValues.elasticity,
        base_demand: addValues.baseDemand,
      })
      setAddValues({ ...addValues, name: '' })
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : '追加に失敗しました')
    } finally {
      setSubmitting(false)
    }
  }

  function startEdit(p: Product) {
    setError(null)
    setEditingId(p.id)
    setEditValues({
      name: p.name,
      initialStock: p.initial_stock,
      elasticity: p.elasticity,
      baseDemand: estimateBaseDemand(p),
    })
  }

  async function handleSaveEdit() {
    if (editingId === null || editValues === null) return
    setError(null)
    setSubmitting(true)
    try {
      await updateProduct(editingId, {
        name: editValues.name,
        initial_stock: editValues.initialStock,
        elasticity: editValues.elasticity,
        base_demand: editValues.baseDemand,
      })
      setEditingId(null)
      setEditValues(null)
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : '保存に失敗しました')
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

  return (
    <div>
      <h1>商品設定</h1>
      <p>商品の事前分布（天気・曜日・イベント別の基準需要）を確認・追加・編集・削除できます。</p>

      <div className="card">
        <h2>商品を追加</h2>
        <ProductForm
          values={addValues}
          onChange={setAddValues}
          onSubmit={handleAdd}
          submitting={submitting}
          submitLabel="追加"
        />
        {error && <p className="error">{error}</p>}
      </div>

      {products.map((p) => (
        <div className="card" key={p.id}>
          {editingId === p.id && editValues ? (
            <>
              <h2>{p.name} を編集</h2>
              <ProductForm
                values={editValues}
                onChange={setEditValues}
                onSubmit={handleSaveEdit}
                submitting={submitting}
                submitLabel="保存"
                onCancel={() => {
                  setEditingId(null)
                  setEditValues(null)
                }}
              />
            </>
          ) : (
            <h2>
              {p.name}（初期在庫 {p.initial_stock}・値引き感度 {p.elasticity}）
              <button className="link-secondary" onClick={() => startEdit(p)}>
                編集
              </button>
              <button className="link-danger" onClick={() => handleDelete(p.id)}>
                削除
              </button>
            </h2>
          )}
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
