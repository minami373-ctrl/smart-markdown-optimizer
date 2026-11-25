import { describe, expect, it } from 'vitest'
import { discountLabel, zubariPrice } from './discountLabel'

describe('discountLabel', () => {
  it('0%・30%・半額は売り場の言葉で表す', () => {
    expect(discountLabel(0, 430)).toBe('値引きなし')
    expect(discountLabel(0.3, 430)).toBe('30%引き')
    expect(discountLabel(0.5, 430)).toBe('半額')
  })

  it('半額より大きい値引きはズバリ引きとして10円単位の値段で表す', () => {
    // 430円の55%引き = 193.5円 → 10円単位に切り下げて190円
    expect(discountLabel(0.55, 430)).toBe('ズバリ ¥190')
  })

  it('単価が無い商品のズバリ引きは率で表す', () => {
    expect(discountLabel(0.6, null)).toBe('ズバリ引き（60%引き）')
  })
})

describe('zubariPrice', () => {
  it('下限（元の値段の75%引き）を下回らない', () => {
    // 430円の75%引き = 107.5円。切り下げると100円で下限を割るので、下限を10円単位に切り上げた110円
    expect(zubariPrice(430, 0.75)).toBe(110)
  })

  it('割り切れる場合はそのまま', () => {
    expect(zubariPrice(200, 0.6)).toBe(80)
  })
})
