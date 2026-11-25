import { apiFetch } from './client'
import type { ComparisonResult, DayType, Weather } from './types'

export interface CompareInput {
  weather: Weather
  day_type: DayType
  has_event: boolean
  //: 長期休みの日か（docs/spec.md §5.13）
  is_long_vacation?: boolean
  //: 実際の状況（店は知らない。docs/spec.md §5.16）
  actual_situation?: string
  target_waste_rate: number
  //: 「お客さんが値引きの時刻を覚えて待つ」効果を固定スケジュール側に入れるか（docs/spec.md §5.12。仮定）
  customer_anticipation?: boolean
}

// 固定スケジュール値引きとの比較（docs/spec.md §5.9）。DBには保存されない一過性の比較
export function compareSchedules(input: CompareInput): Promise<ComparisonResult> {
  return apiFetch<ComparisonResult>('/compare', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}
