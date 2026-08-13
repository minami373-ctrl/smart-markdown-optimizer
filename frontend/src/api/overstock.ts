import { apiFetch } from './client'
import type { Overstock } from './types'

export function fetchOverstocks(): Promise<Overstock[]> {
  return apiFetch<Overstock[]>('/overstock')
}
