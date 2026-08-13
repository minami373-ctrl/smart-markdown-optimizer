import { describe, expect, it } from 'vitest'
import { buildInsightMessages } from './insightMessages'

describe('buildInsightMessages', () => {
  it('両方0件なら空配列を返す（バナーを表示しない）', () => {
    expect(buildInsightMessages(0, 0)).toEqual([])
  })

  it('機会損失だけあれば1件のメッセージを返す', () => {
    const result = buildInsightMessages(2, 0)

    expect(result).toEqual([
      { text: '在庫不足の可能性がある商品が2件あります。', to: '/opportunities' },
    ])
  })

  it('過剰在庫だけあれば1件のメッセージを返す', () => {
    const result = buildInsightMessages(0, 3)

    expect(result).toEqual([
      { text: '過剰在庫の可能性がある商品が3件あります。', to: '/overstock' },
    ])
  })

  it('両方あれば2件とも返す（機会損失が先）', () => {
    const result = buildInsightMessages(1, 5)

    expect(result).toEqual([
      { text: '在庫不足の可能性がある商品が1件あります。', to: '/opportunities' },
      { text: '過剰在庫の可能性がある商品が5件あります。', to: '/overstock' },
    ])
  })
})
