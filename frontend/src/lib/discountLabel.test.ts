import { describe, expect, it } from 'vitest'
import { discountLabel, monitorPrice } from './discountLabel'

describe('discountLabel', () => {
  it('すべて「〇%引き」で表す（5%刻み。§5.19）', () => {
    expect(discountLabel(0, 430)).toBe('値引きなし')
    expect(discountLabel(0.2, 430)).toBe('20%引き')
    expect(discountLabel(0.35, 430)).toBe('35%引き')
    expect(discountLabel(0.5, 430)).toBe('50%引き')
    expect(discountLabel(0.75, null)).toBe('75%引き')
  })
})

describe('monitorPrice', () => {
  it('1円単位で四捨五入した売値', () => {
    expect(monitorPrice(430, 0.2)).toBe(344)
    expect(monitorPrice(430, 0.55)).toBe(194)
    expect(monitorPrice(300, 0.35)).toBe(195)
  })
})
