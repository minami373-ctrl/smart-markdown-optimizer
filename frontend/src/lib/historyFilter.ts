import type { DayType, SimulationSummary, Weather } from '../api/types'

export type WeatherFilter = Weather | 'すべて'
export type DayTypeFilter = DayType | 'すべて'
export type EventFilter = 'あり' | 'なし' | 'すべて'

export interface HistoryFilters {
  weather: WeatherFilter
  dayType: DayTypeFilter
  hasEvent: EventFilter
}

export const DEFAULT_HISTORY_FILTERS: HistoryFilters = {
  weather: 'すべて',
  dayType: 'すべて',
  hasEvent: 'すべて',
}

/**
 * 履歴画面（`/history`）の条件フィルタ（docs/spec.md §4③「条件フィルタ」）。
 * 天気・曜日・イベント有無の3条件はAND。「すべて」の条件は絞り込みに使わない。
 */
export function filterRuns(
  runs: SimulationSummary[],
  filters: HistoryFilters,
): SimulationSummary[] {
  return runs.filter((r) => {
    if (filters.weather !== 'すべて' && r.weather !== filters.weather) return false
    if (filters.dayType !== 'すべて' && r.day_type !== filters.dayType) return false
    if (filters.hasEvent !== 'すべて') {
      const wantsEvent = filters.hasEvent === 'あり'
      if (r.has_event !== wantsEvent) return false
    }
    return true
  })
}
