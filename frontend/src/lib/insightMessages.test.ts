import { describe, expect, it } from 'vitest'
import { buildInsightMessages } from './insightMessages'

describe('buildInsightMessages', () => {
  it('両方0件なら空配列を返す（バナーを表示しない）', () => {
    expect(buildInsightMessages(0, 0)).toEqual([])
  })

  it('機会損失だけあれば1件のメッセージを返す', () => {
    const result = buildInsightMessages(2, 0)

    expect(result).toEqual([
      { text: '値引きなしで早く売り切れた商品が2つあります（作る量を増やす候補）。', to: '/opportunities' },
    ])
  })

  it('過剰在庫だけあれば1件のメッセージを返す', () => {
    const result = buildInsightMessages(0, 3)

    expect(result).toEqual([
      { text: '値引きしても売れ残った商品が3つあります（作る量を減らす候補）。', to: '/overstock' },
    ])
  })

  it('両方あれば2件とも返す（機会損失が先）', () => {
    const result = buildInsightMessages(1, 5)

    expect(result).toEqual([
      { text: '値引きなしで早く売り切れた商品が1つあります（作る量を増やす候補）。', to: '/opportunities' },
      { text: '値引きしても売れ残った商品が5つあります（作る量を減らす候補）。', to: '/overstock' },
    ])
  })
})
