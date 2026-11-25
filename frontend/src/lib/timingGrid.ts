import type { ConditionTiming, DayType, Weather } from '../api/types'

export const TIMING_WEATHERS: Weather[] = ['晴れ', '曇り', '雨']
export const TIMING_DAY_EVENT_COMBOS: { dayType: DayType; hasEvent: boolean }[] = [
  { dayType: '平日', hasEvent: false },
  { dayType: '平日', hasEvent: true },
  { dayType: '休日', hasEvent: false },
  { dayType: '休日', hasEvent: true },
]

export interface TimingCell {
  weather: Weather
  dayType: DayType
  hasEvent: boolean
  data: ConditionTiming | null // nullなら該当する完了済みrunがまだ無い（「データなし」表示）
}

/**
 * GET /api/discount-timing の応答（該当runが無い条件は含まれない配列）から、
 * 天気×（曜日・イベント有無）の12マス固定グリッドを組み立てる純関数（docs/spec.md §4⑦）。
 * データが無いマスは`data: null`のまま返す（画面側で「データなし」と表示する）。
 */
export function buildTimingGrid(conditions: ConditionTiming[]): TimingCell[][] {
  const byKey = new Map(
    conditions.map((c) => [`${c.weather}_${c.day_type}_${c.has_event}`, c]),
  )
  return TIMING_WEATHERS.map((weather) =>
    TIMING_DAY_EVENT_COMBOS.map(({ dayType, hasEvent }) => {
      const key = `${weather}_${dayType}_${hasEvent}`
      return { weather, dayType, hasEvent, data: byKey.get(key) ?? null }
    }),
  )
}

/**
 * 平均初回値引きステップ（avgStep）を、表示中のデータ全体の範囲（minStep〜maxStep）の中で
 * 0（最も遅い＝最も薄い）〜1（最も早い＝最も濃い）の強度に変換する純関数。
 * ステップが小さい（早く値引きが必要になった）条件ほど強度を高くする（docs/spec.md §4⑦
 * 「平均初回値引きステップが早いほど濃い暖色にする」）。
 * range幅が0（全条件が同じ平均）のときは中間値0.5を返す。
 */
export function timingIntensity(avgStep: number, minStep: number, maxStep: number): number {
  if (maxStep <= minStep) return 0.5
  const ratio = (avgStep - minStep) / (maxStep - minStep)
  return 1 - Math.min(1, Math.max(0, ratio))
}
