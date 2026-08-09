export interface StockChartStep {
  product_id: number
  step: number
  remaining_stock: number | null
}

export interface StockChartProduct {
  id: number
  name: string
}

export interface StockSeries {
  productId: number
  name: string
  data: (number | null)[]
}

export interface StockChartData {
  labels: number[]
  series: StockSeries[]
}

/**
 * 在庫推移グラフ（`SimulationPage`）用のデータを組み立てる純関数（docs/spec.md §4①）。
 * `visibleStep` までを描画範囲とし、ステップが進むごとに描画範囲が伸びていく。
 *
 * `remaining_stock` が無い/null のステップは「在庫が減っていない（満タン）」と誤読されないよう
 * null のまま返す（Chart.js はデータ点が null の箇所で線を途切れさせる）。`SimulationPage` が使う
 * `POST /api/simulations` の応答では実際には常に非nullだが、`StepOut.remaining_stock` の型が
 * 履歴詳細（`GET /api/simulations/{id}`。削除済み商品でnullになりうる。§6 Product）と共有のため、
 * ここで意味の取り違えが起きないようにしておく。
 */
export function buildStockChartData(
  steps: StockChartStep[],
  products: StockChartProduct[],
  visibleStep: number,
): StockChartData {
  const productIds = [...new Set(steps.map((s) => s.product_id))]
  const labels = Array.from({ length: visibleStep }, (_, i) => i)

  const series = productIds.map((pid) => {
    const product = products.find((p) => p.id === pid)
    const byStep = new Map(
      steps.filter((s) => s.product_id === pid).map((s) => [s.step, s.remaining_stock]),
    )
    return {
      productId: pid,
      name: product?.name ?? `商品${pid}`,
      data: labels.map((step) => byStep.get(step) ?? null),
    }
  })

  return { labels, series }
}
