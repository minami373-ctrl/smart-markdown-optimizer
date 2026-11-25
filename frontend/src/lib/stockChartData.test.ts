import { describe, expect, it } from 'vitest'
import { buildStockChartData } from './stockChartData'

const PRODUCTS = [
  { id: 1, name: '唐揚げ' },
  { id: 2, name: 'おでん' },
]

describe('buildStockChartData', () => {
  it('visibleStepの数だけlabelsを作り、ステップが進むごとに描画範囲が伸びる', () => {
    const steps = [
      { product_id: 1, step: 0, remaining_stock: 10 },
      { product_id: 1, step: 1, remaining_stock: 8 },
      { product_id: 1, step: 2, remaining_stock: 5 },
    ]

    expect(buildStockChartData(steps, PRODUCTS, 0).labels).toEqual([])
    expect(buildStockChartData(steps, PRODUCTS, 1).labels).toEqual([0])
    expect(buildStockChartData(steps, PRODUCTS, 2).labels).toEqual([0, 1])

    const full = buildStockChartData(steps, PRODUCTS, 3)
    expect(full.labels).toEqual([0, 1, 2])
    expect(full.series).toEqual([{ productId: 1, name: '唐揚げ', data: [10, 8, 5] }])
  })

  it('商品ごとに系列を分ける', () => {
    const steps = [
      { product_id: 1, step: 0, remaining_stock: 10 },
      { product_id: 2, step: 0, remaining_stock: 20 },
      { product_id: 1, step: 1, remaining_stock: 7 },
      { product_id: 2, step: 1, remaining_stock: 18 },
    ]

    const result = buildStockChartData(steps, PRODUCTS, 2)

    expect(result.series).toEqual([
      { productId: 1, name: '唐揚げ', data: [10, 7] },
      { productId: 2, name: 'おでん', data: [20, 18] },
    ])
  })

  it('remaining_stockがnullのステップはnullのまま返す（満タン扱いにしない）', () => {
    const steps = [
      { product_id: 1, step: 0, remaining_stock: 10 },
      { product_id: 1, step: 1, remaining_stock: null },
    ]

    const result = buildStockChartData(steps, PRODUCTS, 2)

    expect(result.series).toEqual([{ productId: 1, name: '唐揚げ', data: [10, null] }])
  })

  it('データが無いステップ（未到達）もnullのまま返す', () => {
    const steps = [{ product_id: 1, step: 0, remaining_stock: 10 }]

    // visibleStep=2だがstep=1のデータが無いケース
    const result = buildStockChartData(steps, PRODUCTS, 2)

    expect(result.series).toEqual([{ productId: 1, name: '唐揚げ', data: [10, null] }])
  })

  it('商品一覧に無いproduct_idは商品${id}のフォールバック名になる', () => {
    const steps = [{ product_id: 99, step: 0, remaining_stock: 3 }]

    const result = buildStockChartData(steps, PRODUCTS, 1)

    expect(result.series).toEqual([{ productId: 99, name: '商品99', data: [3] }])
  })
})

import { buildCategoryStockChartData } from './stockChartData'

describe('buildCategoryStockChartData', () => {
  it('種類ごとに残り在庫を合計する（12本の線を3本にまとめる）', () => {
    const steps = [
      { product_id: 1, step: 0, remaining_stock: 10 },
      { product_id: 2, step: 0, remaining_stock: 5 },
      { product_id: 3, step: 0, remaining_stock: 7 },
      { product_id: 1, step: 1, remaining_stock: 8 },
      { product_id: 2, step: 1, remaining_stock: 4 },
      { product_id: 3, step: 1, remaining_stock: null },
    ]
    const products = [
      { id: 1, category: '弁当・丼' },
      { id: 2, category: '弁当・丼' },
      { id: 3, category: '揚げ物の単品' },
    ]

    const { labels, series } = buildCategoryStockChartData(steps, products, 2)

    expect(labels).toEqual([0, 1])
    expect(series).toEqual([
      { category: '弁当・丼', data: [15, 12] },
      { category: '揚げ物の単品', data: [7, null] },
    ])
  })
})
