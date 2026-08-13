export type StockAdjustmentReason = 'opportunity' | 'overstock'

export interface StockAdjustmentHistoryEntry {
  new_initial_stock: number
  reason: StockAdjustmentReason
}

export interface StockAdjustmentHistoryData {
  labels: string[] // 発生順（1始まり）
  values: number[] // その時点のinitial_stock
  reasons: StockAdjustmentReason[]
}

/**
 * 在庫調整履歴グラフ（`StockAdjustmentHistory`）用のデータを組み立てる純関数（docs/spec.md §5.8）。
 * `entries`は`GET /api/products/{id}/stock-adjustments`の応答（すでに発生順=created_at昇順）を
 * そのまま渡す想定。横軸は発生順（1始まりの通し番号）、縦軸はその時点の`initial_stock`。
 */
export function buildStockAdjustmentHistoryData(
  entries: StockAdjustmentHistoryEntry[],
): StockAdjustmentHistoryData {
  return {
    labels: entries.map((_, i) => `${i + 1}`),
    values: entries.map((e) => e.new_initial_stock),
    reasons: entries.map((e) => e.reason),
  }
}
