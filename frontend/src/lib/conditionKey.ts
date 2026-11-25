import type { DayType, Weather } from '../api/types'

/** backend/services/simulation.py の condition_key() と同じ形式のキーを作る。 */
export function conditionKey(
  weather: Weather,
  dayType: DayType,
  hasEvent: boolean,
  isLongVacation = false,
): string {
  const key = `${weather}_${dayType}_${hasEvent ? 'あり' : 'なし'}`
  // 長期休みの日は別のキー（docs/spec.md §5.13）
  return isLongVacation ? `${key}_長期休み` : key
}
