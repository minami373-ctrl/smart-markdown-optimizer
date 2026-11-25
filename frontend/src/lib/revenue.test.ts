import { describe, expect, it } from 'vitest'
import { computeRevenue } from './revenue'

describe('computeRevenue', () => {
  it('値引きが一度も無ければ 数量×単価 の単純合計になる', () => {
    const steps = [
      { step: 0, quantity: 2, recommended_rate: 0 },
      { step: 1, quantity: 3, recommended_rate: 0 },
    ]

    expect(computeRevenue(steps, 100)).toBe(500) // (2+3) * 100
  })

  it('値引きは決まった次のステップから適用される（決まったそのステップにはまだ効かない）', () => {
    const steps = [
      { step: 0, quantity: 2, recommended_rate: 0.5 }, // ここで50%引きが決定
      { step: 1, quantity: 2, recommended_rate: 0.5 },
    ]

    // step0は値引き0%（決定前）: 2*100=200、step1は50%引きが効く: 2*100*0.5=100
    expect(computeRevenue(steps, 100)).toBe(300)
  })

  it('引数のstepsの順序に依存しない（内部でstep順にソートする）', () => {
    const inOrder = [
      { step: 0, quantity: 2, recommended_rate: 0.5 },
      { step: 1, quantity: 2, recommended_rate: 0.5 },
    ]
    const shuffled = [inOrder[1], inOrder[0]]

    expect(computeRevenue(shuffled, 100)).toBe(computeRevenue(inOrder, 100))
  })

  it('販売数0のステップは売上に加算しない', () => {
    const steps = [
      { step: 0, quantity: 0, recommended_rate: 0 },
      { step: 1, quantity: 5, recommended_rate: 0 },
    ]

    expect(computeRevenue(steps, 100)).toBe(500)
  })

  it('stepsが空なら0を返す', () => {
    expect(computeRevenue([], 100)).toBe(0)
  })

  it('applied_rate（モニターに実際に出ていた値引き）があれば、提案ではなくそちらで計算する', () => {
    // ステップ0でズバリ引き（75%）が提案されたが承認待ちで、モニターは半額のまま
    const steps = [
      { step: 0, quantity: 0, recommended_rate: 0.75, applied_rate: 0.5 },
      { step: 1, quantity: 2, recommended_rate: 0.75, applied_rate: 0.5 },
    ]

    // ステップ1の販売2個は半額（50円）で売れた → 100円（提案の75%引きなら50円になる）
    expect(computeRevenue(steps, 100)).toBe(100)
  })
})
