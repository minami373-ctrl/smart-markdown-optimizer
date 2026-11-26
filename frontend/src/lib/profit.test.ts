import { describe, expect, it } from 'vitest'
import { COST_RATIO, costOf, producedOf, profitOf } from './profit'

describe('profit', () => {
  it('原価は売値の6割（仮）', () => {
    expect(COST_RATIO).toBe(0.6)
    expect(costOf(400, 10)).toBe(2400)
  })

  it('利益＝売上−原価（売れ残った分にも原価がかかる）', () => {
    // 400円を10個作り、8個を合計2,800円で売った → 2,800 − 2,400 = 400円
    expect(profitOf(2800, 400, 10)).toBe(400)
  })

  it('作った量は最初のステップの「1日の残り＋売れた数」', () => {
    const steps = [
      { step: 1, quantity: 2, remaining_stock: 16 },
      { step: 0, quantity: 2, remaining_stock: 18 },
    ]
    expect(producedOf(steps)).toBe(20)
    expect(producedOf([])).toBeNull()
  })
})
