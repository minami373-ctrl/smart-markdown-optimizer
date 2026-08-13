export interface RevenueStep {
  step: number
  quantity: number
  recommended_rate: number
}

/**
 * 商品1つぶんの推定売上を計算する純関数（docs/spec.md §4①「単価が設定されている商品だけ…」）。
 *
 * ステップごとに「販売数 × 単価 × (1 − そのステップで適用されていた値引き率)」を積み上げる。
 * 値引き提案はそのステップの販売**後**に決まり、次のステップから効いてくる
 * （`services/opportunity.py`の`build_step_records`と同じ考え方。§5.2）。
 * そのため各ステップの`recommended_rate`は「次のステップから使う値」であり、
 * このステップ自体の販売に適用されていたのは**1つ前のステップの`recommended_rate`**
 * （ステップ0は値引き0%として扱う）。
 */
export function computeRevenue(steps: RevenueStep[], unitPrice: number): number {
  const sorted = [...steps].sort((a, b) => a.step - b.step)
  let currentRate = 0
  let revenue = 0
  for (const s of sorted) {
    revenue += s.quantity * unitPrice * (1 - currentRate)
    currentRate = s.recommended_rate
  }
  return revenue
}
