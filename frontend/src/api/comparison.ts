import { apiFetch } from './client'
import type { ComparisonResult, DayType, Weather } from './types'

export interface CompareInput {
  weather: Weather
  day_type: DayType
  has_event: boolean
  target_waste_rate: number
}

// 固定スケジュール値引きとの比較（docs/spec.md §5.9）。DBには保存されない一過性の比較
export function compareSchedules(input: CompareInput): Promise<ComparisonResult> {
  return apiFetch<ComparisonResult>('/compare', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}
