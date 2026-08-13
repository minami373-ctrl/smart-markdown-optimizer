import { describe, expect, it } from 'vitest'
import { stepToClockTime } from './clock'

describe('stepToClockTime', () => {
  it('ステップ0は10:00になる', () => {
    expect(stepToClockTime(0, 40)).toBe('10:00')
  })

  it('最終ステップ（totalSteps）は21:00になる', () => {
    expect(stepToClockTime(40, 40)).toBe('21:00')
  })

  it('中間のステップは10:00〜21:00の間に線形に対応する', () => {
    // 20/40 = 半分 → 10:00と21:00のちょうど中間（15:30）
    expect(stepToClockTime(20, 40)).toBe('15:30')
  })

  it('19時前後・20時半前後になるステップを確認する（企画の出発点との対応）', () => {
    // 40ステップで11時間はきれいに割り切れないため、19:00/20:30ちょうどにはならないが、
    // 元の企画（19時=3割引・20時半=半額）の時間帯に対応するステップで近い時刻になることを確認する
    expect(stepToClockTime(33, 40)).toBe('19:05')
    expect(stepToClockTime(38, 40)).toBe('20:27')
  })

  it('負のステップは10:00にクランプする', () => {
    expect(stepToClockTime(-5, 40)).toBe('10:00')
  })

  it('totalStepsを超えるステップは21:00にクランプする', () => {
    expect(stepToClockTime(999, 40)).toBe('21:00')
  })

  it('分の丸めで60分にならない（繰り上がりが正しく処理される）', () => {
    // 39/40 → 10:00 + 660*39/40 = 10:00 + 643.5分 = 20:43.5 → 20:44に丸まる（20:60にならない）
    expect(stepToClockTime(39, 40)).toBe('20:44')
  })
})
