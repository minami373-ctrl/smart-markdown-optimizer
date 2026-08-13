import { describe, expect, it } from 'vitest'
import { buildStockAdjustmentHistoryData } from './stockAdjustmentHistoryData'

describe('buildStockAdjustmentHistoryData', () => {
  it('0件なら全て空配列になる', () => {
    const result = buildStockAdjustmentHistoryData([])
    expect(result).toEqual({ labels: [], values: [], reasons: [] })
  })

  it('発生順に1始まりの通し番号ラベルを振り、initial_stockとreasonをそのまま並べる', () => {
    const entries = [
      { new_initial_stock: 45, reason: 'opportunity' as const },
      { new_initial_stock: 40, reason: 'overstock' as const },
      { new_initial_stock: 42, reason: 'opportunity' as const },
    ]

    const result = buildStockAdjustmentHistoryData(entries)

    expect(result.labels).toEqual(['1', '2', '3'])
    expect(result.values).toEqual([45, 40, 42])
    expect(result.reasons).toEqual(['opportunity', 'overstock', 'opportunity'])
  })
})
