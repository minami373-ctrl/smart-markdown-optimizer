import { describe, expect, it } from 'vitest'
import { stepToClockTime } from './clock'

describe('stepToClockTime', () => {
  it('ステップ0は10:00になる', () => {
    expect(stepToClockTime(0, 40)).toBe('10:00')
  })

  it('最終ステップ（totalSteps）は22:00になる', () => {
    expect(stepToClockTime(40, 40)).toBe('22:00')
  })

  it('中間のステップは10:00〜22:00の間に線形に対応する（1ステップ18分）', () => {
    expect(stepToClockTime(20, 40)).toBe('16:00')
    expect(stepToClockTime(1, 40)).toBe('10:18')
  })

  it('19時・20時半ちょうどになるステップ（固定スケジュール比較のステップ30・35と対応）', () => {
    expect(stepToClockTime(30, 40)).toBe('19:00')
    expect(stepToClockTime(35, 40)).toBe('20:30')
  })

  it('負のステップは10:00にクランプする', () => {
    expect(stepToClockTime(-5, 40)).toBe('10:00')
  })

  it('totalStepsを超えるステップは22:00にクランプする', () => {
    expect(stepToClockTime(999, 40)).toBe('22:00')
  })

  it('割り切れないステップ数でも分単位に丸めて表示する', () => {
    // 1/7 → 10:00 + 720/7分 = 10:00 + 102.86分 → 103分 → 11:43
    expect(stepToClockTime(1, 7)).toBe('11:43')
  })
})
