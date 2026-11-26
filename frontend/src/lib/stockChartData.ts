export interface StockChartStep {
  product_id: number
  step: number
  remaining_stock: number | null
  //: 店頭の在庫（あれば種類ごとの在庫推移はこちらを使う。16時の補充で増える）
  shelf_stock?: number | null
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

export interface CategoryProduct {
  id: number
  category: string
}

/** 種類ごとの在庫推移の色（docs/spec.md §4①。2026-11-26） */
export const CATEGORY_COLORS: Record<string, string> = {
  '弁当・丼': '#b5651d',
  '揚げ物の単品': '#1f5f99',
  '軽食・つまみ': '#3a7d44',
}

/**
 * 在庫推移を商品の種類ごとの合計にまとめる純関数（2026-11-26追加）。12本の線では読めないため、
 * 「弁当・丼／揚げ物の単品／軽食・つまみ」の3本にする。種類の並びは`products`に出てくる順。
 * あるステップでその種類の商品の在庫が1つも分からなければnull（線を途切れさせる）。
 */
export function buildCategoryStockChartData(
  steps: StockChartStep[],
  products: CategoryProduct[],
  visibleStep: number,
): { labels: number[]; series: { category: string; data: (number | null)[] }[] } {
  const labels = Array.from({ length: visibleStep }, (_, i) => i)
  const categoryOf = new Map(products.map((p) => [p.id, p.category]))
  const categories = [...new Set(products.map((p) => p.category))]
  const series = categories.map((category) => {
    const totals = labels.map((step) => {
      let total: number | null = null
      for (const s of steps) {
        if (s.step !== step || categoryOf.get(s.product_id) !== category) continue
        const stock = s.shelf_stock ?? s.remaining_stock
        if (stock == null) continue
        total = (total ?? 0) + stock
      }
      return total
    })
    return { category, data: totals }
  })
  return { labels, series }
}
