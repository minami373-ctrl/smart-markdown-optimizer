/**
 * 原価と利益（docs/spec.md §5.20。2026-11-26追加）。
 *
 * 原価は売値の6割とする（仮の値）。全国スーパーマーケット協会の2023年の調査で、惣菜の目標利益率
 * （粗利率）の平均が37.8%だったことから換算した（100% − 37.8% ≒ 62%）。実際の店の値ではない。
 */
export const COST_RATIO = 0.6

interface StockStep {
  step: number
  quantity: number
  remaining_stock: number | null
}

/** その日に作った量＝最初のステップの「1日の残り＋売れた数」（朝の分＋16時の補充） */
export function producedOf(steps: StockStep[]): number | null {
  if (steps.length === 0) return null
  const first = steps.reduce((a, b) => (b.step < a.step ? b : a))
  if (first.remaining_stock == null) return null
  return first.remaining_stock + first.quantity
}

/** 原価＝単価×原価率×作った量（売れ残った分も、作った時点でお金はかかっている） */
export function costOf(unitPrice: number, produced: number): number {
  return unitPrice * COST_RATIO * produced
}

/** 利益（粗利）＝推定売上−原価 */
export function profitOf(revenue: number, unitPrice: number, produced: number): number {
  return revenue - costOf(unitPrice, produced)
}
