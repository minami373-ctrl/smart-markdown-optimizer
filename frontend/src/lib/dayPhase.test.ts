import { describe, expect, it } from 'vitest'
import { dayPhase } from './dayPhase'

describe('dayPhase', () => {
  it('16時の補充・18時の値引き開始・閉店で区切る（15分×48ステップ）', () => {
    expect(dayPhase(0, 48)).toBe('朝の分を定価で販売中')
    expect(dayPhase(23, 48)).toBe('朝の分を定価で販売中')
    expect(dayPhase(24, 48)).toBe('16時に補充済み・定価で販売中')
    expect(dayPhase(32, 48)).toBe('値引きの時間（15分ごとに確認）')
    expect(dayPhase(47, 48)).toBe('値引きの時間（15分ごとに確認）')
    expect(dayPhase(48, 48)).toBe('閉店')
  })
})
