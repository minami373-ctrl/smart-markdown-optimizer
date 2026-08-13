import { describe, expect, it } from 'vitest'
import { buildHistoryCsv } from './historyCsv'
import type { SimulationSummary } from '../api/types'

function makeRun(overrides: Partial<SimulationSummary> = {}): SimulationSummary {
  return {
    id: 1,
    weather: '晴れ',
    day_type: '平日',
    has_event: false,
    target_waste_rate: 0.03,
    status: 'finished',
    started_at: '2026-08-10T12:00:00',
    finished_at: '2026-08-10T12:01:00',
    finals: [{ product_id: 1, product_name: '唐揚げ', final_waste_rate: 0.05, achieved: true }],
    stock_adjustments: [],
    ...overrides,
  }
}

describe('buildHistoryCsv', () => {
  it('1行目はヘッダー行になる', () => {
    const csv = buildHistoryCsv([])

    expect(csv).toBe(
      '実行ID,日時,天気,曜日,イベント,目標廃棄率(%),商品名,実績廃棄率(%),達成可否',
    )
  })

  it('1回の実行×1商品を1行にする', () => {
    const csv = buildHistoryCsv([makeRun()])
    const lines = csv.split('\r\n')

    expect(lines).toHaveLength(2)
    expect(lines[1]).toBe('1,2026/8/10 12:00:00,晴れ,平日,なし,3,唐揚げ,5,達成')
  })

  it('1回の実行に複数商品あれば商品数ぶんの行になる', () => {
    const csv = buildHistoryCsv([
      makeRun({
        finals: [
          { product_id: 1, product_name: '唐揚げ', final_waste_rate: 0.05, achieved: true },
          { product_id: 2, product_name: 'おでん', final_waste_rate: 0.2, achieved: false },
        ],
      }),
    ])
    const lines = csv.split('\r\n')

    expect(lines).toHaveLength(3)
    expect(lines[1]).toContain('唐揚げ')
    expect(lines[1]).toContain('達成')
    expect(lines[2]).toContain('おでん')
    expect(lines[2]).toContain('未達')
  })

  it('商品が1件も無い回でも、回自体の行は空欄で出力される（欠落しない）', () => {
    const csv = buildHistoryCsv([makeRun({ finals: [] })])
    const lines = csv.split('\r\n')

    expect(lines).toHaveLength(2)
    expect(lines[1]).toBe('1,2026/8/10 12:00:00,晴れ,平日,なし,3,,,')
  })

  it('イベント有無を あり/なし で表す', () => {
    const csv = buildHistoryCsv([makeRun({ has_event: true })])

    expect(csv).toContain(',あり,')
  })

  it('商品名にカンマが含まれる場合はダブルクォートで囲む', () => {
    const csv = buildHistoryCsv([
      makeRun({
        finals: [
          { product_id: 1, product_name: '唐揚げ,特盛', final_waste_rate: 0.05, achieved: true },
        ],
      }),
    ])

    expect(csv).toContain('"唐揚げ,特盛"')
  })

  it('複数の実行回をすべて含める', () => {
    const csv = buildHistoryCsv([makeRun({ id: 1 }), makeRun({ id: 2 })])
    const lines = csv.split('\r\n')

    expect(lines).toHaveLength(3) // ヘッダー + 2行
  })

  it.each(['=1+1', '+1+1', '-1+1', '@SUM(A1)'])(
    'CSVインジェクション対策：商品名が"%s"のように=+-@で始まる場合はシングルクォートを足す',
    (dangerous) => {
      const csv = buildHistoryCsv([
        makeRun({
          finals: [{ product_id: 1, product_name: dangerous, final_waste_rate: 0.05, achieved: true }],
        }),
      ])

      expect(csv).toContain(`,'${dangerous},`)
    },
  )

  it('=+-@で始まらない普通の商品名にはシングルクォートを足さない', () => {
    const csv = buildHistoryCsv([makeRun()]) // makeRunのデフォルトは「唐揚げ」

    expect(csv).toContain(',唐揚げ,')
  })
})
