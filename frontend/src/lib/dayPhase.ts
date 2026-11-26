/**
 * 今が1日のどの区切りかを、売り場の言葉で返す純関数（docs/spec.md §4①・§5.12・§5.19）。
 * backend/services/simulation.py の RESTOCK_STEP（16:00）・EARLIEST_DISCOUNT_STEP（18:00）と同じ区切り。
 * 48ステップ（1ステップ15分）が前提。
 */
export const RESTOCK_STEP = 24
export const EARLIEST_DISCOUNT_STEP = 32

export function dayPhase(visibleStep: number, totalSteps: number): string {
  if (totalSteps > 0 && visibleStep >= totalSteps) return '閉店'
  if (visibleStep < RESTOCK_STEP) return '朝の分を定価で販売中'
  if (visibleStep < EARLIEST_DISCOUNT_STEP) return '16時に補充済み・定価で販売中'
  return '値引きの時間（15分ごとに確認）'
}
