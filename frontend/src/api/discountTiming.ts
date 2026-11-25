import { apiFetch } from './client'
import type { ConditionTiming } from './types'

export function fetchDiscountTiming(): Promise<ConditionTiming[]> {
  return apiFetch<ConditionTiming[]>('/discount-timing')
}
