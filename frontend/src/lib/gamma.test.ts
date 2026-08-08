import { describe, expect, it } from 'vitest'
import { gammaCurve, gammaPdf } from './gamma'

describe('gammaPdf', () => {
  it('x<=0 では 0 を返す', () => {
    expect(gammaPdf(0, 2, 2)).toBe(0)
    expect(gammaPdf(-1, 2, 2)).toBe(0)
  })

  it('alpha=1 のとき指数分布と一致する（beta * exp(-beta * x)）', () => {
    const got = gammaPdf(1, 1, 2)
    const expected = 2 * Math.exp(-2)
    expect(got).toBeCloseTo(expected, 6)
  })

  it('平均が同じでもデータが増える（alpha・betaが大きい）ほど山が高く鋭くなる', () => {
    // 事前ワークのスライド通り「山が高く尖る」ことを検証する。
    // 平均(alpha/beta)を1に揃えたまま、alpha・betaを10倍にすると分散(alpha/beta^2)は1/10になる
    const wide = gammaPdf(1, 2, 2) // 平均1・分散0.5
    const narrow = gammaPdf(1, 20, 20) // 平均1・分散0.05
    expect(narrow).toBeGreaterThan(wide)
  })

  it('alpha<1（反射公式を通る値）でもNaN/Infinityにならない', () => {
    const got = gammaPdf(0.3, 0.3, 2)
    expect(Number.isFinite(got)).toBe(true)
    expect(got).toBeGreaterThanOrEqual(0)
  })

  it('シミュレーション終盤相当の大きなalpha/betaでもNaN/Infinityにならない', () => {
    // 40ステップ・elasticity 0.18・70%引きが続いた場合を想定した規模
    const got = gammaPdf(30, 55, 90)
    expect(Number.isFinite(got)).toBe(true)
    expect(got).toBeGreaterThanOrEqual(0)
  })
})

describe('gammaCurve', () => {
  it('指定した点数ぶんのx,yを返す', () => {
    const { xs, ys } = gammaCurve(3, 2, 10)
    expect(xs).toHaveLength(10)
    expect(ys).toHaveLength(10)
    expect(xs[0]).toBe(0)
    expect(ys[0]).toBe(0) // x=0ではPDFは0
  })
})
