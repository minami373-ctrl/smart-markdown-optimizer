import { apiFetch } from './client'
import type { Opportunity } from './types'

export function fetchOpportunities(): Promise<Opportunity[]> {
  return apiFetch<Opportunity[]>('/opportunities')
}
