import { describe, expect, it } from 'vitest'
import { DEFAULT_HISTORY_FILTERS, filterRuns } from './historyFilter'
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
    finals: [],
    stock_adjustments: [],
    ...overrides,
  }
}

describe('filterRuns', () => {
  it('デフォルト（すべて）では全件そのまま返す', () => {
    const runs = [makeRun({ id: 1, weather: '晴れ' }), makeRun({ id: 2, weather: '雨' })]

    const result = filterRuns(runs, DEFAULT_HISTORY_FILTERS)

    expect(result).toEqual(runs)
  })

  it('天気で絞り込む', () => {
    const runs = [
      makeRun({ id: 1, weather: '晴れ' }),
      makeRun({ id: 2, weather: '雨' }),
      makeRun({ id: 3, weather: '雨' }),
    ]

    const result = filterRuns(runs, { ...DEFAULT_HISTORY_FILTERS, weather: '雨' })

    expect(result.map((r) => r.id)).toEqual([2, 3])
  })

  it('曜日で絞り込む', () => {
    const runs = [
      makeRun({ id: 1, day_type: '平日' }),
      makeRun({ id: 2, day_type: '休日' }),
    ]

    const result = filterRuns(runs, { ...DEFAULT_HISTORY_FILTERS, dayType: '休日' })

    expect(result.map((r) => r.id)).toEqual([2])
  })

  it('イベント有無で絞り込む', () => {
    const runs = [
      makeRun({ id: 1, has_event: true }),
      makeRun({ id: 2, has_event: false }),
    ]

    expect(
      filterRuns(runs, { ...DEFAULT_HISTORY_FILTERS, hasEvent: 'あり' }).map((r) => r.id),
    ).toEqual([1])
    expect(
      filterRuns(runs, { ...DEFAULT_HISTORY_FILTERS, hasEvent: 'なし' }).map((r) => r.id),
    ).toEqual([2])
  })

  it('複数条件はAND（すべて満たすものだけ残る）', () => {
    const runs = [
      makeRun({ id: 1, weather: '雨', day_type: '休日' }),
      makeRun({ id: 2, weather: '雨', day_type: '平日' }),
      makeRun({ id: 3, weather: '晴れ', day_type: '休日' }),
    ]

    const result = filterRuns(runs, { ...DEFAULT_HISTORY_FILTERS, weather: '雨', dayType: '休日' })

    expect(result.map((r) => r.id)).toEqual([1])
  })

  it('一致するものが無ければ空配列を返す', () => {
    const runs = [makeRun({ id: 1, weather: '晴れ' })]

    const result = filterRuns(runs, { ...DEFAULT_HISTORY_FILTERS, weather: '雨' })

    expect(result).toEqual([])
  })
})
