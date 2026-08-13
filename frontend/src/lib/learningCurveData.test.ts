import { describe, expect, it } from 'vitest'
import { buildLearningCurveData } from './learningCurveData'

describe('buildLearningCurveData', () => {
  it('実行回数ぶんのlabelsを1始まりで作る', () => {
    const runs = [
      { finals: [{ product_id: 1, product_name: '唐揚げ', final_waste_rate: 0.1 }] },
      { finals: [{ product_id: 1, product_name: '唐揚げ', final_waste_rate: 0.05 }] },
      { finals: [{ product_id: 1, product_name: '唐揚げ', final_waste_rate: 0.02 }] },
    ]

    const result = buildLearningCurveData(runs)

    expect(result.labels).toEqual([1, 2, 3])
  })

  it('商品ごとに系列を分け、実績廃棄率を%に変換する', () => {
    const runs = [
      {
        finals: [
          { product_id: 1, product_name: '唐揚げ', final_waste_rate: 0.1 },
          { product_id: 2, product_name: 'おでん', final_waste_rate: 0.2 },
        ],
      },
      {
        finals: [
          { product_id: 1, product_name: '唐揚げ', final_waste_rate: 0.05 },
          { product_id: 2, product_name: 'おでん', final_waste_rate: 0.15 },
        ],
      },
    ]

    const result = buildLearningCurveData(runs)

    expect(result.series).toEqual([
      { productId: 1, name: '唐揚げ', data: [10, 5] },
      { productId: 2, name: 'おでん', data: [20, 15] },
    ])
  })

  it('学習が進むにつれて廃棄率が下がっていく様子をそのまま表せる', () => {
    const runs = [
      { finals: [{ product_id: 1, product_name: '唐揚げ', final_waste_rate: 0.3 }] },
      { finals: [{ product_id: 1, product_name: '唐揚げ', final_waste_rate: 0.1 }] },
      { finals: [{ product_id: 1, product_name: '唐揚げ', final_waste_rate: 0.02 }] },
    ]

    const result = buildLearningCurveData(runs)

    const data = result.series[0].data
    expect(data[0]! > data[1]! && data[1]! > data[2]!).toBe(true)
  })

  it('ある回にその商品のfinalsが無ければnullを返す（線を途切れさせる）', () => {
    const runs = [
      {
        finals: [
          { product_id: 1, product_name: '唐揚げ', final_waste_rate: 0.1 },
          { product_id: 2, product_name: 'おでん', final_waste_rate: 0.2 },
        ],
      },
      { finals: [{ product_id: 1, product_name: '唐揚げ', final_waste_rate: 0.05 }] },
    ]

    const result = buildLearningCurveData(runs)

    const odenSeries = result.series.find((s) => s.productId === 2)
    expect(odenSeries?.data).toEqual([20, null])
  })

  it('runsが0件ならlabelsも系列も空になる', () => {
    const result = buildLearningCurveData([])

    expect(result.labels).toEqual([])
    expect(result.series).toEqual([])
  })
})
