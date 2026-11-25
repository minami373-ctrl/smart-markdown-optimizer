import { describe, expect, it } from 'vitest'
import { dayPhase } from './dayPhase'

describe('dayPhase', () => {
  it('16時の補充・18時の値引き開始・21時のズバリ引き・閉店で区切る', () => {
    expect(dayPhase(0, 40)).toBe('朝の分を定価で販売中')
    expect(dayPhase(19, 40)).toBe('朝の分を定価で販売中')
    expect(dayPhase(20, 40)).toBe('16時に補充済み・定価で販売中')
    expect(dayPhase(27, 40)).toBe('値引きの時間（30%引き → 半額）')
    expect(dayPhase(37, 40)).toBe('ズバリ引きの時間')
    expect(dayPhase(40, 40)).toBe('閉店')
  })
})
