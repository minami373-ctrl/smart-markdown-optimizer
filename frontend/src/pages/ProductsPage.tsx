import { useEffect, useState } from 'react'
import {
  createProduct,
  deleteProduct,
  fetchProducts,
  fetchStockAdjustments,
  updateProduct,
} from '../api/products'
import { PRODUCT_CATEGORIES } from '../api/types'
import type { Product, ProductCategory, StockAdjustmentLogEntry } from '../api/types'
import StockAdjustmentHistory from '../components/StockAdjustmentHistory'

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
  //: 種類（docs/spec.md §2.1）
  category: ProductCategory
  initialStock: number
  elasticity: number
  baseDemand: number
  //: 単価（円・任意）。'' は未入力（＝サーバーへは null で送る）を表す
  unitPrice: number | ''
}

/**
 * 追加・保存ボタンが無効化されている理由を1行で返す（docs/spec.md §4②「入力エラーのヒント表示」）。
 * 商品名→初期在庫→値引き感度→基準需要の順で、最初に引っかかった1件だけを返す。
 * すべて満たしていれば null（＝ヒントを出さない）。
 */
function getValidationMessage(values: ProductFormValues): string | null {
  // !(x > 0) を使う（x <= 0 ではなく）。number入力が不正でNaNになった場合も
  // NaN > 0 は false なので !(NaN > 0) は true になり、安全側（未入力扱い）に倒れる
  if (values.name.trim().length === 0) return '商品名を入力してください'
  if (!(values.initialStock > 0)) return '初期在庫は1以上にしてください'
  if (!(values.elasticity > 0)) return '値引き感度は0より大きい値にしてください'
  if (!(values.baseDemand > 0)) return '基準需要は0より大きい値にしてください'
  return null
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
  const validationMessage = getValidationMessage(values)
  const canSubmit = validationMessage === null

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
        種類
        <select
          value={values.category}
          onChange={(e) => onChange({ ...values, category: e.target.value as ProductCategory })}
        >
          {PRODUCT_CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
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
        基準需要（晴れの平日・18分あたりに売れる平均の個数）
        <input
          type="number"
          min={0.1}
          step={0.1}
          value={values.baseDemand}
          onChange={(e) => onChange({ ...values, baseDemand: Number(e.target.value) })}
        />
      </label>
      <label>
        単価（円・任意）
        <input
          type="number"
          min={0}
          value={values.unitPrice}
          onChange={(e) =>
            onChange({
              ...values,
              unitPrice: e.target.value === '' ? '' : Number(e.target.value),
            })
          }
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
      {validationMessage && <span className="hint">{validationMessage}</span>}
    </div>
  )
}

export default function ProductsPage() {
  const [products, setProducts] = useState<Product[]>([])
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  //: 商品ごとの在庫調整履歴（docs/spec.md §5.8）。キーはproduct_id
  const [adjustments, setAdjustments] = useState<Record<number, StockAdjustmentLogEntry[]>>({})

  const [addValues, setAddValues] = useState<ProductFormValues>({
    name: '',
    category: '弁当・丼',
    initialStock: 20,
    elasticity: 0.12,
    baseDemand: 1.0,
    unitPrice: '',
  })

  const [editingId, setEditingId] = useState<number | null>(null)
  const [editValues, setEditValues] = useState<ProductFormValues | null>(null)
  //: 編集の保存失敗は編集中のカード自身に表示する（使い勝手向上。docs/spec.md §4②）。
  // 「商品を追加」の失敗（error）とは表示場所を分けるため別のstateにする
  const [editError, setEditError] = useState<string | null>(null)

  function load() {
    fetchProducts()
      .then((loaded) => {
        setProducts(loaded)
        loadAdjustments(loaded)
      })
      .catch((e) => setError(e.message))
  }

  //: 在庫調整履歴（docs/spec.md §5.8）は補助的な表示のため、取得に失敗しても
  // 商品一覧本体のエラー（error state）にはしない（その商品の履歴が空のまま表示されるだけ）
  function loadAdjustments(loaded: Product[]) {
    Promise.all(
      loaded.map((p) =>
        fetchStockAdjustments(p.id)
          .then((entries) => [p.id, entries] as const)
          .catch(() => [p.id, []] as const),
      ),
    ).then((pairs) => setAdjustments(Object.fromEntries(pairs)))
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
        category: addValues.category,
        initial_stock: addValues.initialStock,
        elasticity: addValues.elasticity,
        base_demand: addValues.baseDemand,
        unit_price: addValues.unitPrice === '' ? null : addValues.unitPrice,
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
    // トップの「商品を追加」カードに残っている古いエラー（追加・削除の失敗）も、
    // 編集という別の操作を始めたタイミングで一緒に消す（今の操作と無関係なエラーが
    // 画面に残り続けるのを防ぐ。editErrorとの役割分担はdocs/spec.md §4②参照）
    setError(null)
    setEditError(null)
    setEditingId(p.id)
    setEditValues({
      name: p.name,
      category: p.category,
      initialStock: p.initial_stock,
      elasticity: p.elasticity,
      baseDemand: estimateBaseDemand(p),
      unitPrice: p.unit_price ?? '',
    })
  }

  async function handleSaveEdit() {
    if (editingId === null || editValues === null) return
    setEditError(null)
    setSubmitting(true)
    try {
      await updateProduct(editingId, {
        name: editValues.name,
        category: editValues.category,
        initial_stock: editValues.initialStock,
        elasticity: editValues.elasticity,
        base_demand: editValues.baseDemand,
        unit_price: editValues.unitPrice === '' ? null : editValues.unitPrice,
      })
      setEditingId(null)
      setEditValues(null)
      setEditError(null)
      load()
    } catch (e) {
      setEditError(e instanceof Error ? e.message : '保存に失敗しました')
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
      <h1>商品</h1>
      <p>売り場に並べる惣菜です。種類・1日に作る量・値段・値引きの効き方（値引き感度）を決めます。</p>

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
                  setEditError(null)
                }}
              />
              {editError && <p className="error">{editError}</p>}
            </>
          ) : (
            <h2>
              {p.name}（{p.category}・初期在庫 {p.initial_stock}・値引き感度 {p.elasticity}
              {p.unit_price != null && `・単価 ¥${p.unit_price}`}）
              <button className="link-secondary" onClick={() => startEdit(p)}>
                編集
              </button>
              <button className="link-danger" onClick={() => handleDelete(p.id)}>
                削除
              </button>
            </h2>
          )}
          <StockAdjustmentHistory entries={adjustments[p.id] ?? []} />
          <details className="prior-details">
            <summary>条件ごとの売れ方の予測（天気・曜日・イベント・長期休み）</summary>
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
          </details>
        </div>
      ))}
    </div>
  )
}
