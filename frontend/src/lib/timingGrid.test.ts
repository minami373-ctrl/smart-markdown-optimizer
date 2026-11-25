import { describe, expect, it } from 'vitest'
import { buildTimingGrid, timingIntensity } from './timingGrid'
import type { ConditionTiming } from '../api/types'

describe('buildTimingGrid', () => {
  it('12マスの固定グリッドを組み立てる（3天気 × 4曜日・イベント組み合わせ）', () => {
    const grid = buildTimingGrid([])

    expect(grid).toHaveLength(3)
    for (const row of grid) {
      expect(row).toHaveLength(4)
    }
  })

  it('データが無いマスはdata: nullになる', () => {
    const grid = buildTimingGrid([])

    expect(grid[0][0].data).toBeNull()
    expect(grid[0][0].weather).toBe('晴れ')
    expect(grid[0][0].dayType).toBe('平日')
    expect(grid[0][0].hasEvent).toBe(false)
  })

  it('該当する条件のマスにデータを差し込む', () => {
    const rainy: ConditionTiming = {
      weather: '雨',
      day_type: '平日',
      has_event: false,
      sample_count: 3,
      discounted_count: 3,
      avg_first_discount_step: 10,
    }

    const grid = buildTimingGrid([rainy])

    const rainyRow = grid[2] // TIMING_WEATHERSの3番目が「雨」
    expect(rainyRow[0].data).toEqual(rainy)
    // 他のマスはデータなしのまま
    expect(rainyRow[1].data).toBeNull()
    expect(grid[0][0].data).toBeNull()
  })
})

describe('timingIntensity', () => {
  it('最小値（最も早い）は強度1になる', () => {
    expect(timingIntensity(5, 5, 20)).toBe(1)
  })

  it('最大値（最も遅い）は強度0になる', () => {
    expect(timingIntensity(20, 5, 20)).toBe(0)
  })

  it('中間値は0と1の間になる', () => {
    const mid = timingIntensity(12.5, 5, 20)
    expect(mid).toBeGreaterThan(0)
    expect(mid).toBeLessThan(1)
  })

  it('range幅が0（全条件が同じ平均）のときは中間値0.5を返す', () => {
    expect(timingIntensity(10, 10, 10)).toBe(0.5)
  })
})
