/**
 * 今が1日のどの区切りかを、売り場の言葉で返す純関数（docs/spec.md §4①・§5.12。2026-11-26追加）。
 * backend/services/simulation.py の RESTOCK_STEP（16:00）・EARLIEST_DISCOUNT_STEP（18:06）・
 * ZUBARI_START_STEP（21:06）と同じ区切り。40ステップ（1ステップ18分）が前提。
 */
export const RESTOCK_STEP = 20
export const EARLIEST_DISCOUNT_STEP = 27
export const ZUBARI_START_STEP = 37

export function dayPhase(visibleStep: number, totalSteps: number): string {
  if (totalSteps > 0 && visibleStep >= totalSteps) return '閉店'
  if (visibleStep < RESTOCK_STEP) return '朝の分を定価で販売中'
  if (visibleStep < EARLIEST_DISCOUNT_STEP) return '16時に補充済み・定価で販売中'
  if (visibleStep < ZUBARI_START_STEP) return '値引きの時間（30%引き → 半額）'
  return 'ズバリ引きの時間'
}
