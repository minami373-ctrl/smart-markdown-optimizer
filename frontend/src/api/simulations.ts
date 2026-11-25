import { apiFetch } from './client'
import type { DayType, SimulationDetail, SimulationSummary, Weather } from './types'

export interface CreateSimulationInput {
  weather: Weather
  day_type: DayType
  has_event: boolean
  //: 長期休みの日か（docs/spec.md §5.13）
  is_long_vacation?: boolean
  //: 実際の状況（店は知らない。docs/spec.md §5.16）
  actual_situation?: string
  target_waste_rate: number
  //: ズバリ引きをナイトマネージャーが何ステップ後に承認するか（docs/spec.md §5.11。0〜3）
  approval_delay_steps?: number
}

export function createSimulation(input: CreateSimulationInput): Promise<SimulationDetail> {
  return apiFetch<SimulationDetail>('/simulations', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function fetchSimulations(): Promise<SimulationSummary[]> {
  return apiFetch<SimulationSummary[]>('/simulations')
}

export function fetchSimulation(id: number): Promise<SimulationDetail> {
  return apiFetch<SimulationDetail>(`/simulations/${id}`)
}
