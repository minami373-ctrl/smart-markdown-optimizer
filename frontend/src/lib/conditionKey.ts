import type { DayType, Weather } from '../api/types'

/** backend/services/simulation.py の condition_key() と同じ形式のキーを作る。 */
export function conditionKey(weather: Weather, dayType: DayType, hasEvent: boolean): string {
  return `${weather}_${dayType}_${hasEvent ? 'あり' : 'なし'}`
}
